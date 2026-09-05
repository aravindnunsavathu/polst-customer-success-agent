"""The eight portfolio archetypes named in BUILD-PROMPT.md §13. Each
function returns a flat list of unsaved ORM objects for one account —
seed/generator.py collects these across scenarios into the full synthetic
portfolio; seed/cli.py is the only place that touches the database."""

import uuid
from datetime import date, datetime, time, timedelta

from core.enums import CommercialModel, Quadrant, RelationshipStrength, StakeholderType, Tier
from seed import builder

MONTHS_OF_HISTORY = 12  # + the current partial month = 13 data points


def _pattern_linear(start: int, end: int, n: int) -> list[int]:
    step = (end - start) / (n - 1)
    return [max(0, round(start + step * i)) for i in range(n)]


def _pattern_flat(value: int, n: int) -> list[int]:
    return [value] * n


def _pattern_seasonal_dip(normal: int, dip: int, n: int) -> list[int]:
    pattern = [normal] * n
    pattern[0] = dip  # same quarter, one year back
    for i in range(n - 3, n):  # the current quarter
        pattern[i] = dip
    return pattern


def _pattern_cliff(normal: int, cliff_at: int, after: int, n: int) -> list[int]:
    return [normal if i < cliff_at else after for i in range(n)]


def _build_common(
    rng,
    name: str,
    contract_start: date,
    tier: Tier,
    quadrant: Quadrant,
    department_names: list[str],
    creators_per_department: int,
    monthly_pattern_by_dept: list[list[int]],
    as_of: date,
    commercial_model: CommercialModel = CommercialModel.AD_HOC,
    committed_volume: int | None = None,
    commitment_end: date | None = None,
    single_threaded_depts: set[int] | None = None,
    deactivate_creator_in_dept: dict[int, date] | None = None,
):
    """Shared skeleton: account + departments + users + campaigns +
    billing periods, driven by a per-department monthly campaign-count
    pattern. Scenario-specific stakeholder/plan/value-doc detail is added
    by each scenario function after calling this."""

    single_threaded_depts = single_threaded_depts or set()
    deactivate_creator_in_dept = deactivate_creator_in_dept or {}
    months = builder.month_starts(as_of, MONTHS_OF_HISTORY)

    identity, account = builder.make_account(
        rng,
        name=name,
        contract_start=contract_start,
        tier=tier,
        quadrant=quadrant,
        commercial_model=commercial_model,
        committed_volume=committed_volume,
        commitment_end=commitment_end,
        potential_departments=max(len(department_names) + 1, 3),
        potential_creators_per_dept=3,
        potential_campaigns_per_creator=6,
    )

    objects = [identity, account]
    all_campaigns = []

    for dept_index, dept_name in enumerate(department_names):
        dept_created_at = datetime.combine(contract_start, time(9, 0))
        department = builder.make_department(identity.id, dept_name, dept_created_at)
        objects.append(department)

        n_creators = 1 if dept_index in single_threaded_depts else creators_per_department
        creators = []
        for c in range(n_creators):
            user = builder.make_user(
                identity.id,
                department.id,
                created_at=dept_created_at + timedelta(days=c),
                last_active_at=datetime.combine(as_of, time(9, 0)),
            )
            creators.append(user)
        objects.extend(creators)

        deactivation_date = deactivate_creator_in_dept.get(dept_index)
        if deactivation_date is not None:
            creators[0].deactivated_at = datetime.combine(deactivation_date, time(17, 0))
            creators[0].last_active_at = datetime.combine(deactivation_date, time(17, 0))

        creator_ids = [u.id for u in creators]
        pattern = monthly_pattern_by_dept[dept_index]
        dept_campaigns = []
        contract_start_month = contract_start.replace(day=1)
        for month_start, count in zip(months, pattern):
            if month_start < contract_start_month:
                continue  # the account didn't exist yet — no campaigns before signing
            dept_campaigns.extend(
                builder.spread_campaigns_in_month(
                    rng, month_start, count, identity.id, department.id, creator_ids, as_of
                )
            )
        # Belt-and-suspenders: spread_campaigns_in_month already clips the
        # current month to elapsed days, and the loop above skips whole
        # months before signing — this just guards the exact boundary day.
        dept_campaigns = [
            c for c in dept_campaigns if contract_start <= c.created_at.date() <= as_of
        ]

        department.first_campaign_at = (
            min(c.created_at for c in dept_campaigns) if dept_campaigns else None
        )
        all_campaigns.extend(dept_campaigns)

    objects.extend(all_campaigns)
    objects.extend(builder.billing_periods_from_campaigns(identity.id, all_campaigns, months))
    return identity, account, objects


def healthy_growth(rng, faker, as_of: date, index: int) -> list:
    name = f"{faker.company()} — Growth"
    contract_start = as_of - timedelta(days=500)
    pattern = _pattern_linear(5, 13, MONTHS_OF_HISTORY + 1)
    identity, account, objects = _build_common(
        rng, name, contract_start, Tier.T2, Quadrant.INVEST,
        department_names=["Marketing", "Ops"],
        creators_per_department=2,
        monthly_pattern_by_dept=[pattern, [max(0, p - 2) for p in pattern]],
        as_of=as_of,
    )
    objects.append(builder.make_stakeholder(
        identity.id, faker.name(), StakeholderType.ECONOMIC_BUYER,
        relationship_strength=RelationshipStrength.STRONG,
        last_contact_at=datetime.combine(as_of - timedelta(days=10), time(10, 0)),
    ))
    objects.append(builder.make_stakeholder(
        identity.id, faker.name(), StakeholderType.EXEC_SPONSOR,
        relationship_strength=RelationshipStrength.STRONG,
        last_contact_at=datetime.combine(as_of - timedelta(days=20), time(10, 0)),
    ))
    objects.append(builder.make_value_doc(
        identity.id, "Cut menu-decision cycle from 3 weeks to 4 days", "decision cycle time",
        confirmed_by=faker.name(), confirmed_at=datetime.combine(as_of - timedelta(days=30), time(9, 0)),
    ))
    objects.append(builder.make_account_plan(
        identity.id, datetime.combine(as_of, time(9, 0)),
        stated_objective="Get store managers a same-week read on new menu items before wide rollout.",
        how_measured="Time from concept to go/no-go decision",
        baseline="3 weeks",
        potential_basis="3 addressable departments across 2 regions",
        top_risk="None material — steady expansion",
        top_opportunity="Add the Franchise Ops department next quarter",
    ))
    return objects


def seasonal_dip(rng, faker, as_of: date, index: int) -> list:
    # Built with explicit day offsets rather than _build_common's
    # per-calendar-month pattern: metrics.dimensions.seasonality_flag
    # compares against an EXACT 90-day window ending 365 days ago, and a
    # whole-month bucket a year back only partially overlaps that window
    # (a real bug found when the decay trigger fired anyway on this
    # scenario against real seeded data — see signals/triggers.py). Offsets
    # here mirror tests/metrics/test_golden_scores.py's seasonality test,
    # which does align exactly, so this scenario now actually exercises
    # the suppression path instead of silently missing it.
    name = f"{faker.company()} — Seasonal"
    contract_start = as_of - timedelta(days=650)
    identity, account = builder.make_account(
        rng, name=name, contract_start=contract_start, tier=Tier.T2, quadrant=Quadrant.PROTECT,
        potential_departments=2, potential_creators_per_dept=3, potential_campaigns_per_creator=6,
    )
    dept_created_at = datetime.combine(contract_start, time(9, 0))
    department = builder.make_department(identity.id, "Menu Innovation", dept_created_at)
    creators = [
        builder.make_user(identity.id, department.id, dept_created_at + timedelta(days=c),
                           last_active_at=datetime.combine(as_of, time(9, 0)))
        for c in range(2)
    ]
    creator_ids = [u.id for u in creators]

    offsets = (
        list(range(0, 90, 15))          # last 90d: 6 campaigns (the dip)
        + list(range(92, 182, 5))       # prior 90d: 18 campaigns (the normal quarter)
        + [365 + d for d in range(0, 90, 15)]  # same 90d window one year ago: also 6 (the same dip)
        + list(range(185, 360, 20))     # modest off-season baseline, for realism only
        + [500]                          # pushes earliest-campaign history past the 12-month threshold
    )
    campaigns = []
    for i, days_ago in enumerate(offsets):
        created_at = datetime.combine(as_of - timedelta(days=days_ago), time(hour=rng.randrange(8, 18)))
        campaigns.append(builder.make_campaign_on(
            identity.id, department.id, creator_ids[i % len(creator_ids)], created_at, rng
        ))

    earliest = min(c.created_at for c in campaigns)
    department.first_campaign_at = earliest
    # This scenario's campaigns intentionally reach back further (500
    # days, for the YoY comparison) than the standard MONTHS_OF_HISTORY
    # window — billing_periods must cover that full range too, or months
    # with real campaigns but no billing_period row look like a
    # reconciliation discrepancy (caught by ingest.reconciliation, which
    # is exactly what it's for).
    months_back = (as_of.year - earliest.year) * 12 + (as_of.month - earliest.month)
    months = builder.month_starts(as_of, months_back)
    billing_periods = builder.billing_periods_from_campaigns(identity.id, campaigns, months)

    objects = [identity, account, department, *creators, *campaigns, *billing_periods]
    objects.append(builder.make_stakeholder(
        identity.id, faker.name(), StakeholderType.ECONOMIC_BUYER,
        relationship_strength=RelationshipStrength.STRONG,
        last_contact_at=datetime.combine(as_of - timedelta(days=15), time(10, 0)),
    ))
    objects.append(builder.make_stakeholder(
        identity.id, faker.name(), StakeholderType.EXEC_SPONSOR,
        relationship_strength=RelationshipStrength.NEUTRAL,
        last_contact_at=datetime.combine(as_of - timedelta(days=80), time(10, 0)),
    ))
    objects.append(builder.make_value_doc(
        identity.id, "Reduced seasonal menu waste 22%", "food waste %",
        confirmed_by=faker.name(), confirmed_at=datetime.combine(as_of - timedelta(days=100), time(9, 0)),
    ))
    objects.append(builder.make_account_plan(
        identity.id, datetime.combine(as_of, time(9, 0)),
        stated_objective="Validate seasonal menu changes before the holiday rush every year.",
        how_measured="Post-launch waste and repeat-order rate",
        baseline="Manual taste panels, 2 weeks",
        potential_basis="Single department, deep seasonal usage pattern",
        top_risk="Sequential volume trend looks like decay every Q1 — known and expected",
        top_opportunity="Bring in the Catering department for the same seasonal cycle",
    ))
    return objects


def slow_decay(rng, faker, as_of: date, index: int) -> list:
    name = f"{faker.company()} — Eroding"
    contract_start = as_of - timedelta(days=800)
    pattern = _pattern_linear(20, 8, MONTHS_OF_HISTORY + 1)
    identity, account, objects = _build_common(
        rng, name, contract_start, Tier.T2, Quadrant.PROTECT,
        department_names=["Store Ops", "Regional"],
        creators_per_department=2,
        monthly_pattern_by_dept=[pattern, [max(0, p - 6) for p in pattern]],
        as_of=as_of,
    )
    objects.append(builder.make_stakeholder(
        identity.id, faker.name(), StakeholderType.ECONOMIC_BUYER,
        relationship_strength=RelationshipStrength.WEAK,
        last_contact_at=datetime.combine(as_of - timedelta(days=70), time(10, 0)),
    ))
    objects.append(builder.make_account_plan(
        identity.id, datetime.combine(as_of, time(9, 0)),
        stated_objective="Faster read on regional pricing tests.",
        how_measured="Time to pricing decision",
        baseline="10 days",
        potential_basis="4 regions, historically 2 live",
        top_risk="Volume eroding for 8 straight months with no named cause yet",
        top_opportunity="Re-engage economic buyer before Q1 renewal window",
    ))
    return objects


def champion_departure_collapse(rng, faker, as_of: date, index: int) -> list:
    name = f"{faker.company()} — Single Threaded"
    contract_start = as_of - timedelta(days=400)
    departure = as_of - timedelta(days=75)
    pattern = _pattern_cliff(10, MONTHS_OF_HISTORY + 1 - 3, 0, MONTHS_OF_HISTORY + 1)
    identity, account, objects = _build_common(
        rng, name, contract_start, Tier.T2, Quadrant.PROTECT,
        department_names=["Comms"],
        creators_per_department=1,
        monthly_pattern_by_dept=[pattern],
        as_of=as_of,
        single_threaded_depts={0},
        deactivate_creator_in_dept={0: departure},
    )
    objects.append(builder.make_stakeholder(
        identity.id, faker.name(), StakeholderType.CHAMPION,
        relationship_strength=RelationshipStrength.STRONG,
        last_contact_at=datetime.combine(departure, time(17, 0)),
        departed_at=datetime.combine(departure, time(17, 0)),
    ))
    objects.append(builder.make_stakeholder(
        identity.id, faker.name(), StakeholderType.ECONOMIC_BUYER,
        relationship_strength=RelationshipStrength.NEUTRAL,
        last_contact_at=datetime.combine(as_of - timedelta(days=200), time(10, 0)),
    ))
    objects.append(builder.make_account_plan(
        identity.id, datetime.combine(as_of, time(9, 0)),
        stated_objective="Distribute compliance updates to clinical staff within 5 days.",
        how_measured="Distribution cycle time",
        baseline="19 days",
        potential_basis="Single comms department, no successor identified yet",
        top_risk="Sole champion departed 75 days ago; volume collapsed to zero, no successor named",
        top_opportunity="Re-seed a successor creator before the account goes fully dark",
    ))
    return objects


def oversold_commitment(rng, faker, as_of: date, index: int) -> list:
    name = f"{faker.company()} — Committed"
    contract_start = as_of - timedelta(days=280)
    # 600/yr committed = 50/month pace. ~9 valid months since contract_start
    # (months before signing are dropped by _build_common) at 14+6=20/month
    # lands consumption around 35-40% of the committed volume.
    pattern = _pattern_flat(14, MONTHS_OF_HISTORY + 1)
    identity, account, objects = _build_common(
        rng, name, contract_start, Tier.T1, Quadrant.INVEST,
        department_names=["Category Mgmt", "Store Ops"],
        creators_per_department=2,
        monthly_pattern_by_dept=[pattern, [max(0, p - 8) for p in pattern]],
        as_of=as_of,
        commercial_model=CommercialModel.COMMITTED,
        committed_volume=600,
        commitment_end=as_of + timedelta(days=70),
    )
    objects.append(builder.make_stakeholder(
        identity.id, faker.name(), StakeholderType.ECONOMIC_BUYER,
        relationship_strength=RelationshipStrength.NEUTRAL,
        last_contact_at=datetime.combine(as_of - timedelta(days=25), time(10, 0)),
    ))
    objects.append(builder.make_stakeholder(
        identity.id, faker.name(), StakeholderType.EXEC_SPONSOR,
        relationship_strength=RelationshipStrength.WEAK,
        last_contact_at=datetime.combine(as_of - timedelta(days=140), time(10, 0)),
    ))
    objects.append(builder.make_account_plan(
        identity.id, datetime.combine(as_of, time(9, 0)),
        stated_objective="Standardize category resets across all regions.",
        how_measured="Reset cycle time",
        baseline="6 weeks",
        potential_basis="600 campaigns/yr committed at signing, based on a 5-region rollout that stalled at 2",
        top_risk="~40% utilization with under 90 days of term left — renewal at current volume is unlikely",
        top_opportunity="Use the unused balance to launch the 3rd region before term end",
    ))
    return objects


def single_threaded_department(rng, faker, as_of: date, index: int) -> list:
    name = f"{faker.company()} — Concentrated"
    contract_start = as_of - timedelta(days=300)
    pattern = _pattern_flat(9, MONTHS_OF_HISTORY + 1)
    identity, account, objects = _build_common(
        rng, name, contract_start, Tier.T2, Quadrant.QUALIFY,
        department_names=["Field Marketing", "Category Mgmt"],
        creators_per_department=2,
        monthly_pattern_by_dept=[pattern, pattern],
        as_of=as_of,
        single_threaded_depts={0, 1},  # every live department has exactly one creator
    )
    objects.append(builder.make_stakeholder(
        identity.id, faker.name(), StakeholderType.CHAMPION,
        relationship_strength=RelationshipStrength.STRONG,
        last_contact_at=datetime.combine(as_of - timedelta(days=5), time(10, 0)),
    ))
    objects.append(builder.make_account_plan(
        identity.id, datetime.combine(as_of, time(9, 0)),
        stated_objective="Get a fast read on regional promo effectiveness.",
        how_measured="Promo lift vs. control",
        baseline="No prior read — gut call",
        potential_basis="2 departments, currently one creator each",
        top_risk="Both live departments are single-threaded — steady volume, but one departure from failure",
        top_opportunity="Seed a second creator in Field Marketing before the next planning cycle",
    ))
    return objects


def new_logo_onboarding(rng, faker, as_of: date, index: int) -> list:
    name = f"{faker.company()} — New Logo"
    contract_start = as_of - timedelta(days=18)
    identity, account, objects = _build_common(
        rng, name, contract_start, Tier.T2, Quadrant.INVEST,
        department_names=["Pilot Dept"],
        creators_per_department=1,
        monthly_pattern_by_dept=[[0] * MONTHS_OF_HISTORY + [2]],
        as_of=as_of,
    )
    objects.append(builder.make_stakeholder(
        identity.id, faker.name(), StakeholderType.ECONOMIC_BUYER,
        relationship_strength=RelationshipStrength.NEUTRAL,
        last_contact_at=datetime.combine(contract_start, time(10, 0)),
    ))
    objects.append(builder.make_account_plan(
        identity.id, datetime.combine(as_of, time(9, 0)),
        stated_objective=None,  # deliberate gap — doc 05 §3's "the single most important gap"
        how_measured=None,
        baseline=None,
        potential_basis="1 pilot department, 2 more identified at kickoff",
        top_risk="Only one named creator so far — second-creator seeding not yet started",
        top_opportunity="Convert the pilot department's first result into the case for department 2",
    ))
    return objects


def expansion_ready(rng, faker, as_of: date, index: int) -> list:
    name = f"{faker.company()} — Expansion Ready"
    contract_start = as_of - timedelta(days=280)
    pattern = _pattern_linear(8, 13, MONTHS_OF_HISTORY + 1)
    identity, account, objects = _build_common(
        rng, name, contract_start, Tier.T1, Quadrant.PROTECT,
        department_names=["Menu Innovation", "Pricing"],
        creators_per_department=2,
        monthly_pattern_by_dept=[pattern, pattern],
        as_of=as_of,
        # 3 potential departments, 2 live — the 3rd is the expansion target.
    )
    objects.append(builder.make_stakeholder(
        identity.id, faker.name(), StakeholderType.CHAMPION,
        relationship_strength=RelationshipStrength.STRONG,
        last_contact_at=datetime.combine(as_of - timedelta(days=7), time(10, 0)),
        reference_willing=True,
    ))
    objects.append(builder.make_stakeholder(
        identity.id, faker.name(), StakeholderType.EXEC_SPONSOR,
        relationship_strength=RelationshipStrength.STRONG,
        last_contact_at=datetime.combine(as_of - timedelta(days=20), time(10, 0)),
    ))
    objects.append(builder.make_stakeholder(
        identity.id, faker.name(), StakeholderType.ECONOMIC_BUYER,
        relationship_strength=RelationshipStrength.STRONG,
        last_contact_at=datetime.combine(as_of - timedelta(days=14), time(10, 0)),
    ))
    objects.append(builder.make_value_doc(
        identity.id, "Cut pricing test turnaround from 2 weeks to 3 days", "test turnaround time",
        confirmed_by=faker.name(), confirmed_at=datetime.combine(as_of - timedelta(days=40), time(9, 0)),
    ))
    objects.append(builder.make_account_plan(
        identity.id, datetime.combine(as_of, time(9, 0)),
        stated_objective="Faster, evidence-based pricing decisions across the category.",
        how_measured="Test turnaround time",
        baseline="2 weeks",
        potential_basis="3 addressable departments, 2 live and healthy",
        top_risk="None material — the qualification gate is otherwise clear",
        top_opportunity="Franchise Relations — champion has offered to make the introduction",
    ))
    return objects


SCENARIOS = [
    healthy_growth,
    seasonal_dip,
    slow_decay,
    champion_departure_collapse,
    oversold_commitment,
    single_threaded_department,
    new_logo_onboarding,
    expansion_ready,
]
