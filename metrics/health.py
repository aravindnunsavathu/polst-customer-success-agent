"""The composite health score — ties the six dimensions and seven
overrides together. Per the implementation plan's resolution: the
composite is a weighted average renormalized over whichever dimensions
are actually computable, not forced to null the instant one dimension
(today, always campaign_quality's cousin sentiment_friction, or both)
lacks a data source. Every skipped dimension is named in null_reasons —
nothing is guessed, the score is just honestly partial."""

from datetime import date

from metrics.config import HealthModelConfig
from metrics.dimensions import (
    score_breadth,
    score_campaign_quality,
    score_relationship_coverage,
    score_sentiment_friction,
    score_value_realisation,
    score_volume_trajectory,
    seasonality_flag,
)
from metrics.overrides import apply_overrides
from metrics.types import (
    AccountContext,
    CampaignFact,
    EscalationFact,
    HealthScoreResult,
    StakeholderFact,
    ValueDocFact,
)


def derive_band(score: float, bands) -> str:
    if score >= bands.healthy_min:
        return "healthy"
    if score >= bands.watch_min:
        return "watch"
    if score >= bands.at_risk_min:
        return "at_risk"
    return "critical"


def compute_health_score(
    *,
    campaigns: list[CampaignFact],
    value_docs: list[ValueDocFact],
    stakeholders: list[StakeholderFact],
    escalations: list[EscalationFact],
    account: AccountContext,
    as_of: date,
    config: HealthModelConfig,
    cohort_outcome_metrics: list[float] | None = None,
) -> HealthScoreResult:
    dimensions = {
        "volume_trajectory": score_volume_trajectory(campaigns, account.contract_start, as_of, config),
        "breadth": score_breadth(campaigns, account, as_of, config),
        "value_realisation": score_value_realisation(value_docs, as_of, config),
        "campaign_quality": score_campaign_quality(campaigns, as_of, config, cohort_outcome_metrics),
        "relationship_coverage": score_relationship_coverage(stakeholders, as_of, config),
        "sentiment_friction": score_sentiment_friction(escalations, as_of, config),
    }

    weights = config.dimension_weights.as_dict()
    available = {name: d for name, d in dimensions.items() if d.score is not None}
    null_reasons = {name: d.reason for name, d in dimensions.items() if d.score is None and d.reason}

    composite = None
    if available:
        total_weight = sum(weights[name] for name in available)
        composite = sum(weights[name] * available[name].score for name in available) / total_weight

    consumed = sum(1 for c in campaigns if c.billable)
    cap, fired_overrides = apply_overrides(
        campaigns=campaigns,
        stakeholders=stakeholders,
        escalations=escalations,
        account=account,
        consumed=consumed,
        as_of=as_of,
        config=config,
    )

    if cap is not None:
        # An override can fire even when the composite itself is null
        # (e.g. "zero campaigns in 90 days" needs no dimension score to
        # evaluate) — the cap becomes the final score in that case, since
        # we know the account is at least this bad regardless.
        final_score = min(composite, cap) if composite is not None else cap
    else:
        final_score = composite

    band = derive_band(final_score, config.score_bands) if final_score is not None else None

    return HealthScoreResult(
        dimension_scores=dimensions,
        composite_score=composite,
        final_score=final_score,
        band=band,
        applied_overrides=fired_overrides,
        null_reasons=null_reasons,
        seasonality=seasonality_flag(campaigns, as_of, config),
        model_version=config.version,
    )
