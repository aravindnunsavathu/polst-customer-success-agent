from datetime import date, datetime, time, timedelta

from evals.calibration import (
    RetrospectiveEvent,
    RiskEpisode,
    assess_event,
    detect_event,
    detect_risk_episodes,
    false_alarm_rate,
    hit_rate,
    median_lead_time_days,
    surprises,
)
from metrics.types import CampaignFact

AS_OF = date(2026, 9, 5)


def _campaign(dept, creator, created_on: date):
    created = datetime.combine(created_on, time(10, 0))
    return CampaignFact(id=f"{dept}-{creator}-{created_on}", department_id=dept, creator_id=creator,
                          created_at=created, launched_at=created)


def test_detect_event_none_without_a_prior_baseline():
    campaigns = [_campaign("d1", "u1", AS_OF - timedelta(days=5))]
    assert detect_event(campaigns, AS_OF) is None


def test_detect_event_churned_when_last_90d_is_completely_empty():
    campaigns = [_campaign("d1", "u1", AS_OF - timedelta(days=d)) for d in range(95, 179, 5)]
    event = detect_event(campaigns, AS_OF)
    assert event.event_type == "churned"
    assert event.volume_ratio == 0.0


def test_detect_event_decayed_past_30_percent_drop():
    prior = [_campaign("d1", "u1", AS_OF - timedelta(days=d)) for d in range(95, 179, 3)]  # ~28 campaigns
    last = [_campaign("d1", "u1", AS_OF - timedelta(days=d)) for d in range(0, 89, 15)]  # ~6 campaigns
    event = detect_event(prior + last, AS_OF)
    assert event.event_type == "decayed"


def test_detect_event_expanded_past_30_percent_growth():
    prior = [_campaign("d1", "u1", AS_OF - timedelta(days=d)) for d in range(95, 179, 20)]  # ~5 campaigns
    last = [_campaign("d1", "u1", AS_OF - timedelta(days=d)) for d in range(0, 89, 3)]  # ~30 campaigns
    event = detect_event(prior + last, AS_OF)
    assert event.event_type == "expanded"


def test_detect_event_none_in_the_normal_band():
    prior = [_campaign("d1", "u1", AS_OF - timedelta(days=d)) for d in range(95, 179, 10)]
    last = [_campaign("d1", "u1", AS_OF - timedelta(days=d)) for d in range(0, 89, 10)]
    assert detect_event(prior + last, AS_OF) is None


def _event(event_type="decayed", event_date=AS_OF):
    return RetrospectiveEvent(account_id="a1", event_type=event_type, event_date=event_date, volume_ratio=0.5)


def test_assess_event_flagged_ahead_when_at_risk_one_quarter_before():
    history = [
        (AS_OF - timedelta(days=200), "healthy"),
        (AS_OF - timedelta(days=95), "at_risk"),
        (AS_OF - timedelta(days=10), "critical"),
    ]
    assessment = assess_event(_event(), history)
    assert assessment.band_one_quarter_before == "at_risk"
    assert assessment.flagged_ahead_one_quarter is True
    assert assessment.band_two_quarters_before == "healthy"


def test_assess_event_not_flagged_when_still_healthy_one_quarter_before():
    history = [(AS_OF - timedelta(days=95), "healthy"), (AS_OF - timedelta(days=5), "watch")]
    assessment = assess_event(_event(), history)
    assert assessment.flagged_ahead_one_quarter is False


def test_assess_event_lead_time_from_first_amber_flag():
    history = [
        (AS_OF - timedelta(days=200), "healthy"),
        (AS_OF - timedelta(days=150), "watch"),  # first amber
        (AS_OF - timedelta(days=95), "at_risk"),
        (AS_OF - timedelta(days=10), "critical"),
    ]
    assessment = assess_event(_event(), history)
    assert assessment.first_amber_date == AS_OF - timedelta(days=150)
    assert assessment.lead_time_days == 150


def test_assess_event_no_lead_time_when_never_flagged_before_the_event():
    history = [(AS_OF - timedelta(days=5), "healthy")]
    assessment = assess_event(_event(), history)
    assert assessment.first_amber_date is None
    assert assessment.lead_time_days is None


def test_hit_rate_across_multiple_events():
    flagged = assess_event(_event("decayed"), [(AS_OF - timedelta(days=95), "at_risk")])
    not_flagged = assess_event(_event("churned"), [(AS_OF - timedelta(days=95), "healthy")])
    result = hit_rate([flagged, not_flagged])
    assert result.value == 0.5


def test_hit_rate_ignores_expansion_events():
    expanded = assess_event(_event("expanded"), [(AS_OF - timedelta(days=95), "healthy")])
    result = hit_rate([expanded])
    assert result.value is None
    assert result.reason == "no_decay_or_churn_events_this_period"


def test_detect_risk_episodes_finds_a_closed_episode():
    history = [
        (date(2026, 1, 1), "healthy"),
        (date(2026, 2, 1), "at_risk"),
        (date(2026, 3, 1), "critical"),
        (date(2026, 4, 1), "watch"),
    ]
    episodes = detect_risk_episodes("a1", history)
    assert len(episodes) == 1
    assert episodes[0].flagged_at == date(2026, 2, 1)
    assert episodes[0].recovered_at == date(2026, 4, 1)


def test_detect_risk_episodes_leaves_an_ongoing_episode_unrecovered():
    history = [(date(2026, 1, 1), "healthy"), (date(2026, 2, 1), "critical")]
    episodes = detect_risk_episodes("a1", history)
    assert episodes[0].recovered_at is None


def test_detect_risk_episodes_splits_two_separate_episodes():
    history = [
        (date(2026, 1, 1), "at_risk"), (date(2026, 2, 1), "healthy"),
        (date(2026, 3, 1), "at_risk"), (date(2026, 4, 1), "healthy"),
    ]
    episodes = detect_risk_episodes("a1", history)
    assert len(episodes) == 2


def test_false_alarm_rate_counts_recovered_episodes_with_no_intervention():
    candidates = detect_risk_episodes("a1", [(date(2026, 1, 1), "at_risk"), (date(2026, 2, 1), "healthy")])
    episode = RiskEpisode(candidate=candidates[0], had_intervention=False)
    result = false_alarm_rate([episode])
    assert result.value == 1.0


def test_false_alarm_rate_excludes_episodes_with_an_intervention():
    candidates = detect_risk_episodes("a1", [(date(2026, 1, 1), "at_risk"), (date(2026, 2, 1), "healthy")])
    episode = RiskEpisode(candidate=candidates[0], had_intervention=True)
    result = false_alarm_rate([episode])
    assert result.value == 0.0


def test_false_alarm_rate_excludes_episodes_that_never_recovered():
    candidates = detect_risk_episodes("a1", [(date(2026, 1, 1), "at_risk")])
    episode = RiskEpisode(candidate=candidates[0], had_intervention=False)
    result = false_alarm_rate([episode])
    assert result.value == 0.0  # never recovered -> not a false alarm either way


def test_false_alarm_rate_null_with_no_episodes():
    result = false_alarm_rate([])
    assert result.value is None


def test_median_lead_time_days_odd_count():
    assessments = [
        assess_event(_event(), [(AS_OF - timedelta(days=10), "watch")]),
        assess_event(_event(), [(AS_OF - timedelta(days=30), "watch")]),
        assess_event(_event(), [(AS_OF - timedelta(days=20), "watch")]),
    ]
    result = median_lead_time_days(assessments)
    assert result.value == 20


def test_median_lead_time_days_null_with_no_flagged_events():
    assessments = [assess_event(_event(), [(AS_OF - timedelta(days=5), "healthy")])]
    result = median_lead_time_days(assessments)
    assert result.value is None


def test_surprises_returns_only_unflagged_decay_or_churn():
    flagged_decay = assess_event(_event("decayed"), [(AS_OF - timedelta(days=95), "at_risk")])
    surprise_churn = assess_event(_event("churned"), [(AS_OF - timedelta(days=95), "healthy")])
    unflagged_expansion = assess_event(_event("expanded"), [(AS_OF - timedelta(days=95), "healthy")])
    result = surprises([flagged_decay, surprise_churn, unflagged_expansion])
    assert result == [surprise_churn]
