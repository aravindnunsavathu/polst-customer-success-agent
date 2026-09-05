from datetime import date, datetime, time, timedelta

from agents.expansion.gate import check_expansion_gate, healthy_streak_days
from signals.types import CampaignFact, StakeholderFact, ValueDocFact

AS_OF = date(2026, 9, 5)


def _campaign(dept, creator, created_on: date):
    created = datetime.combine(created_on, time(10, 0))
    return CampaignFact(id=f"{dept}-{creator}-{created_on}", department_id=dept, creator_id=creator,
                          created_at=created, launched_at=created)


def _qualifying_kwargs(**overrides):
    kwargs = dict(
        value_docs=[ValueDocFact(created_at=datetime(2026, 1, 1), confirmed_at=datetime(2026, 7, 1))],
        campaigns=[_campaign("d1", "a", AS_OF - timedelta(days=5)), _campaign("d1", "b", AS_OF - timedelta(days=3))],
        stakeholders=[StakeholderFact(type="champion", last_contact_at=datetime(2026, 8, 1), departed_at=None)],
        health_score_history=[(AS_OF - timedelta(days=d), "healthy") for d in range(0, 70, 7)],
        target_department="Franchise Relations",
        target_owner="Jamie Lee",
        champion_introduction=True,
        new_budget_holder=False,
        as_of=AS_OF,
    )
    kwargs.update(overrides)
    return kwargs


def test_fully_qualifying_account_passes():
    result = check_expansion_gate(**_qualifying_kwargs())
    assert result.qualified is True
    assert result.missing == []


def test_no_confirmed_result_fails():
    result = check_expansion_gate(**_qualifying_kwargs(value_docs=[]))
    assert "no_confirmed_result_in_last_2_quarters" in result.missing


def test_stale_confirmed_result_fails():
    result = check_expansion_gate(**_qualifying_kwargs(
        value_docs=[ValueDocFact(created_at=datetime(2025, 1, 1), confirmed_at=datetime(2025, 6, 1))],
    ))
    assert "no_confirmed_result_in_last_2_quarters" in result.missing


def test_no_health_score_history_fails_with_its_own_reason():
    result = check_expansion_gate(**_qualifying_kwargs(health_score_history=[]))
    assert "no_health_score_history" in result.missing
    assert "not_healthy_for_60_days" not in result.missing


def test_healthy_for_fewer_than_60_days_fails():
    history = [(AS_OF - timedelta(days=d), "healthy") for d in range(0, 30, 7)]
    result = check_expansion_gate(**_qualifying_kwargs(health_score_history=history))
    assert "not_healthy_for_60_days" in result.missing


def test_not_currently_healthy_fails_even_with_a_long_history():
    history = [(AS_OF - timedelta(days=d), "watch") for d in range(0, 100, 7)]
    history[0] = (AS_OF, "watch")
    result = check_expansion_gate(**_qualifying_kwargs(health_score_history=history))
    assert "not_healthy_for_60_days" in result.missing


def test_single_threaded_department_fails():
    result = check_expansion_gate(**_qualifying_kwargs(
        campaigns=[_campaign("d1", "solo", AS_OF - timedelta(days=5))],
    ))
    assert "has_single_threaded_departments" in result.missing


def test_missing_target_department_fails():
    result = check_expansion_gate(**_qualifying_kwargs(target_department=None))
    assert "no_named_target_department_or_owner" in result.missing


def test_missing_target_owner_fails():
    result = check_expansion_gate(**_qualifying_kwargs(target_owner=None))
    assert "no_named_target_department_or_owner" in result.missing


def test_champion_not_willing_fails():
    result = check_expansion_gate(**_qualifying_kwargs(champion_introduction=False))
    assert "champion_not_willing_or_departed" in result.missing


def test_departed_champion_fails_even_if_flag_is_true():
    result = check_expansion_gate(**_qualifying_kwargs(
        stakeholders=[StakeholderFact(type="champion", last_contact_at=datetime(2026, 1, 1), departed_at=datetime(2026, 6, 1))],
    ))
    assert "champion_not_willing_or_departed" in result.missing


def test_unknown_budget_holder_fails():
    result = check_expansion_gate(**_qualifying_kwargs(new_budget_holder=None))
    assert "budget_path_not_understood" in result.missing


def test_known_budget_holder_true_or_false_both_pass_that_check():
    result_false = check_expansion_gate(**_qualifying_kwargs(new_budget_holder=False))
    result_true = check_expansion_gate(**_qualifying_kwargs(new_budget_holder=True))
    assert "budget_path_not_understood" not in result_false.missing
    assert "budget_path_not_understood" not in result_true.missing


def test_multiple_missing_conditions_all_reported():
    result = check_expansion_gate(**_qualifying_kwargs(
        value_docs=[], target_department=None, new_budget_holder=None,
    ))
    assert set(result.missing) == {
        "no_confirmed_result_in_last_2_quarters", "no_named_target_department_or_owner", "budget_path_not_understood",
    }


def test_healthy_streak_days_measures_the_trailing_run_only():
    history = [
        (AS_OF - timedelta(days=90), "at_risk"),
        (AS_OF - timedelta(days=60), "healthy"),
        (AS_OF - timedelta(days=30), "healthy"),
        (AS_OF, "healthy"),
    ]
    assert healthy_streak_days(history) == 60


def test_healthy_streak_days_zero_when_currently_not_healthy():
    history = [(AS_OF - timedelta(days=10), "healthy"), (AS_OF, "watch")]
    assert healthy_streak_days(history) == 0


def test_healthy_streak_days_none_with_no_history():
    assert healthy_streak_days([]) is None
