"""Trigger correctness tests, BUILD-PROMPT.md §6 / §15. The seasonal
suppression test is the named §15 acceptance criterion ("the seasonal
case not firing an intervention"); the "noisy history" test locks in a
real bug found while verifying against the seeded portfolio (a sparse
prior-year window produced a nonsense YoY ratio that silently suppressed
genuine decay — see metrics/dimensions.py's seasonality_flag)."""

from datetime import date, datetime, time, timedelta

from metrics.config import default_config
from signals.triggers import (
    trigger_champion_departure,
    trigger_commitment_pace_low,
    trigger_contract_signed,
    trigger_dept_zero_creators,
    trigger_expansion_candidate,
    trigger_renewal_window,
    trigger_single_creator_inactive_14d,
    trigger_volume_ratio_below_085,
    trigger_zero_campaigns_30d,
)
from signals.types import (
    AccountContext,
    CampaignFact,
    DepartmentFact,
    StakeholderFact,
    UserFact,
    ValueDocFact,
)

CONFIG = default_config()
AS_OF = date(2026, 9, 1)
CONTRACT_START = date(2024, 1, 1)  # well past every age-gate this module checks


def _campaign(dept, creator, days_ago, launched=True):
    created = datetime.combine(AS_OF - timedelta(days=days_ago), time(10, 0))
    return CampaignFact(
        id=f"{dept}-{creator}-{days_ago}",
        department_id=dept,
        creator_id=creator,
        created_at=created,
        launched_at=created + timedelta(hours=2) if launched else None,
    )


def _flat_account():
    return AccountContext(
        contract_start=CONTRACT_START, commercial_model="ad_hoc",
        committed_volume=None, commitment_end=None, potential_departments=3,
    )


# --- Volume ratio + seasonal suppression --------------------------------

def test_volume_ratio_fires_on_real_decay():
    campaigns = [_campaign("d1", "u1", d) for d in range(0, 89, 30)]  # 3 in last 90d
    campaigns += [_campaign("d1", "u1", d) for d in range(95, 179, 5)]  # ~17 in prior 90d
    result = trigger_volume_ratio_below_085(campaigns, CONTRACT_START, AS_OF, CONFIG)
    assert result is not None
    assert result.type == "decay_volume_ratio_below_085"


def test_volume_ratio_suppressed_by_genuine_seasonal_pattern():
    """The named §15 acceptance criterion: a sequential dip that recurs
    at the same point every year must NOT fire the decay trigger."""
    campaigns = [_campaign("d1", "u1", d) for d in range(0, 90, 15)]  # last 90d: 6 (the dip)
    campaigns += [_campaign("d1", "u1", d) for d in range(92, 182, 5)]  # prior 90d: 18 (normal)
    campaigns += [_campaign("d1", "u1", 365 + d) for d in range(0, 90, 15)]  # same dip, one year back
    campaigns += [_campaign("d1", "u1", 500)]  # enough history depth

    result = trigger_volume_ratio_below_085(campaigns, CONTRACT_START, AS_OF, CONFIG)
    assert result is None


def test_volume_ratio_not_suppressed_by_sparse_noisy_history():
    """Regression test: real decay with only a sliver of data landing in
    the prior-year comparison window must NOT be suppressed just because
    a wild, unreliable YoY ratio happens to fall on the "healthy" side."""
    # Real decay: 3 in last 90d vs ~17 in prior 90d (ratio well under 0.85)
    campaigns = [_campaign("d1", "u1", d) for d in range(0, 89, 30)]
    campaigns += [_campaign("d1", "u1", d) for d in range(95, 179, 5)]
    # A sparse handful of campaigns landing right at the edge of the
    # prior-year window (this is what produced a 7-24x nonsense ratio
    # against real seeded data before the coverage-depth fix)
    campaigns += [_campaign("d1", "u1", d) for d in (400, 410, 420)]

    result = trigger_volume_ratio_below_085(campaigns, CONTRACT_START, AS_OF, CONFIG)
    assert result is not None  # must still fire — the "seasonality" here is a data artifact, not real


def test_volume_ratio_skips_accounts_younger_than_180_days():
    contract_start = AS_OF - timedelta(days=30)
    campaigns = [_campaign("d1", "u1", d) for d in range(0, 20, 5)]
    result = trigger_volume_ratio_below_085(campaigns, contract_start, AS_OF, CONFIG)
    assert result is None


# --- Zero campaigns in 30 days -------------------------------------------

def test_zero_campaigns_30d_fires_for_previously_active_account():
    campaigns = [_campaign("d1", "u1", 45)]
    assert trigger_zero_campaigns_30d(campaigns, AS_OF) is not None


def test_zero_campaigns_30d_does_not_fire_for_never_active_account():
    assert trigger_zero_campaigns_30d([], AS_OF) is None


def test_zero_campaigns_30d_does_not_fire_when_recently_active():
    campaigns = [_campaign("d1", "u1", 5)]
    assert trigger_zero_campaigns_30d(campaigns, AS_OF) is None


# --- Department zero creators ---------------------------------------------

def test_dept_zero_creators_fires_when_all_users_deactivated():
    departments = [DepartmentFact(id="d1", created_at=datetime(2024, 1, 1))]
    users = [
        UserFact(id="u1", department_id="d1", created_at=datetime(2024, 1, 1),
                  last_active_at=None, deactivated_at=datetime(2026, 6, 1))
    ]
    result = trigger_dept_zero_creators(departments, users, AS_OF)
    assert len(result) == 1
    assert result[0].evidence["department_id"] == "d1"


def test_dept_zero_creators_does_not_fire_with_an_active_user():
    departments = [DepartmentFact(id="d1", created_at=datetime(2024, 1, 1))]
    users = [UserFact(id="u1", department_id="d1", created_at=datetime(2024, 1, 1),
                        last_active_at=None, deactivated_at=None)]
    assert trigger_dept_zero_creators(departments, users, AS_OF) == []


# --- Single creator inactive 14 days --------------------------------------

def test_single_creator_inactive_14d_fires():
    campaigns = [_campaign("d1", "solo", d) for d in (20, 30, 40)]
    users = [UserFact(id="solo", department_id="d1", created_at=datetime(2024, 1, 1),
                        last_active_at=datetime.combine(AS_OF - timedelta(days=20), time(9, 0)),
                        deactivated_at=None)]
    result = trigger_single_creator_inactive_14d(campaigns, users, AS_OF)
    assert len(result) == 1


def test_single_creator_inactive_14d_does_not_fire_when_recently_active():
    campaigns = [_campaign("d1", "solo", d) for d in (5, 10, 15)]
    users = [UserFact(id="solo", department_id="d1", created_at=datetime(2024, 1, 1),
                        last_active_at=datetime.combine(AS_OF - timedelta(days=2), time(9, 0)),
                        deactivated_at=None)]
    assert trigger_single_creator_inactive_14d(campaigns, users, AS_OF) == []


# --- Commitment pace -------------------------------------------------------

def test_commitment_pace_low_fires():
    account = AccountContext(
        contract_start=date(2025, 1, 1), commercial_model="committed",
        committed_volume=600, commitment_end=AS_OF + timedelta(days=60), potential_departments=2,
    )
    result = trigger_commitment_pace_low(consumed=100, account=account, as_of=AS_OF)
    assert result is not None


def test_commitment_pace_low_ignores_ad_hoc_accounts():
    result = trigger_commitment_pace_low(consumed=1, account=_flat_account(), as_of=AS_OF)
    assert result is None


# --- Champion departure -----------------------------------------------------

def test_champion_departure_fires_without_successor():
    stakeholders = [StakeholderFact(type="champion", last_contact_at=None,
                                       departed_at=datetime(2026, 7, 1))]
    assert trigger_champion_departure(stakeholders) is not None


def test_champion_departure_does_not_fire_with_a_successor():
    stakeholders = [
        StakeholderFact(type="champion", last_contact_at=None, departed_at=datetime(2026, 7, 1)),
        StakeholderFact(type="champion", last_contact_at=datetime(2026, 8, 1), departed_at=None),
    ]
    assert trigger_champion_departure(stakeholders) is None


# --- Play triggers -----------------------------------------------------------

def test_contract_signed_fires_within_grace_window():
    account = AccountContext(contract_start=AS_OF - timedelta(days=1), commercial_model="ad_hoc",
                                committed_volume=None, commitment_end=None, potential_departments=3)
    assert trigger_contract_signed(account, AS_OF) is not None


def test_contract_signed_does_not_fire_after_grace_window():
    account = AccountContext(contract_start=AS_OF - timedelta(days=10), commercial_model="ad_hoc",
                                committed_volume=None, commitment_end=None, potential_departments=3)
    assert trigger_contract_signed(account, AS_OF) is None


def test_renewal_window_fires_at_t_minus_20():
    account = AccountContext(contract_start=CONTRACT_START, commercial_model="ad_hoc",
                                committed_volume=None, commitment_end=None, potential_departments=3)
    next_review = AS_OF + timedelta(days=15)
    assert trigger_renewal_window(account, AS_OF, next_review) is not None


def test_renewal_window_does_not_fire_outside_the_window():
    account = AccountContext(contract_start=CONTRACT_START, commercial_model="ad_hoc",
                                committed_volume=None, commitment_end=None, potential_departments=3)
    next_review = AS_OF + timedelta(days=60)
    assert trigger_renewal_window(account, AS_OF, next_review) is None


def test_expansion_candidate_requires_healthy_and_addressable_department():
    campaigns = [_campaign("d1", "u1", d) for d in range(0, 60, 10)]
    value_docs = [ValueDocFact(created_at=datetime.combine(AS_OF - timedelta(days=40), time(9, 0)), confirmed_at=datetime.combine(AS_OF - timedelta(days=30), time(9, 0)))]
    account = AccountContext(contract_start=CONTRACT_START, commercial_model="ad_hoc",
                                committed_volume=None, commitment_end=None, potential_departments=3)
    result = trigger_expansion_candidate(campaigns, value_docs, account, "healthy", AS_OF)
    assert result is not None


def test_expansion_candidate_does_not_fire_when_not_healthy():
    campaigns = [_campaign("d1", "u1", d) for d in range(0, 60, 10)]
    value_docs = [ValueDocFact(created_at=datetime.combine(AS_OF - timedelta(days=40), time(9, 0)), confirmed_at=datetime.combine(AS_OF - timedelta(days=30), time(9, 0)))]
    account = AccountContext(contract_start=CONTRACT_START, commercial_model="ad_hoc",
                                committed_volume=None, commitment_end=None, potential_departments=3)
    assert trigger_expansion_candidate(campaigns, value_docs, account, "watch", AS_OF) is None
