from signals.orchestrator import decide, priority_score
from signals.types import SignalCandidate


def test_dedups_against_already_open_signals():
    c1 = SignalCandidate(type="decay_volume_ratio_below_085", reason="r")
    c2 = SignalCandidate(type="decay_champion_departure", reason="r")
    decision = decide([c1, c2], already_open_signal_types={"decay_volume_ratio_below_085"}, has_open_play_run=False)
    assert decision.new_signals == [c2]


def test_refuses_a_second_concurrent_play_run():
    c1 = SignalCandidate(type="decay_volume_ratio_below_085", reason="r")
    decision = decide([c1], already_open_signal_types=set(), has_open_play_run=True)
    assert decision.new_signals == [c1]  # signal still logged...
    assert decision.play_to_open is None  # ...but no second play opens


def test_decay_wins_priority_over_other_plays():
    decay = SignalCandidate(type="decay_zero_campaigns_30d", reason="r")
    expansion = SignalCandidate(type="play4_expansion_candidate", reason="r")
    decision = decide([expansion, decay], already_open_signal_types=set(), has_open_play_run=False)
    assert decision.play_to_open == "decay"


def test_no_play_opens_when_nothing_new_fired():
    c1 = SignalCandidate(type="decay_volume_ratio_below_085", reason="r")
    decision = decide([c1], already_open_signal_types={"decay_volume_ratio_below_085"}, has_open_play_run=False)
    assert decision.new_signals == []
    assert decision.play_to_open is None


def test_priority_score_ranks_tier_above_signal_count():
    t1_light = priority_score("T1", num_open_signals=1, estimated_monthly_revenue=8000)
    t3_heavy = priority_score("T3", num_open_signals=5, estimated_monthly_revenue=8000)
    assert t1_light > t3_heavy
