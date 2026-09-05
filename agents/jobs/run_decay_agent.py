"""Bridges real Postgres into the Decay Agent — the only module allowed
to import both `core` and `agents`, same pattern as core/jobs/ and
signals/jobs/. Entrypoint: `python -m agents.jobs.run_decay_agent`.

Two responsibilities: (1) process open decay play_runs that haven't been
diagnosed yet, and (2) close out play_runs whose 90-day recovery window
has elapsed — the play's named exit-test condition and metric (§7:
"volume back to >=90% of baseline within 90 days")."""

import sys
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agents.decay.agent import run_decay_agent
from agents.llm.config import provider_for
from core.db import SessionLocal
from core.enums import ActionStatus, PlayType
from core.jobs.fetch import (
    account_context,
    fetch_campaign_facts,
    fetch_department_facts,
    fetch_stakeholder_facts,
    fetch_user_facts,
)
from core.models import Account, AccountPlan, Action, FeedbackItem, PlayRun


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


def _unprocessed_open_decay_play_runs(session: Session) -> list[PlayRun]:
    """Open decay play_runs with no Action tied to them yet — product
    friction and seasonal outcomes never create an Action FK'd to the
    play_run in the product-friction case either... actually they do
    (route_to_product creates one); only the seasonal branch creates no
    Action, but it also closes the play_run immediately, so "open" alone
    already excludes it. The play_run_id filter here is what stops the
    job from re-diagnosing (and re-drafting) an account it already
    processed on a prior run."""
    already_processed = select(Action.play_run_id).where(Action.play_run_id.is_not(None))
    return list(
        session.execute(
            select(PlayRun).where(
                PlayRun.play == PlayType.DECAY,
                PlayRun.closed_at.is_(None),
                PlayRun.id.not_in(already_processed),
            )
        ).scalars()
    )


def process_play_run(session: Session, play_run: PlayRun, as_of: date) -> str:
    account = session.execute(
        select(Account).where(Account.account_id == play_run.account_id, Account.valid_to.is_(None))
    ).scalar_one()
    plan = _latest_account_plan(session, play_run.account_id)

    campaigns = fetch_campaign_facts(session, play_run.account_id)
    departments = fetch_department_facts(session, play_run.account_id)
    users = fetch_user_facts(session, play_run.account_id)
    stakeholders = fetch_stakeholder_facts(session, play_run.account_id)
    tier = account.tier.value

    classifier = provider_for("decay_cause_classification")
    drafter = provider_for("decay_outreach_drafting")

    # The promotion count depends on which action_type the agent lands
    # on, which we don't know until it classifies the cause. Both real
    # candidate types here are gated identically for a T3 account (the
    # only tier where the matrix says auto at all) — decay_outreach_creator
    # is the one that actually reaches the threshold check in practice —
    # so it's fetched for that type; the two internal/human-gated paths
    # don't consult this value at all (see agents/autonomy.py).
    approved_without_edit_count = _approved_without_edit_count(session, "decay_outreach_creator")

    result = run_decay_agent(
        campaigns=campaigns, departments=departments, users=users, stakeholders=stakeholders,
        account=account_context(account),
        stated_objective=plan.stated_objective if plan else None,
        how_measured=plan.how_measured if plan else None,
        tier=tier, as_of=as_of, classifier=classifier, drafter=drafter,
        approved_without_edit_count=approved_without_edit_count,
    )

    now = datetime.now(timezone.utc)
    play_run.cause_classification = result.cause_classification
    play_run.exit_test_results = result.exit_test_results
    if result.closes_play_run:
        play_run.closed_at = now
        play_run.outcome = result.outcome

    if result.action:
        session.add(
            Action(
                id=uuid.uuid4(),
                play_run_id=play_run.id,
                agent=result.action.agent,
                type=result.action.type,
                payload=result.action.payload,
                reasoning=result.action.reasoning,
                autonomy_level=result.action.autonomy_level,
                status=ActionStatus.PENDING,
            )
        )
    if result.feedback_item:
        session.add(
            FeedbackItem(
                id=uuid.uuid4(),
                account_id=play_run.account_id,
                source=result.feedback_item.source,
                verbatim=result.feedback_item.verbatim,
                tag=result.feedback_item.tag,
                routed_to=result.feedback_item.routed_to,
            )
        )
    return result.outcome


def close_recovered_or_stale_play_runs(session: Session, as_of: date, recovery_window_days: int = 90) -> dict:
    """Closes open decay play_runs whose diagnosis is >=90 days old:
    "recovered" if current volume in the diagnosed department is back to
    >=90% of the baseline captured at diagnosis time, else "unrecovered"
    — the play's exit test requires one or the other, not an indefinitely
    open play_run."""
    candidates = session.execute(
        select(PlayRun).where(
            PlayRun.play == PlayType.DECAY,
            PlayRun.closed_at.is_(None),
            PlayRun.exit_test_results["onset_date"].is_not(None),
        )
    ).scalars().all()

    counts = {"recovered": 0, "unrecovered": 0, "still_open": 0}
    now = datetime.now(timezone.utc)
    for play_run in candidates:
        if (as_of - play_run.opened_at.date()).days < recovery_window_days:
            counts["still_open"] += 1
            continue

        results = play_run.exit_test_results
        baseline = results.get("baseline_prior_90d_count")
        department_id = results.get("department_id")
        if baseline is None:
            counts["still_open"] += 1
            continue

        campaigns = fetch_campaign_facts(session, play_run.account_id)
        scoped = [c for c in campaigns if department_id is None or c.department_id == department_id]
        current = len(
            [c for c in scoped if c.billable and as_of - timedelta(days=89) <= c.created_at.date() <= as_of]
        )
        recovered = baseline > 0 and current / baseline >= 0.9

        play_run.closed_at = now
        play_run.outcome = "recovered" if recovered else "unrecovered"
        play_run.exit_test_results = {
            **results,
            "volume_recovering": recovered,
            "current_90d_count": current,
        }
        counts["recovered" if recovered else "unrecovered"] += 1
    return counts


def run(as_of: date | None = None) -> int:
    as_of = as_of or date.today()
    session = SessionLocal()
    try:
        play_runs = _unprocessed_open_decay_play_runs(session)
        outcomes: dict[str, int] = {}
        for play_run in play_runs:
            outcome = process_play_run(session, play_run, as_of)
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
        session.commit()

        recovery_counts = close_recovered_or_stale_play_runs(session, as_of)
        session.commit()

        print(f"Processed {len(play_runs)} decay play_runs: {outcomes}")
        print(f"Recovery check: {recovery_counts}")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(run())
