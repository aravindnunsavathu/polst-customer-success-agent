"""Golden-file tests: ten hand-verified scores against the model in
BUILD-PROMPT.md §5 / doc 02 §3-5, satisfying the §15 acceptance
criterion ("Health scores reproduce by hand ... for ten sampled
accounts"). Every expected number in this file is computed in a comment
first, then asserted — if the assertion ever needs to change, the
arithmetic above it must be re-derived by hand, not just edited to match.

No database, no network — plain dataclasses in, plain numbers out."""

from datetime import date, datetime, time, timedelta

from metrics.config import default_config
from metrics.dimensions import score_value_realisation, score_volume_trajectory
from metrics.health import compute_health_score
from metrics.overrides import (
    check_champion_departed_no_successor,
    check_committed_utilization_floor,
    check_single_creator_whole_account,
)
from metrics.types import AccountContext, CampaignFact, StakeholderFact, ValueDocFact

CONFIG = default_config()
AS_OF = date(2026, 9, 1)


def _campaign(dept, creator, days_ago, launched=True):
    created = datetime.combine(AS_OF - timedelta(days=days_ago), time(10, 0))
    return CampaignFact(
        id=f"{dept}-{creator}-{days_ago}",
        department_id=dept,
        creator_id=creator,
        created_at=created,
        launched_at=created + timedelta(hours=2) if launched else None,
    )


# --- 1. Full composite: a healthy, fully-covered account ---------------
#
# volume: last90d offsets range(0,90,9) = 10 per dept x 2 depts = 20;
#         prior90d offsets range(95,185,9) = 10 per dept x 2 depts = 20.
#         ratio = 20/20 = 1.00 -> band [>=1.00 -> 85] -> 85
# breadth: both depts live (target=2) -> 50*min(2/2,1)=50.
#          last-90d offsets <=59 for each dept, alternating creators,
#          both creators appear -> both depts have 2+ creators -> 50*1=50.
#          breadth = 50+50 = 100
# value: confirmed 10 days ago (<=90) -> 100
# quality: 60d window (offsets<=59) = [0,9,18,27,36,45,54], alternating
#          creator assignment over full 10-offset list gives, restricted
#          to <=59: creator@even-index (0,2,4,6) = 4 campaigns, creator@
#          odd-index (1,3,5) = 3 campaigns -> both creators repeat (>=2)
#          -> repeat_rate = 2/2 = 1.0 -> rubric high_min=0.6 -> 100
# relcov: buyer + sponsor(contacted 10d ago) + reference-willing champion
#         = 3 active stakeholders -> all 5 checks true -> 100
# sentiment: no escalation data -> null, excluded from composite
#
# weights available: volume .30, breadth .20, value .20, quality .15, relcov .10
# total_weight = 0.95
# composite = (.30*85 + .20*100 + .20*100 + .15*100 + .10*100) / 0.95
#           = (25.5 + 20 + 20 + 15 + 10) / 0.95 = 90.5 / 0.95 = 95.2631578947...
# no override fires -> final = composite -> band: >=75 -> healthy
def test_healthy_fully_covered_account():
    last90_offsets = list(range(0, 90, 9))
    prior90_offsets = list(range(95, 185, 9))
    campaigns = []
    for dept, creators in (("dept_a", ("a1", "a2")), ("dept_b", ("b1", "b2"))):
        for i, days_ago in enumerate(last90_offsets):
            campaigns.append(_campaign(dept, creators[i % 2], days_ago))
        for i, days_ago in enumerate(prior90_offsets):
            campaigns.append(_campaign(dept, creators[i % 2], days_ago))

    account = AccountContext(
        contract_start=date(2024, 1, 1), commercial_model="ad_hoc",
        committed_volume=None, commitment_end=None, potential_departments=2,
    )
    value_docs = [ValueDocFact(
        created_at=datetime.combine(AS_OF - timedelta(days=20), time(9, 0)),
        confirmed_at=datetime.combine(AS_OF - timedelta(days=10), time(9, 0)),
    )]
    stakeholders = [
        StakeholderFact(type="economic_buyer", last_contact_at=None, departed_at=None),
        StakeholderFact(
            type="exec_sponsor",
            last_contact_at=datetime.combine(AS_OF - timedelta(days=10), time(9, 0)),
            departed_at=None,
        ),
        StakeholderFact(
            type="champion", last_contact_at=None, departed_at=None, reference_willing=True
        ),
    ]

    result = compute_health_score(
        campaigns=campaigns, value_docs=value_docs, stakeholders=stakeholders,
        escalations=[], account=account, as_of=AS_OF, config=CONFIG,
    )

    assert result.dimension_scores["volume_trajectory"].score == 85.0
    assert result.dimension_scores["breadth"].score == 100.0
    assert result.dimension_scores["value_realisation"].score == 100.0
    assert result.dimension_scores["campaign_quality"].score == 100.0
    assert result.dimension_scores["relationship_coverage"].score == 100.0
    assert result.dimension_scores["sentiment_friction"].score is None
    assert result.null_reasons == {"sentiment_friction": "no_escalation_or_ticket_data_instrumented"}
    assert result.composite_score == 90.5 / 0.95
    assert result.final_score == result.composite_score
    assert result.applied_overrides == []
    assert result.band == "healthy"


# --- 2. Zero campaigns in 90 days -> critical override wins ------------
#
# last90d: 0 campaigns. prior90d: 15 campaigns (offsets 100..170 step5).
# volume ratio = 0/15 = 0.0 -> band [>=0.0 -> 0] -> score 0
# breadth: live depts (last90d) = 0 -> 50*min(0/2,1) + 50*0 = 0
# quality: no campaigns in the last-60d window -> null
# value: confirmed 10 days ago -> 100
# relcov: buyer+sponsor(engaged)+champion -> 5/5 -> 100
# sentiment: null
# available: volume .30(0), breadth .20(0), value .20(100), relcov .10(100)
# total_weight=0.80; composite=(0+0+20+10)/0.80=30/0.80=37.5
# last campaign was 100 days ago -> zero_campaigns_45d fires (cap 49)
#                                 -> zero_campaigns_90d fires (cap 29)
# cap = min(49,29) = 29; final = min(37.5, 29) = 29 -> band: <30 -> critical
def test_zero_campaigns_90d_forces_critical():
    campaigns = [_campaign("dept_a", "a1", days_ago) for days_ago in range(100, 175, 5)]
    account = AccountContext(
        contract_start=date(2024, 1, 1), commercial_model="ad_hoc",
        committed_volume=None, commitment_end=None, potential_departments=2,
    )
    value_docs = [ValueDocFact(
        created_at=datetime.combine(AS_OF - timedelta(days=20), time(9, 0)),
        confirmed_at=datetime.combine(AS_OF - timedelta(days=10), time(9, 0)),
    )]
    stakeholders = [
        StakeholderFact(type="economic_buyer", last_contact_at=None, departed_at=None),
        StakeholderFact(
            type="exec_sponsor",
            last_contact_at=datetime.combine(AS_OF - timedelta(days=10), time(9, 0)),
            departed_at=None,
        ),
        StakeholderFact(type="champion", last_contact_at=None, departed_at=None, reference_willing=True),
    ]

    result = compute_health_score(
        campaigns=campaigns, value_docs=value_docs, stakeholders=stakeholders,
        escalations=[], account=account, as_of=AS_OF, config=CONFIG,
    )

    assert result.dimension_scores["volume_trajectory"].score == 0.0
    assert result.dimension_scores["breadth"].score == 0.0
    assert result.composite_score == 37.5
    fired = {o.name for o in result.applied_overrides}
    assert fired == {"zero_campaigns_45d", "zero_campaigns_90d"}
    assert result.final_score == 29.0
    assert result.band == "critical"


# --- 3. Onboarding-target path for a <180-day-old account ---------------
#
# age = 30 days (<180) -> onboarding path. elapsed=min(30,90)=30.
# expected_by_now = target_campaigns_by_day_90(6) * (30/90) = 2.0
# actual = 2 campaigns within [contract_start, as_of] -> ratio = 2/2.0 = 1.0
# band [>=1.00 -> 85] -> score 85
def test_onboarding_target_path_for_new_account():
    contract_start = AS_OF - timedelta(days=30)
    campaigns = [_campaign("dept_a", "a1", 5), _campaign("dept_a", "a1", 15)]

    result = score_volume_trajectory(campaigns, contract_start, AS_OF, CONFIG)

    assert result.score == 85.0
    assert "onboarding pace" in result.basis


# --- 4. Value realisation: confirmed but stale (>180 days) --------------
#
# confirmed 200 days ago -> >180d bucket -> documented_not_confirmed (40)
def test_value_realisation_stale_confirmation():
    value_docs = [ValueDocFact(
        created_at=datetime.combine(AS_OF - timedelta(days=210), time(9, 0)),
        confirmed_at=datetime.combine(AS_OF - timedelta(days=200), time(9, 0)),
    )]
    result = score_value_realisation(value_docs, AS_OF, CONFIG)
    assert result.score == 40.0


# --- 5. Value realisation: documented, never confirmed -------------------
#
# a value doc exists but confirmed_at is None -> documented_not_confirmed (40)
def test_value_realisation_documented_not_confirmed():
    value_docs = [ValueDocFact(
        created_at=datetime.combine(AS_OF - timedelta(days=20), time(9, 0)), confirmed_at=None
    )]
    result = score_value_realisation(value_docs, AS_OF, CONFIG)
    assert result.score == 40.0


# --- 6. Campaign quality: medium rubric band -----------------------------
#
# 5 creators active in the last 60 days; exactly 2 of them repeat
# (>=2 campaigns each) -> repeat_rate = 2/5 = 0.40
# rubric: medium_min=0.3 <= 0.40 < high_min=0.6 -> score 50
def test_campaign_quality_medium_rubric_band():
    campaigns = []
    # 2 repeat creators: 2 campaigns each, well within the last 60 days
    for creator in ("r1", "r2"):
        campaigns.append(_campaign("dept_a", creator, 5))
        campaigns.append(_campaign("dept_a", creator, 10))
    # 3 one-and-done creators
    for creator in ("s1", "s2", "s3"):
        campaigns.append(_campaign("dept_a", creator, 5))

    from metrics.dimensions import score_campaign_quality

    result = score_campaign_quality(campaigns, AS_OF, CONFIG)
    assert result.score == 50.0


# --- 7. Override: champion departed, no successor ------------------------
def test_champion_departed_no_successor_override():
    stakeholders = [
        StakeholderFact(
            type="champion",
            last_contact_at=datetime.combine(AS_OF - timedelta(days=60), time(9, 0)),
            departed_at=datetime.combine(AS_OF - timedelta(days=60), time(9, 0)),
        )
    ]
    result = check_champion_departed_no_successor(stakeholders, CONFIG)
    assert result.fired is True
    assert result.cap == CONFIG.override_caps.at_risk == 49.0


# --- 8. Override: committed utilization floor ----------------------------
#
# committed_volume=600, consumed=200 -> utilization = 200/600 = 0.3333...
# floor = 0.40, so 0.333 < 0.40 -> fires (days_left=60 <= 90 threshold)
def test_committed_utilization_floor_override():
    account = AccountContext(
        contract_start=date(2025, 1, 1), commercial_model="committed",
        committed_volume=600, commitment_end=AS_OF + timedelta(days=60),
        potential_departments=2,
    )
    result = check_committed_utilization_floor(consumed=200, account=account, as_of=AS_OF, config=CONFIG)
    assert result.fired is True
    assert result.cap == CONFIG.override_caps.at_risk == 49.0
    assert "33%" in result.reason


# --- 9. Override: single creator across the whole account, past day 90 --
def test_single_creator_whole_account_override():
    contract_start = date(2025, 1, 1)  # well past the 90-day tenure threshold
    campaigns = [_campaign("dept_a", "solo", d) for d in (5, 15, 25, 35)]
    result = check_single_creator_whole_account(campaigns, contract_start, AS_OF, CONFIG)
    assert result.fired is True
    assert result.cap == CONFIG.override_caps.watch == 74.0


# --- 10. Seasonality flag: sequential decline matches last year's dip ---
#
# >=12 months of history. last-90d count (6, a seasonal dip) vs prior-90d
# count (18, the normal quarter before it) gives a sequential ratio of
# 6/18 = 0.333 -- on its own this reads as a 67% volume collapse.
# But the SAME trailing-90d window exactly one year earlier also shows 6
# campaigns, so yoy_ratio = 6/6 = 1.0: this account does the same thing
# every year. The two ratios disagreeing by more than the configured
# threshold (0.15) is exactly the signal doc 02 §8 wants surfaced -- it's
# what tells a human "the sequential alarm is very likely seasonal."
def test_seasonality_flag_flags_yoy_consistency():
    from metrics.dimensions import seasonality_flag

    campaigns = []
    # last 90d: 6 campaigns (a seasonal dip)
    for d in range(0, 90, 15):
        campaigns.append(_campaign("dept_a", "a1", d))
    # prior 90d (the normal quarter just before the dip): 18 campaigns,
    # offsets 92..177 step 5 -- 18 values, all within [90,179]
    for d in range(92, 182, 5):
        campaigns.append(_campaign("dept_a", "a1", d))
    # the same trailing-90d window one year (365 days) earlier: also 6
    # campaigns, at days_ago = 365 + d for d in the same [0,90,15] pattern
    for d in range(0, 90, 15):
        campaigns.append(_campaign("dept_a", "a1", 365 + d))
    # enough additional history so months_of_history >= 12 -- placed at
    # 500 days ago, well outside the prior-year window [365,454] checked
    # above, so it doesn't inflate that count
    campaigns.append(_campaign("dept_a", "a1", 500))

    flag = seasonality_flag(campaigns, AS_OF, CONFIG)

    assert flag is not None
    assert flag["yoy_ratio"] == 1.0
    assert flag["sequential_ratio"] == 6 / 18
    assert flag["diverges"] is True  # 0.333 vs 1.0 differ by > 0.15 -- the point of the flag
