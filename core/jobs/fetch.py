"""Shared Postgres-to-pure-facts fetchers, used by both nightly jobs
(core/jobs/score_portfolio.py and signals/jobs/evaluate_triggers.py) so
the bridge between canonical rows and metrics'/signals' pure dataclasses
is defined exactly once."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import Account, Campaign, Department, Stakeholder, User, ValueDoc
from metrics.types import AccountContext, CampaignFact, StakeholderFact, ValueDocFact
from signals.types import DepartmentFact, UserFact


def account_context(account: Account) -> AccountContext:
    return AccountContext(
        contract_start=account.contract_start,
        commercial_model=account.commercial_model.value,
        committed_volume=account.committed_volume,
        commitment_end=account.commitment_end,
        potential_departments=account.potential_departments,
    )


def fetch_campaign_facts(session: Session, account_id: uuid.UUID) -> list[CampaignFact]:
    campaigns = session.execute(select(Campaign).where(Campaign.account_id == account_id)).scalars().all()
    return [
        CampaignFact(
            id=str(c.id),
            department_id=str(c.department_id),
            creator_id=str(c.creator_user_id),
            created_at=c.created_at,
            launched_at=c.launched_at,
            billable=c.billable,
        )
        for c in campaigns
    ]


def fetch_value_doc_facts(session: Session, account_id: uuid.UUID) -> list[ValueDocFact]:
    value_docs = session.execute(select(ValueDoc).where(ValueDoc.account_id == account_id)).scalars().all()
    return [
        ValueDocFact(created_at=v.created_at, confirmed_at=v.confirmed_at, confirmed_by=v.confirmed_by)
        for v in value_docs
    ]


def fetch_stakeholder_facts(session: Session, account_id: uuid.UUID) -> list[StakeholderFact]:
    stakeholders = session.execute(
        select(Stakeholder).where(Stakeholder.account_id == account_id, Stakeholder.valid_to.is_(None))
    ).scalars().all()
    return [
        StakeholderFact(
            type=s.type.value,
            last_contact_at=s.last_contact_at,
            departed_at=s.departed_at,
            reference_willing=s.reference_willing,
        )
        for s in stakeholders
    ]


def fetch_department_facts(session: Session, account_id: uuid.UUID) -> list[DepartmentFact]:
    departments = session.execute(select(Department).where(Department.account_id == account_id)).scalars().all()
    return [DepartmentFact(id=str(d.id), created_at=d.created_at) for d in departments]


def fetch_user_facts(session: Session, account_id: uuid.UUID) -> list[UserFact]:
    users = session.execute(select(User).where(User.account_id == account_id)).scalars().all()
    return [
        UserFact(
            id=str(u.id),
            department_id=str(u.department_id) if u.department_id else None,
            created_at=u.created_at,
            last_active_at=u.last_active_at,
            deactivated_at=u.deactivated_at,
        )
        for u in users
    ]
