"""Upserts normalized records into the canonical schema. Shared by every
adapter so upsert semantics (what counts as a change, how account
versioning works) are defined exactly once — an adapter's only job is
producing NormalizedX records; it never touches Postgres directly.

Accounts are the one entity versioned per BUILD-PROMPT.md §4: a change to
a product-sourced field (name, contract_start, term, plan) closes out the
current version and opens a new one, so retrospective scoring can still
see what the account looked like before the change. CS-owned judgment
fields on the same row — tier, quadrant, commercial_model, commitment
terms, potential_* — are never touched by ingestion; they default on
first creation (lowest tier, until a human reviews the account) and are
otherwise carried forward unchanged, since no product-DB adapter is a
source of truth for CS's own classification of an account."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.enums import CommercialModel, Quadrant, Tier
from core.models import (
    Account,
    AccountIdentity,
    BillingPeriod,
    Campaign,
    Department,
    User,
)
from ingest.base import SourceAdapter

ACCOUNT_PRODUCT_FIELDS = ("name", "contract_start", "term", "plan")


@dataclass
class LoadSummary:
    accounts_created: int = 0
    accounts_versioned: int = 0
    departments_created: int = 0
    departments_updated: int = 0
    users_created: int = 0
    users_updated: int = 0
    campaigns_created: int = 0
    campaigns_updated: int = 0
    billing_periods_created: int = 0
    billing_periods_updated: int = 0


def _get_or_create_identity(session: Session, external_id: str) -> AccountIdentity:
    identity = session.execute(
        select(AccountIdentity).where(AccountIdentity.external_id == external_id)
    ).scalar_one_or_none()
    if identity is None:
        identity = AccountIdentity(id=uuid.uuid4(), external_id=external_id)
        session.add(identity)
        session.flush()
    return identity


def _current_account_version(session: Session, account_id: uuid.UUID) -> Account | None:
    return session.execute(
        select(Account).where(Account.account_id == account_id, Account.valid_to.is_(None))
    ).scalar_one_or_none()


def _upsert_account(session: Session, record, summary: LoadSummary) -> AccountIdentity:
    identity = _get_or_create_identity(session, record.external_id)
    current = _current_account_version(session, identity.id)
    new_fields = {f: getattr(record, f) for f in ACCOUNT_PRODUCT_FIELDS}

    if current is None:
        session.add(
            Account(
                id=uuid.uuid4(),
                account_id=identity.id,
                commercial_model=CommercialModel.AD_HOC,
                tier=Tier.T3,
                quadrant=Quadrant.QUALIFY,
                **new_fields,
            )
        )
        summary.accounts_created += 1
    elif any(getattr(current, f) != v for f, v in new_fields.items()):
        now = datetime.now(timezone.utc)
        current.valid_to = now
        # Flush the close-out before adding the replacement row — the
        # partial unique index (one current row per account_id) would
        # otherwise see both rows satisfy valid_to IS NULL simultaneously
        # if SQLAlchemy happened to emit the INSERT before the UPDATE.
        session.flush()
        session.add(
            Account(
                id=uuid.uuid4(),
                account_id=identity.id,
                valid_from=now,
                commercial_model=current.commercial_model,
                tier=current.tier,
                quadrant=current.quadrant,
                committed_volume=current.committed_volume,
                commitment_end=current.commitment_end,
                next_review_date=current.next_review_date,
                potential_departments=current.potential_departments,
                potential_creators_per_dept=current.potential_creators_per_dept,
                potential_campaigns_per_creator=current.potential_campaigns_per_creator,
                **new_fields,
            )
        )
        summary.accounts_versioned += 1
    session.flush()
    return identity


def _upsert_department(
    session: Session, record, account_id: uuid.UUID, summary: LoadSummary
) -> Department:
    dept = session.execute(
        select(Department).where(Department.external_id == record.external_id)
    ).scalar_one_or_none()
    if dept is None:
        dept = Department(
            id=uuid.uuid4(),
            account_id=account_id,
            external_id=record.external_id,
            name=record.name,
            created_at=record.created_at,
        )
        session.add(dept)
        summary.departments_created += 1
    elif dept.name != record.name:
        dept.name = record.name
        summary.departments_updated += 1
    session.flush()
    return dept


def _upsert_user(
    session: Session,
    record,
    account_id: uuid.UUID,
    department_id: uuid.UUID | None,
    summary: LoadSummary,
) -> User:
    user = session.execute(
        select(User).where(User.external_id == record.external_id)
    ).scalar_one_or_none()
    mutable = {
        "department_id": department_id,
        "role": record.role,
        "last_active_at": record.last_active_at,
        "deactivated_at": record.deactivated_at,
    }
    if user is None:
        user = User(
            id=uuid.uuid4(),
            account_id=account_id,
            external_id=record.external_id,
            created_at=record.created_at,
            **mutable,
        )
        session.add(user)
        summary.users_created += 1
    elif any(getattr(user, f) != v for f, v in mutable.items()):
        for f, v in mutable.items():
            setattr(user, f, v)
        summary.users_updated += 1
    session.flush()
    return user


def _upsert_campaign(
    session: Session,
    record,
    account_id: uuid.UUID,
    department: Department,
    creator_id: uuid.UUID,
    summary: LoadSummary,
) -> Campaign:
    campaign = session.execute(
        select(Campaign).where(Campaign.external_id == record.external_id)
    ).scalar_one_or_none()
    mutable = {
        "launched_at": record.launched_at,
        "template_type": record.template_type,
        "billable": record.billable,
    }
    if campaign is None:
        campaign = Campaign(
            id=uuid.uuid4(),
            account_id=account_id,
            external_id=record.external_id,
            department_id=department.id,
            creator_user_id=creator_id,
            created_at=record.created_at,
            **mutable,
        )
        session.add(campaign)
        summary.campaigns_created += 1
    elif any(getattr(campaign, f) != v for f, v in mutable.items()):
        for f, v in mutable.items():
            setattr(campaign, f, v)
        summary.campaigns_updated += 1

    if department.first_campaign_at is None or record.created_at < department.first_campaign_at:
        department.first_campaign_at = record.created_at

    session.flush()
    return campaign


def _upsert_billing_period(
    session: Session, record, account_id: uuid.UUID, summary: LoadSummary
) -> BillingPeriod:
    period = session.execute(
        select(BillingPeriod).where(
            BillingPeriod.account_id == account_id, BillingPeriod.period == record.period
        )
    ).scalar_one_or_none()
    if period is None:
        period = BillingPeriod(
            id=uuid.uuid4(),
            account_id=account_id,
            period=record.period,
            billable_campaign_count=record.billable_campaign_count,
        )
        session.add(period)
        summary.billing_periods_created += 1
    elif period.billable_campaign_count != record.billable_campaign_count:
        period.billable_campaign_count = record.billable_campaign_count
        summary.billing_periods_updated += 1
    session.flush()
    return period


def load(adapter: SourceAdapter, session: Session) -> LoadSummary:
    summary = LoadSummary()

    account_identities: dict[str, AccountIdentity] = {}
    for record in adapter.fetch_accounts():
        account_identities[record.external_id] = _upsert_account(session, record, summary)

    departments: dict[str, Department] = {}
    for record in adapter.fetch_departments():
        identity = account_identities.get(record.account_external_id)
        if identity is None:
            raise ValueError(
                f"department {record.external_id!r} references unknown account "
                f"{record.account_external_id!r} — an adapter must yield accounts "
                f"before the departments that belong to them"
            )
        departments[record.external_id] = _upsert_department(session, record, identity.id, summary)

    users: dict[str, User] = {}
    for record in adapter.fetch_users():
        identity = account_identities.get(record.account_external_id)
        if identity is None:
            raise ValueError(
                f"user {record.external_id!r} references unknown account "
                f"{record.account_external_id!r}"
            )
        dept = departments.get(record.department_external_id) if record.department_external_id else None
        users[record.external_id] = _upsert_user(session, record, identity.id, dept.id if dept else None, summary)

    for record in adapter.fetch_campaigns():
        identity = account_identities.get(record.account_external_id)
        dept = departments.get(record.department_external_id)
        creator = users.get(record.creator_external_id)
        if identity is None or dept is None or creator is None:
            raise ValueError(
                f"campaign {record.external_id!r} references an unknown account, "
                f"department, or creator"
            )
        _upsert_campaign(session, record, identity.id, dept, creator.id, summary)

    for record in adapter.fetch_billing_periods():
        identity = account_identities.get(record.account_external_id)
        if identity is None:
            raise ValueError(
                f"billing period for unknown account {record.account_external_id!r}"
            )
        _upsert_billing_period(session, record, identity.id, summary)

    session.commit()
    return summary
