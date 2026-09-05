from datetime import date, datetime

from signals.coverage import (
    check_champion_departure,
    check_first_90_days,
    check_health_critical,
    check_reference_candidate,
    effective_tier,
)
from signals.types import StakeholderFact


def test_first_90_days_only_applies_to_t1_and_t2():
    as_of = date(2026, 9, 1)
    contract_start = date(2026, 8, 1)
    assert check_first_90_days("T1", contract_start, as_of) is not None
    assert check_first_90_days("T2", contract_start, as_of) is not None
    assert check_first_90_days("T3", contract_start, as_of) is None
    assert check_first_90_days("T4", contract_start, as_of) is None


def test_first_90_days_expires_after_90_days():
    as_of = date(2026, 9, 1)
    contract_start = date(2026, 1, 1)  # well over 90 days ago
    assert check_first_90_days("T1", contract_start, as_of) is None


def test_health_critical_is_condition_based_not_calendar_based():
    result = check_health_critical("critical")
    assert result is not None
    assert result.duration_days is None  # closed by condition, not a timer

    assert check_health_critical("watch") is None


def test_champion_departure_elevation_fires_and_is_time_boxed():
    stakeholders = [StakeholderFact(type="champion", last_contact_at=None, departed_at=datetime(2026, 8, 1))]
    result = check_champion_departure(stakeholders)
    assert result is not None
    assert result.duration_days == 30


def test_reference_candidate_needs_a_willing_champion():
    no_champion = [StakeholderFact(type="economic_buyer", last_contact_at=None, departed_at=None)]
    assert check_reference_candidate("healthy", no_champion) is None

    unwilling = [StakeholderFact(type="champion", last_contact_at=None, departed_at=None, reference_willing=False)]
    assert check_reference_candidate("healthy", unwilling) is None

    willing = [StakeholderFact(type="champion", last_contact_at=None, departed_at=None, reference_willing=True)]
    assert check_reference_candidate("healthy", willing) is not None


def test_effective_tier_bumps_one_level_and_caps_at_t1():
    assert effective_tier("T3", has_active_elevation=True) == "T2"
    assert effective_tier("T1", has_active_elevation=True) == "T1"
    assert effective_tier("T3", has_active_elevation=False) == "T3"
