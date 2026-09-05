from core.enums import AutonomyLevel
from agents.autonomy import is_customer_facing, raw_matrix_level, resolve_autonomy


def test_internal_actions_are_never_capped():
    # score_detect_alert / internal_brief are Auto for every tier and
    # stay Auto in v1 — nothing customer-facing is at stake.
    assert not is_customer_facing("internal_brief")
    assert resolve_autonomy("T3", "internal_brief", approved_without_edit_count=0) == AutonomyLevel.AUTO
    assert resolve_autonomy("T1", "score_detect_alert", approved_without_edit_count=0) == AutonomyLevel.AUTO


def test_customer_facing_auto_is_capped_to_draft_at_zero_history():
    assert raw_matrix_level("T3", "decay_outreach_creator") == AutonomyLevel.AUTO
    assert resolve_autonomy("T3", "decay_outreach_creator", approved_without_edit_count=0) == AutonomyLevel.DRAFT


def test_customer_facing_auto_promotes_after_threshold():
    assert resolve_autonomy("T3", "decay_outreach_creator", approved_without_edit_count=29) == AutonomyLevel.DRAFT
    assert resolve_autonomy("T3", "decay_outreach_creator", approved_without_edit_count=30) == AutonomyLevel.AUTO


def test_non_auto_levels_pass_through_unaffected_by_history():
    assert resolve_autonomy("T1", "decay_outreach_buyer", approved_without_edit_count=0) == AutonomyLevel.HUMAN_WRITES
    assert resolve_autonomy("T2", "exec_to_exec_budget_or_displacement", approved_without_edit_count=1000) == AutonomyLevel.NEVER


def test_unknown_action_type_raises():
    import pytest

    with pytest.raises(ValueError):
        raw_matrix_level("T1", "not_a_real_action_type")
