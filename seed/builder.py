"""Pure, deterministic helpers for constructing synthetic ORM objects.
No network or database access happens here — objects are built in memory
and only written to Postgres by seed/cli.py. Keeps /seed's core data
generation testable and importable with zero I/O, per BUILD-PROMPT.md
§11's environment rule."""

import uuid
from collections import Counter
from datetime import date, datetime, time, timedelta

from core.models import (
    Account,
    AccountIdentity,
    AccountPlan,
    BillingPeriod,
    Campaign,
    Department,
    Stakeholder,
    User,
    ValueDoc,
)
from core.enums import CommercialModel, Quadrant, RelationshipStrength, StakeholderType, Tier

TEMPLATE_TYPES = ["standard_poll", "ranked_choice", "quick_pulse"]


def month_starts(as_of: date, months_back: int) -> list[date]:
    """`months_back + 1` first-of-month dates, oldest first, ending with
    the first of as_of's own month."""
    result = []
    y, m = as_of.year, as_of.month
    for i in range(months_back, -1, -1):
        mm = m - i
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        result.append(date(yy, mm, 1))
    return result


def days_in_month(d: date) -> int:
    nxt = date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)
    return (nxt - d).days


def make_account(
    rng,
    name: str,
    contract_start: date,
    tier: Tier,
    quadrant: Quadrant,
    commercial_model: CommercialModel = CommercialModel.AD_HOC,
    committed_volume: int | None = None,
    commitment_end: date | None = None,
    potential_departments: int = 3,
    potential_creators_per_dept: int = 3,
    potential_campaigns_per_creator: int = 5,
) -> tuple[AccountIdentity, Account]:
    identity_id = uuid.uuid4()
    identity = AccountIdentity(id=identity_id)
    # Synthetic review anchor for ad-hoc accounts — see the implementation
    # plan's renewal-trigger resolution. Quarterly from contract_start.
    next_review = None
    if commercial_model == CommercialModel.AD_HOC:
        months_elapsed = 0
        candidate = contract_start
        while candidate < date.today():
            months_elapsed += 3
            candidate = _add_months(contract_start, months_elapsed)
        next_review = candidate
    account = Account(
        id=uuid.uuid4(),
        account_id=identity_id,
        name=name,
        contract_start=contract_start,
        term="monthly" if commercial_model == CommercialModel.AD_HOC else "annual",
        plan="standard",
        commercial_model=commercial_model,
        committed_volume=committed_volume,
        commitment_end=commitment_end,
        next_review_date=next_review,
        tier=tier,
        quadrant=quadrant,
        potential_departments=potential_departments,
        potential_creators_per_dept=potential_creators_per_dept,
        potential_campaigns_per_creator=potential_campaigns_per_creator,
    )
    return identity, account


def _add_months(d: date, months: int) -> date:
    total = (d.year * 12 + (d.month - 1)) + months
    y, m = divmod(total, 12)
    return date(y, m + 1, min(d.day, 28))


def make_department(account_id, name: str, created_at: datetime) -> Department:
    return Department(id=uuid.uuid4(), account_id=account_id, name=name, created_at=created_at)


def make_user(
    account_id,
    department_id,
    created_at: datetime,
    role: str = "creator",
    last_active_at: datetime | None = None,
    deactivated_at: datetime | None = None,
) -> User:
    return User(
        id=uuid.uuid4(),
        account_id=account_id,
        department_id=department_id,
        role=role,
        created_at=created_at,
        last_active_at=last_active_at,
        deactivated_at=deactivated_at,
    )


def spread_campaigns_in_month(
    rng,
    month_start: date,
    count: int,
    account_id,
    department_id,
    creator_ids: list,
    as_of: date,
    abandonment_rate: float = 0.08,
) -> list[Campaign]:
    campaigns = []
    # Clip to the days actually elapsed in a partial (current) month — a
    # random offset drawn against the month's full length would otherwise
    # sometimes land after as_of, i.e. a campaign "created" in the
    # future, which is invisible to every backward-looking scoring window.
    dim = min(days_in_month(month_start), (as_of - month_start).days + 1)
    for i in range(count):
        day_offset = rng.randrange(0, dim)
        created_at = datetime.combine(month_start, time(hour=rng.randrange(8, 18))) + timedelta(
            days=day_offset
        )
        creator_id = creator_ids[i % len(creator_ids)]
        abandoned = rng.random() < abandonment_rate
        launched_at = None if abandoned else created_at + timedelta(hours=rng.randrange(1, 72))
        campaigns.append(
            Campaign(
                id=uuid.uuid4(),
                account_id=account_id,
                department_id=department_id,
                creator_user_id=creator_id,
                created_at=created_at,
                launched_at=launched_at,
                template_type=rng.choice(TEMPLATE_TYPES),
                billable=True,
            )
        )
    return campaigns


def make_campaign_on(
    account_id,
    department_id,
    creator_id,
    created_at: datetime,
    rng,
    abandonment_rate: float = 0.08,
) -> Campaign:
    """A single campaign at an exact timestamp — for scenarios that need
    precise day-level alignment (e.g. seasonal_dip's year-over-year
    comparison) rather than spread_campaigns_in_month's whole-month
    random spread."""
    abandoned = rng.random() < abandonment_rate
    launched_at = None if abandoned else created_at + timedelta(hours=rng.randrange(1, 72))
    return Campaign(
        id=uuid.uuid4(),
        account_id=account_id,
        department_id=department_id,
        creator_user_id=creator_id,
        created_at=created_at,
        launched_at=launched_at,
        template_type=rng.choice(TEMPLATE_TYPES),
        billable=True,
    )


def billing_periods_from_campaigns(account_id, campaigns: list[Campaign], months: list[date]) -> list[BillingPeriod]:
    counts = Counter(c.created_at.date().replace(day=1) for c in campaigns if c.billable)
    return [
        BillingPeriod(
            id=uuid.uuid4(),
            account_id=account_id,
            period=m,
            billable_campaign_count=counts.get(m, 0),
        )
        for m in months
    ]


def make_stakeholder(
    account_id,
    name: str,
    type_: StakeholderType,
    role: str | None = None,
    relationship_strength: RelationshipStrength = RelationshipStrength.NEUTRAL,
    last_contact_at: datetime | None = None,
    departed_at: datetime | None = None,
    reference_willing: bool = False,
) -> Stakeholder:
    return Stakeholder(
        id=uuid.uuid4(),
        stakeholder_id=uuid.uuid4(),
        account_id=account_id,
        name=name,
        role=role,
        type=type_,
        relationship_strength=relationship_strength,
        last_contact_at=last_contact_at,
        departed_at=departed_at,
        reference_willing=reference_willing,
    )


def make_account_plan(
    account_id,
    last_refreshed: datetime,
    stated_objective: str | None,
    how_measured: str | None = None,
    baseline: str | None = None,
    potential_basis: str | None = None,
    top_risk: str | None = None,
    top_opportunity: str | None = None,
) -> AccountPlan:
    return AccountPlan(
        id=uuid.uuid4(),
        account_id=account_id,
        stated_objective=stated_objective,
        how_measured=how_measured,
        baseline=baseline,
        potential_basis=potential_basis,
        top_risk=top_risk,
        top_opportunity=top_opportunity,
        last_refreshed=last_refreshed,
    )


def make_value_doc(
    account_id,
    result: str,
    metric: str,
    confirmed_by: str | None,
    confirmed_at: datetime | None,
) -> ValueDoc:
    return ValueDoc(
        id=uuid.uuid4(),
        account_id=account_id,
        result=result,
        metric=metric,
        confirmed_by=confirmed_by,
        confirmed_at=confirmed_at,
        evidence_url=None,
    )
