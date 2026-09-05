"""Bridges real Postgres into the Second-Creator Agent. Not tied to a
play_run or signal — single-threading is a standing risk, scanned fresh
each night across every current account. Entrypoint:
`python -m agents.jobs.run_second_creator_agent`."""

import sys
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agents.llm.config import provider_for
from agents.second_creator.agent import draft_seeding_action, find_single_threaded_departments
from core.db import SessionLocal
from core.enums import ActionStatus
from core.jobs.fetch import fetch_campaign_facts
from core.models import Account, Action

# No play_run exists to track "already handled" state for this agent, so
# dedup by cooldown instead: don't re-draft for the same department
# within this window, whatever the previous draft's fate.
COOLDOWN_DAYS = 30


def _approved_without_edit_count(session: Session, action_type: str) -> int:
    return session.execute(
        select(func.count(Action.id)).where(Action.type == action_type, Action.status == ActionStatus.APPROVED)
    ).scalar_one()


def _recently_actioned_department_ids(session: Session, as_of: date) -> set[str]:
    cutoff = datetime.combine(as_of - timedelta(days=COOLDOWN_DAYS), datetime.min.time(), tzinfo=timezone.utc)
    rows = session.execute(
        select(Action.payload).where(Action.type == "second_creator_seeding", Action.created_at >= cutoff)
    ).scalars().all()
    return {payload.get("department_id") for payload in rows if payload.get("department_id")}


def run(as_of: date | None = None) -> int:
    as_of = as_of or date.today()
    session = SessionLocal()
    try:
        accounts = session.execute(select(Account).where(Account.valid_to.is_(None))).scalars().all()
        already_actioned = _recently_actioned_department_ids(session, as_of)
        promotion_count = _approved_without_edit_count(session, "second_creator_seeding")
        drafter = provider_for("second_creator_drafting")

        actions_created = 0
        for account in accounts:
            campaigns = fetch_campaign_facts(session, account.account_id)
            for candidate in find_single_threaded_departments(campaigns, as_of):
                if candidate.department_id in already_actioned:
                    continue
                action = draft_seeding_action(
                    candidate=candidate, tier=account.tier.value, drafter=drafter,
                    promotion_count=promotion_count,
                )
                session.add(
                    Action(
                        id=uuid.uuid4(), play_run_id=None, agent=action.agent, type=action.type,
                        payload=action.payload, reasoning=action.reasoning,
                        autonomy_level=action.autonomy_level, status=ActionStatus.PENDING,
                    )
                )
                actions_created += 1
        session.commit()
        print(f"Scanned {len(accounts)} accounts, drafted {actions_created} second-creator seeding actions.")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(run())
