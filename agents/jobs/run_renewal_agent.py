"""Bridges real Postgres into the Renewal Agent. Entrypoint:
`python -m agents.jobs.run_renewal_agent`."""

import sys
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agents.llm.config import provider_for
from agents.renewal.agent import run_renewal_agent
from core.db import SessionLocal
from core.enums import ActionStatus, PlayType
from core.jobs.fetch import (
    account_context,
    fetch_campaign_facts,
    fetch_stakeholder_facts,
    fetch_value_doc_facts,
)
from core.models import Account, AccountPlan, Action, FeedbackItem, PlayRun


def _latest_account_plan(session: Session, account_id) -> AccountPlan | None:
    return session.execute(
        select(AccountPlan)
        .where(AccountPlan.account_id == account_id)
        .order_by(AccountPlan.last_refreshed.desc())
        .limit(1)
    ).scalar_one_or_none()


def _approved_without_edit_count(session: Session, action_types: list[str]) -> int:
    return session.execute(
        select(func.count(Action.id)).where(Action.type.in_(action_types), Action.status == ActionStatus.APPROVED)
    ).scalar_one()


def process_play_run(session: Session, play_run: PlayRun, as_of: date) -> str:
    account = session.execute(
        select(Account).where(Account.account_id == play_run.account_id, Account.valid_to.is_(None))
    ).scalar_one()
    plan = _latest_account_plan(session, play_run.account_id)
    ctx = account_context(account)
    reference_date = account.commitment_end or account.next_review_date
    if reference_date is None:
        # The trigger that opened this play_run required a reference date
        # to exist at open time; if it's since been cleared, there's
        # nothing to count down to. Leave the play_run open rather than
        # guessing — a human needs to look at why the date disappeared.
        return "no_reference_date"

    promotion_counts = {
        "renewal_value_review": _approved_without_edit_count(session, ["renewal_value_review"]),
        "renewal_commercial_proposal": _approved_without_edit_count(
            session, ["renewal_growth_proposal", "renewal_objection_check"]
        ),
    }

    result = run_renewal_agent(
        campaigns=fetch_campaign_facts(session, play_run.account_id),
        value_docs=fetch_value_doc_facts(session, play_run.account_id),
        stakeholders=fetch_stakeholder_facts(session, play_run.account_id),
        account=ctx,
        reference_date=reference_date,
        stated_objective=plan.stated_objective if plan else None,
        how_measured=plan.how_measured if plan else None,
        tier=account.tier.value,
        as_of=as_of,
        state=play_run.exit_test_results,
        brief_provider=provider_for("renewal_internal_brief"),
        drafter=provider_for("renewal_drafting"),
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

    if result.feedback_item:
        session.add(
            FeedbackItem(
                id=uuid.uuid4(), account_id=play_run.account_id,
                source=result.feedback_item["source"], verbatim=result.feedback_item["verbatim"],
                tag=result.feedback_item["tag"], routed_to=result.feedback_item["routed_to"],
            )
        )

    return result.stage


def run(as_of: date | None = None) -> int:
    as_of = as_of or date.today()
    session = SessionLocal()
    try:
        play_runs = session.execute(
            select(PlayRun).where(PlayRun.play == PlayType.RENEWAL, PlayRun.closed_at.is_(None))
        ).scalars().all()
        stage_counts: dict[str, int] = {}
        for play_run in play_runs:
            stage = process_play_run(session, play_run, as_of)
            stage_counts[stage] = stage_counts.get(stage, 0) + 1
        session.commit()
        print(f"Processed {len(play_runs)} renewal play_runs: {stage_counts}")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(run())
