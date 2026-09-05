from agents.guardrails import check_volume_pushing


def test_clean_draft_passes():
    assert check_volume_pushing("Hi — checking in on your compliance rollout. Still on track?") == []


def test_flags_run_more_campaigns():
    violations = check_volume_pushing("You should run more campaigns this month to hit your goal.")
    assert "run more campaigns" in violations


def test_case_insensitive():
    violations = check_volume_pushing("RUN MORE CAMPAIGNS today!")
    assert violations
