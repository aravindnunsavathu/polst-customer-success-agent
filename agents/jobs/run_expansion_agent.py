"""Bridges real Postgres into the Expansion Agent. Entrypoint:
`python -m agents.jobs.run_expansion_agent`."""

import sys
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agents.expansion.agent import run_expansion_agent
from agents.llm.config import provider_for
from core.db import SessionLocal
from core.enums import ActionStatus, PlayType
from core.jobs.fetch import (
    fetch_campaign_facts,
    fetch_department_facts,
    fetch_health_score_history,
    fetch_stakeholder_facts,
    fetch_value_doc_facts,
)
from core.models import Account, AccountPlan, Action, PlayRun


def _latest_account_plan(session: Session, account_id) -> AccountPlan | None:
    return session.execute(
        select(AccountPlan)
        .where(AccountPlan.account_id == account_id)
        .order_by(AccountPlan.last_refreshed.desc())
        .limit(1)
    ).scalar_one_or_none()


def _approved_without_edit_count(session: Session, action_type: str) -> int:
    return session.execute(
        select(func.count(Action.id)).where(Action.type == action_type, Action.status == ActionStatus.APPROVED)
    ).scalar_one()


def _has_open_play_run(session: Session, account_id) -> bool:
    return (
        session.execute(
            select(PlayRun.id).where(PlayRun.account_id == account_id, PlayRun.closed_at.is_(None)).limit(1)
        ).scalar_one_or_none()
        is not None
    )


def process_play_run(session: Session, play_run: PlayRun, as_of: date) -> str:
    account = session.execute(
        select(Account).where(Account.account_id == play_run.account_id, Account.valid_to.is_(None))
    ).scalar_one()
    plan = _latest_account_plan(session, play_run.account_id)

    promotion_counts = {
        "expansion_champion_case": _approved_without_edit_count(session, "expansion_champion_case"),
    }

    result = run_expansion_agent(
        campaigns=fetch_campaign_facts(session, play_run.account_id),
        departments=fetch_department_facts(session, play_run.account_id),
        stakeholders=fetch_stakeholder_facts(session, play_run.account_id),
        value_docs=fetch_value_doc_facts(session, play_run.account_id),
        health_score_history=fetch_health_score_history(session, play_run.account_id),
        target_department=plan.expansion_target_department if plan else None,
        target_owner=plan.expansion_target_owner if plan else None,
        champion_introduction=plan.expansion_champion_introduction if plan else False,
        new_budget_holder=plan.expansion_new_budget_holder if plan else None,
        stated_objective=plan.stated_objective if plan else None,
        tier=account.tier.value,
        as_of=as_of,
        state=play_run.exit_test_results,
        drafter=provider_for("expansion_drafting"),
        promotion_counts=promotion_counts,
    )

    now = datetime.now(timezone.utc)
    play_run.exit_test_results = result.exit_test_results
    if result.closes_play_run:
        play_run.closed_at = now
        play_run.outcome = result.outcome

    for action in result.actions:
        session.add(
            Action(
                id=uuid.uuid4(), play_run_id=play_run.id, agent=action.agent, type=action.type,
                payload=action.payload, reasoning=action.reasoning,
                autonomy_level=action.autonomy_level, status=ActionStatus.PENDING,
            )
        )

    # "A new department triggers a full Play 1 run, not an extension of
    # the existing one" (doc 06 / BUILD-PROMPT §7). Guarded by the same
    # one-open-play-run-per-account rule the signals orchestrator applies
    # everywhere else — this play_run is already closing above, so by the
    # time this commits there's exactly one open play, not two.
    if result.opens_onboarding_play_run and not _has_open_play_run(session, play_run.account_id):
        session.add(
            PlayRun(
                id=uuid.uuid4(), account_id=play_run.account_id, play=PlayType.ONBOARDING,
                opened_at=now, exit_test_results={},
            )
        )

    return result.stage


def run(as_of: date | None = None) -> int:
    as_of = as_of or date.today()
    session = SessionLocal()
    try:
        play_runs = session.execute(
            select(PlayRun).where(PlayRun.play == PlayType.EXPANSION, PlayRun.closed_at.is_(None))
        ).scalars().all()
        stage_counts: dict[str, int] = {}
        for play_run in play_runs:
            stage = process_play_run(session, play_run, as_of)
            stage_counts[stage] = stage_counts.get(stage, 0) + 1
        session.commit()
        print(f"Processed {len(play_runs)} expansion play_runs: {stage_counts}")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(run())
