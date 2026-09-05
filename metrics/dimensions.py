"""The six health-score dimensions, doc 02 §5 / BUILD-PROMPT.md §5,
reproduced verbatim except where noted. Each function returns a
DimensionScore: a 0-100 score, or None with a named reason — the
fail-loud rule applies dimension by dimension, not just to the composite."""

from datetime import date, timedelta

from metrics.config import HealthModelConfig
from metrics.derived import (
    billable_in_window,
    active_creators_by_department,
    creator_repeat_rate,
    departments_live,
    volume_ratio_90d,
)
from metrics.types import (
    AccountContext,
    CampaignFact,
    DimensionScore,
    EscalationFact,
    StakeholderFact,
    ValueDocFact,
)


def _band_score(ratio: float, bands) -> float:
    for band in bands:
        if ratio >= band.min_ratio:
            return band.score
    return bands[-1].score


def score_volume_trajectory(
    campaigns: list[CampaignFact], contract_start: date, as_of: date, config: HealthModelConfig
) -> DimensionScore:
    age_days = (as_of - contract_start).days
    if age_days < config.onboarding_target.age_days_threshold:
        elapsed = max(1, min(age_days, 90))
        expected_by_now = config.onboarding_target.target_campaigns_by_day_90 * (elapsed / 90)
        actual = len(billable_in_window(campaigns, contract_start, as_of))
        if expected_by_now <= 0:
            return DimensionScore(None, "invalid_onboarding_target")
        ratio = actual / expected_by_now
        score = _band_score(ratio, config.volume_trajectory_bands)
        return DimensionScore(
            score,
            basis=f"onboarding pace: {actual} campaigns vs {expected_by_now:.1f} expected by day {elapsed}",
        )

    result = volume_ratio_90d(campaigns, as_of)
    if result.value is None:
        return DimensionScore(None, result.reason)
    score = _band_score(result.value, config.volume_trajectory_bands)
    return DimensionScore(score, basis=f"sequential 90d ratio {result.value:.2f}")


def seasonality_flag(campaigns: list[CampaignFact], as_of: date, config: HealthModelConfig) -> dict | None:
    """Returns diagnostic info if there's enough real history to trust a
    YoY comparison, else None. Never changes the score itself — surfaces
    context (doc 02 §8) so a human can tell a real decline from an
    expected seasonal dip.

    Eligibility requires data actually covering the whole prior-year
    window, not just "the earliest campaign is roughly 12 months old" —
    an account whose data starts 13 months back but whose prior-year
    window needs [454,365] days ago only has a few days of real overlap
    at the near edge. That produced a real bug: a handful of campaigns
    in a mostly-empty window gave a yoy_ratio in the double digits,
    which silently suppressed a genuine decay signal (see
    signals/triggers.py and tests/signals/)."""
    billable = [c for c in campaigns if c.billable]
    if not billable:
        return None
    earliest = min(c.created_at.date() for c in billable)

    one_year_ago = as_of - timedelta(days=365)
    prior_year_start = one_year_ago - timedelta(days=89)
    if earliest > prior_year_start:
        return None  # data doesn't reach back far enough to cover the whole comparison window

    current = billable_in_window(campaigns, as_of - timedelta(days=89), as_of)
    prior_year = billable_in_window(campaigns, prior_year_start, one_year_ago)
    min_sample = config.seasonality.min_campaigns_per_window_for_yoy
    if len(prior_year) < min_sample or len(current) < min_sample:
        return None  # too few campaigns in one of the windows for the ratio to mean anything

    yoy_ratio = len(current) / len(prior_year)
    sequential = volume_ratio_90d(campaigns, as_of)
    diverges = (
        sequential.value is not None
        and abs(sequential.value - yoy_ratio) > config.seasonality.divergence_threshold
    )
    return {"sequential_ratio": sequential.value, "yoy_ratio": yoy_ratio, "diverges": diverges}


def score_breadth(
    campaigns: list[CampaignFact], account: AccountContext, as_of: date, config: HealthModelConfig
) -> DimensionScore:
    if not account.potential_departments or account.potential_departments <= 0:
        return DimensionScore(None, "no_departments_target_set")

    live = departments_live(campaigns, as_of)
    active_by_dept = active_creators_by_department(campaigns, as_of)
    depts_with_2plus = sum(1 for creators in active_by_dept.values() if len(creators) >= 2)
    pct_2plus = (depts_with_2plus / live) if live > 0 else 0.0

    score = 50 * min(live / account.potential_departments, 1) + 50 * min(pct_2plus, 1)
    return DimensionScore(
        score,
        basis=f"{live}/{account.potential_departments} depts live, {depts_with_2plus}/{live} with 2+ creators",
    )


def score_value_realisation(
    value_docs: list[ValueDocFact], as_of: date, config: HealthModelConfig
) -> DimensionScore:
    scores = config.value_realisation_scores
    confirmed = [d for d in value_docs if d.confirmed_at is not None]
    if confirmed:
        most_recent = max(confirmed, key=lambda d: d.confirmed_at)
        age_days = (as_of - most_recent.confirmed_at.date()).days
        if age_days <= 90:
            return DimensionScore(scores.confirmed_within_days_90, basis=f"confirmed {age_days}d ago")
        if age_days <= 180:
            return DimensionScore(scores.confirmed_within_days_180, basis=f"confirmed {age_days}d ago")
        return DimensionScore(scores.documented_not_confirmed, basis=f"confirmation stale ({age_days}d ago)")
    if value_docs:
        return DimensionScore(scores.documented_not_confirmed, basis="documented, not customer-confirmed")
    return DimensionScore(scores.none, basis="no value doc on record")


def score_campaign_quality(
    campaigns: list[CampaignFact],
    as_of: date,
    config: HealthModelConfig,
    cohort_outcome_metrics: list[float] | None = None,
) -> DimensionScore:
    """No campaign quality metric is confirmed yet (BUILD-PROMPT.md
    §16.1) — this falls back to creator repeat rate, doc 02 §4's own
    suggested proxy ("if you can only instrument two things, make them
    volume and repeat rate"). The percentile path is real code, not a
    stub, but stays behind use_percentile until Product names a metric
    and campaign_outcomes actually has data in it."""
    if config.campaign_quality.use_percentile:
        if cohort_outcome_metrics is None:
            return DimensionScore(None, "quality_metric_not_instrumented")
        if len(cohort_outcome_metrics) < config.campaign_quality.percentile_min_cohort_size:
            return DimensionScore(None, "cohort_too_small_for_percentile")
        raise NotImplementedError(
            "percentile scoring needs a confirmed quality metric (§16.1) — not reachable "
            "while use_percentile stays false in metrics/config/health_model_v1.yaml"
        )

    repeat = creator_repeat_rate(campaigns, as_of)
    if repeat.value is None:
        return DimensionScore(None, repeat.reason)

    rubric = config.campaign_quality.repeat_rate_rubric
    if repeat.value >= rubric.high_min:
        score = 100.0
    elif repeat.value >= rubric.medium_min:
        score = 50.0
    else:
        score = 0.0
    return DimensionScore(
        score, basis=f"repeat-rate rubric proxy ({repeat.value:.0%}) — no confirmed quality metric, §16.1"
    )


def score_relationship_coverage(
    stakeholders: list[StakeholderFact], as_of: date, config: HealthModelConfig
) -> DimensionScore:
    active = [s for s in stakeholders if s.departed_at is None]
    checks = {
        "economic_buyer_identified": any(s.type == "economic_buyer" for s in active),
        "exec_sponsor_identified": any(s.type == "exec_sponsor" for s in active),
        "exec_sponsor_engaged_this_quarter": any(
            s.type == "exec_sponsor"
            and s.last_contact_at is not None
            and (as_of - s.last_contact_at.date()).days <= 90
            for s in active
        ),
        "three_plus_contacts_mapped": len(active) >= 3,
        "reference_willing_champion": any(s.type == "champion" and s.reference_willing for s in active),
    }
    points = config.relationship_coverage.points_per_check
    score = min(sum(checks.values()) * points, 100.0)
    met = ", ".join(k for k, v in checks.items() if v) or "none"
    return DimensionScore(score, basis=f"{sum(checks.values())}/5 checks met ({met})")


def score_sentiment_friction(
    escalations: list[EscalationFact], as_of: date, config: HealthModelConfig
) -> DimensionScore:
    """No escalation/support-ticket table exists in the schema yet (not
    in doc 03's instrumentation ask either) — this is always null in
    practice today. Real, not a stub: correct the moment that data
    source exists, without ever defaulting absence to "clean"."""
    if not escalations:
        return DimensionScore(None, "no_escalation_or_ticket_data_instrumented")

    scores = config.sentiment_friction_scores
    if any(e.resolved_at is None for e in escalations):
        return DimensionScore(scores.escalation_open, basis="open escalation")
    if any(e.resolved_at and (as_of - e.resolved_at.date()).days <= 90 for e in escalations):
        return DimensionScore(scores.elevated, basis="recently resolved escalation")
    return DimensionScore(scores.clean, basis="no open or recent escalations")
