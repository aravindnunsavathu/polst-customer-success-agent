"""The Portfolio Analyst (BUILD-PROMPT.md §7): "non-customer-facing...
writes to the console, drafts nothing outbound." Four cadenced reviews,
each built the same way as every other drafting agent in this codebase —
a deterministic aggregation step (pure, tested, no LLM) followed by an
LLM synthesis step over that data (§11a's "internal synthesis" task
class: "read only by us, a mediocre brief costs nothing").

Unlike the customer-facing agents, nothing here goes through the
approval queue or the autonomy matrix — there's no send/no-send decision
to gate, since the output never reaches a customer."""

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from agents.llm.base import LLMProvider, LLMUsage
from agents.prompts import load_prompt
from core.enums import ReportType
from metrics.derived import nrr

CADENCE_DAYS = {
    ReportType.AT_RISK_CRITICAL_REVIEW: 7,
    ReportType.WATCH_REVIEW: 14,
    ReportType.MONTHLY_CEO_SNAPSHOT: 30,
    ReportType.CALIBRATION_INPUT: 90,
}


@dataclass(frozen=True)
class AccountSnapshot:
    account_id: str
    name: str
    tier: str
    band: str | None
    final_score: float | None
    open_signal_count: int
    revenue_estimate: float
    contract_start: date


@dataclass(frozen=True)
class PortfolioReportDraft:
    report_type: ReportType
    period_start: date
    period_end: date
    data: dict
    narrative: str
    llm: dict


def _usage_dict(usage: LLMUsage) -> dict:
    return {
        "provider": usage.provider, "model": usage.model, "latency_ms": usage.latency_ms,
        "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens, "cost_usd": usage.cost_usd,
    }


def report_due(report_type: ReportType, last_generated_at: datetime | None, as_of: date) -> bool:
    if last_generated_at is None:
        return True
    return (as_of - last_generated_at.date()).days >= CADENCE_DAYS[report_type]


def build_at_risk_critical_review(
    snapshots: list[AccountSnapshot], as_of: date, drafter: LLMProvider
) -> PortfolioReportDraft:
    flagged = sorted(
        (s for s in snapshots if s.band in ("at_risk", "critical")),
        key=lambda s: s.revenue_estimate, reverse=True,
    )
    data = {
        "count": len(flagged),
        "total_revenue_at_risk": sum(s.revenue_estimate for s in flagged),
        "accounts": [
            {"account_id": s.account_id, "name": s.name, "tier": s.tier, "band": s.band,
             "final_score": s.final_score, "open_signal_count": s.open_signal_count,
             "revenue_estimate": s.revenue_estimate}
            for s in flagged
        ],
    }
    response = drafter.complete(
        system="You write internal weekly at-risk/critical account review packs for a VP of Customer Success.",
        prompt=load_prompt("portfolio_at_risk_critical_review", evidence_json=json.dumps(data, indent=2)),
    )
    return PortfolioReportDraft(
        report_type=ReportType.AT_RISK_CRITICAL_REVIEW, period_start=as_of - timedelta(days=6), period_end=as_of,
        data=data, narrative=response.text, llm=_usage_dict(response.usage),
    )


def build_watch_review(
    snapshots: list[AccountSnapshot], as_of: date, drafter: LLMProvider
) -> PortfolioReportDraft:
    watch = sorted(
        (s for s in snapshots if s.band == "watch"), key=lambda s: s.revenue_estimate, reverse=True,
    )
    data = {
        "count": len(watch),
        "accounts": [
            {"account_id": s.account_id, "name": s.name, "tier": s.tier,
             "final_score": s.final_score, "revenue_estimate": s.revenue_estimate}
            for s in watch
        ],
    }
    response = drafter.complete(
        system="You write internal bi-weekly Watch-band account review packs for a VP of Customer Success.",
        prompt=load_prompt("portfolio_watch_review", evidence_json=json.dumps(data, indent=2)),
    )
    return PortfolioReportDraft(
        report_type=ReportType.WATCH_REVIEW, period_start=as_of - timedelta(days=13), period_end=as_of,
        data=data, narrative=response.text, llm=_usage_dict(response.usage),
    )


def build_monthly_ceo_snapshot(
    snapshots: list[AccountSnapshot],
    current_period_revenue_by_account: dict[str, float],
    prior_period_revenue_by_account: dict[str, float],
    as_of: date,
    drafter: LLMProvider,
) -> PortfolioReportDraft:
    """NRR is cohort-based: only accounts present in both periods count,
    per doc 01's definition ("revenue from prior-period cohort in current
    period ÷ revenue from that cohort in prior period"). New logos this
    period inflate raw revenue but are not part of the NRR cohort."""
    period_start = as_of - timedelta(days=29)
    cohort = set(current_period_revenue_by_account) & set(prior_period_revenue_by_account)
    current_cohort_revenue = sum(current_period_revenue_by_account[a] for a in cohort)
    prior_cohort_revenue = sum(prior_period_revenue_by_account[a] for a in cohort)
    nrr_result = nrr(current_cohort_revenue, prior_cohort_revenue)

    band_counts: dict[str, int] = {}
    for s in snapshots:
        key = s.band or "null"
        band_counts[key] = band_counts.get(key, 0) + 1
    new_logos = [s for s in snapshots if period_start <= s.contract_start <= as_of]

    data = {
        "band_counts": band_counts,
        "total_accounts": len(snapshots),
        "total_revenue_estimate": sum(s.revenue_estimate for s in snapshots),
        "nrr": nrr_result.value,
        "nrr_null_reason": nrr_result.reason,
        "cohort_size": len(cohort),
        "new_logos_count": len(new_logos),
        "new_logos": [{"account_id": s.account_id, "name": s.name} for s in new_logos],
    }
    response = drafter.complete(
        system="You write a monthly NRR roll-up and portfolio snapshot for a CEO.",
        prompt=load_prompt("portfolio_monthly_ceo_snapshot", evidence_json=json.dumps(data, indent=2)),
    )
    return PortfolioReportDraft(
        report_type=ReportType.MONTHLY_CEO_SNAPSHOT, period_start=period_start, period_end=as_of,
        data=data, narrative=response.text, llm=_usage_dict(response.usage),
    )


def build_calibration_input(
    calibration_summary: dict, as_of: date, drafter: LLMProvider
) -> PortfolioReportDraft:
    period_start = as_of - timedelta(days=89)
    response = drafter.complete(
        system="You write a quarterly model-calibration summary for a VP of Customer Success.",
        prompt=load_prompt("portfolio_calibration_input", evidence_json=json.dumps(calibration_summary, indent=2)),
    )
    return PortfolioReportDraft(
        report_type=ReportType.CALIBRATION_INPUT, period_start=period_start, period_end=as_of,
        data=calibration_summary, narrative=response.text, llm=_usage_dict(response.usage),
    )
