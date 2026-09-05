"""Derived metrics — BUILD-PROMPT.md §5 formulas, reproduced verbatim.
Pure functions of already-fetched data; nothing here touches a database
or the network. Every metric that can legitimately be undefined (e.g. no
prior-period baseline to compare against) returns a MetricResult with a
named reason rather than a default — a zero or an imputed guess here
would be the "confident score built on absent data" CLAUDE.md calls out
as the most dangerous output this system can produce."""

from collections import Counter, defaultdict
from datetime import date, timedelta

from metrics.types import CampaignFact, MetricResult

# There is no real billing-tied revenue figure wired into this schema yet
# (BUILD-PROMPT.md's driver tree: departments live x creators x campaigns
# x price, but only the first term and the flat per-department price from
# context/polst-company-product.md are available without a pricing/
# billing integration). departments_live x this constant is the proxy
# used everywhere a "revenue" number is needed — the API's priority
# scoring, the Portfolio Analyst's reviews and NRR roll-up. One constant,
# not one hardcoded in each caller.
REVENUE_PER_DEPARTMENT_PROXY = 8000


def billable_in_window(campaigns: list[CampaignFact], start: date, end: date) -> list[CampaignFact]:
    return [c for c in campaigns if c.billable and start <= c.created_at.date() <= end]


def volume_ratio_90d(campaigns: list[CampaignFact], as_of: date) -> MetricResult:
    last_90 = billable_in_window(campaigns, as_of - timedelta(days=89), as_of)
    prior_90 = billable_in_window(
        campaigns, as_of - timedelta(days=179), as_of - timedelta(days=90)
    )
    if len(prior_90) == 0:
        return MetricResult(None, "no_prior_90d_activity_to_compare_against")
    return MetricResult(len(last_90) / len(prior_90))


def creator_repeat_rate(campaigns: list[CampaignFact], as_of: date, window_days: int = 60) -> MetricResult:
    window = billable_in_window(campaigns, as_of - timedelta(days=window_days - 1), as_of)
    counts = Counter(c.creator_id for c in window)
    if not counts:
        return MetricResult(None, "no_campaigns_in_window")
    repeat = sum(1 for n in counts.values() if n >= 2)
    return MetricResult(repeat / len(counts))


def departments_live(campaigns: list[CampaignFact], as_of: date, window_days: int = 90) -> int:
    window = billable_in_window(campaigns, as_of - timedelta(days=window_days - 1), as_of)
    return len({c.department_id for c in window})


def active_creators_by_department(
    campaigns: list[CampaignFact], as_of: date, window_days: int = 90
) -> dict[str, set[str]]:
    window = billable_in_window(campaigns, as_of - timedelta(days=window_days - 1), as_of)
    result: dict[str, set[str]] = defaultdict(set)
    for c in window:
        result[c.department_id].add(c.creator_id)
    return dict(result)


def single_threaded_department_ids(campaigns: list[CampaignFact], as_of: date, window_days: int = 90) -> list[str]:
    active = active_creators_by_department(campaigns, as_of, window_days)
    return [dept_id for dept_id, creators in active.items() if len(creators) == 1]


def abandonment_rate(campaigns: list[CampaignFact]) -> MetricResult:
    created = [c for c in campaigns if c.billable]
    if not created:
        return MetricResult(None, "no_campaigns_created")
    abandoned = sum(1 for c in created if c.launched_at is None)
    return MetricResult(abandoned / len(created))


def time_to_first_campaign(contract_start: date, campaigns: list[CampaignFact]) -> MetricResult:
    launches = [c.launched_at.date() for c in campaigns if c.launched_at is not None]
    if not launches:
        return MetricResult(None, "no_campaign_launched_yet")
    return MetricResult(float((min(launches) - contract_start).days))


def commitment_pace(
    consumed: int,
    committed_volume: int | None,
    contract_start: date,
    commitment_end: date | None,
    as_of: date,
) -> MetricResult:
    if committed_volume is None or commitment_end is None:
        return MetricResult(None, "not_a_committed_account")
    total_term_days = (commitment_end - contract_start).days
    if total_term_days <= 0:
        return MetricResult(None, "invalid_term_dates")
    elapsed_fraction = max(0.0, min(1.0, (as_of - contract_start).days / total_term_days))
    expected = committed_volume * elapsed_fraction
    if expected <= 0:
        return MetricResult(None, "term_not_yet_started")
    return MetricResult(consumed / expected)


def nrr(current_period_revenue: float, prior_period_revenue: float) -> MetricResult:
    """Portfolio-level cohort revenue aggregation (doc 01 §2's headline
    metric) is a Phase 7 Portfolio Analyst concern, not per-account health
    scoring — this is the bare ratio for when that caller has already
    aggregated the two revenue figures."""
    if prior_period_revenue == 0:
        return MetricResult(None, "no_prior_period_revenue")
    return MetricResult(current_period_revenue / prior_period_revenue)
