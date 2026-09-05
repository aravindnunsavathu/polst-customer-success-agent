"""The calibration harness (BUILD-PROMPT.md §10 / doc 02 §7): "not
optional tooling — the thing that keeps the system honest." Pure
functions, no network/DB/LLM — same discipline as /metrics, since these
numbers are themselves a form of scoring (a judgment about the model's
own track record) and CLAUDE.md's "scoring is deterministic" rule
applies here as much as it does to health scores.

Three things doc 02 §7 asks for, computed from campaign volume and
health-score history alone:
  - retrospective scoring: what did the model say ~1-2 quarters before
    an account churned, decayed >30%, or expanded >30%?
  - hit rate: % of decay/churn events flagged At-risk/Critical a
    quarter ahead.
  - false alarm rate: % of At-risk/Critical episodes that recovered
    with no intervention.
  - lead time: median days between the first non-Healthy ("amber")
    flag and the event.

Naming the *missing signal* behind a surprise is explicitly a human
judgment call in doc 02 §7 ("for every surprise, name the signal that
would have caught it") — this module surfaces which events were
surprises, it does not invent what was missing."""

from dataclasses import dataclass
from datetime import date, timedelta

from metrics.derived import volume_ratio_90d
from metrics.types import CampaignFact, MetricResult

AMBER_BANDS = {"watch", "at_risk", "critical"}
FLAGGED_BANDS = {"at_risk", "critical"}

DECAY_THRESHOLD = 0.70  # ratio <= this -> "decayed >30%"
EXPANSION_THRESHOLD = 1.30  # ratio >= this -> "expanded >30%"


@dataclass(frozen=True)
class RetrospectiveEvent:
    account_id: str
    event_type: str  # "churned" | "decayed" | "expanded"
    event_date: date
    volume_ratio: float


@dataclass(frozen=True)
class RetrospectiveAssessment:
    event: RetrospectiveEvent
    band_two_quarters_before: str | None
    band_one_quarter_before: str | None
    flagged_ahead_one_quarter: bool
    first_amber_date: date | None
    lead_time_days: int | None


@dataclass(frozen=True)
class RiskEpisodeCandidate:
    account_id: str
    flagged_at: date
    band: str
    recovered_at: date | None  # first date back in Healthy/Watch after the episode, or None


@dataclass(frozen=True)
class RiskEpisode:
    candidate: RiskEpisodeCandidate
    had_intervention: bool  # any play_run opened during [flagged_at, recovered_at or "now"]


def detect_event(campaigns: list[CampaignFact], as_of: date) -> RetrospectiveEvent | None:
    """A single account's trailing-90d-vs-prior-90d ratio, reusing the
    exact same formula the health model's volume trajectory dimension
    and the decay trigger use — "churned/decayed/expanded" here is just
    that ratio crossing a bigger threshold than the 0.85 decay trigger
    does, not a separately-defined metric."""
    ratio = volume_ratio_90d(campaigns, as_of)
    if ratio.value is None:
        return None
    if ratio.value == 0.0:
        event_type = "churned"
    elif ratio.value <= DECAY_THRESHOLD:
        event_type = "decayed"
    elif ratio.value >= EXPANSION_THRESHOLD:
        event_type = "expanded"
    else:
        return None
    return RetrospectiveEvent(account_id="", event_type=event_type, event_date=as_of, volume_ratio=ratio.value)


def _band_at_or_before(history: list[tuple[date, str | None]], target_date: date) -> str | None:
    candidates = [h for h in history if h[0] <= target_date]
    if not candidates:
        return None
    return max(candidates, key=lambda h: h[0])[1]


def _first_amber_date(history: list[tuple[date, str | None]], before: date) -> date | None:
    ordered = sorted((h for h in history if h[0] <= before), key=lambda h: h[0])
    for scored_at, band in ordered:
        if band in AMBER_BANDS:
            return scored_at
    return None


def assess_event(
    event: RetrospectiveEvent, health_score_history: list[tuple[date, str | None]]
) -> RetrospectiveAssessment:
    band_2q = _band_at_or_before(health_score_history, event.event_date - timedelta(days=180))
    band_1q = _band_at_or_before(health_score_history, event.event_date - timedelta(days=90))
    amber_date = _first_amber_date(health_score_history, event.event_date)
    lead_time = (event.event_date - amber_date).days if amber_date else None
    return RetrospectiveAssessment(
        event=event,
        band_two_quarters_before=band_2q,
        band_one_quarter_before=band_1q,
        flagged_ahead_one_quarter=band_1q in FLAGGED_BANDS,
        first_amber_date=amber_date,
        lead_time_days=lead_time,
    )


def detect_risk_episodes(
    account_id: str, health_score_history: list[tuple[date, str | None]]
) -> list[RiskEpisodeCandidate]:
    """Maximal contiguous runs of At-risk/Critical banding. 'Contiguous'
    is defined over the scored dates that exist — a gap in scoring
    history isn't specially detected here, matching this codebase's
    existing assumption of a regular nightly scoring cadence."""
    ordered = sorted(health_score_history, key=lambda h: h[0])
    episodes = []
    in_episode = False
    flagged_at = None
    episode_band = None
    for scored_at, band in ordered:
        if band in FLAGGED_BANDS:
            if not in_episode:
                in_episode = True
                flagged_at = scored_at
                episode_band = band
        else:
            if in_episode:
                episodes.append(RiskEpisodeCandidate(
                    account_id=account_id, flagged_at=flagged_at, band=episode_band, recovered_at=scored_at,
                ))
                in_episode = False
    if in_episode:
        episodes.append(RiskEpisodeCandidate(
            account_id=account_id, flagged_at=flagged_at, band=episode_band, recovered_at=None,
        ))
    return episodes


def hit_rate(assessments: list[RetrospectiveAssessment]) -> MetricResult:
    decay_or_churn = [a for a in assessments if a.event.event_type in ("decayed", "churned")]
    if not decay_or_churn:
        return MetricResult(None, "no_decay_or_churn_events_this_period")
    hits = sum(1 for a in decay_or_churn if a.flagged_ahead_one_quarter)
    return MetricResult(hits / len(decay_or_churn))


def false_alarm_rate(episodes: list[RiskEpisode]) -> MetricResult:
    if not episodes:
        return MetricResult(None, "no_at_risk_or_critical_episodes_this_period")
    false_alarms = sum(1 for e in episodes if e.candidate.recovered_at is not None and not e.had_intervention)
    return MetricResult(false_alarms / len(episodes))


def median_lead_time_days(assessments: list[RetrospectiveAssessment]) -> MetricResult:
    values = sorted(a.lead_time_days for a in assessments if a.lead_time_days is not None)
    if not values:
        return MetricResult(None, "no_events_with_a_prior_amber_flag")
    n = len(values)
    median = values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2
    return MetricResult(median)


def surprises(assessments: list[RetrospectiveAssessment]) -> list[RetrospectiveAssessment]:
    """Decay/churn events the model did NOT flag a quarter ahead — doc 02
    §7's "did the score move first, or did the outcome surprise you?"
    Naming the missing signal is a human step, not automated here."""
    return [
        a for a in assessments
        if a.event.event_type in ("decayed", "churned") and not a.flagged_ahead_one_quarter
    ]
