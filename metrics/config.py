"""Loads metrics/config/health_model_v1.yaml into a validated config
object. Pure file I/O + pydantic validation — no network, no AWS client,
no database (BUILD-PROMPT.md §11's environment rule). On AWS this same
file is mirrored into Parameter Store (§11) by a deploy step outside this
package; nothing in /metrics itself ever calls out to fetch it."""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, model_validator

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config" / "health_model_v1.yaml"


class VolumeTrajectoryBand(BaseModel):
    min_ratio: float
    score: float


class ValueRealisationScores(BaseModel):
    confirmed_within_days_90: float
    confirmed_within_days_180: float
    documented_not_confirmed: float
    none: float


class SentimentFrictionScores(BaseModel):
    clean: float
    elevated: float
    escalation_open: float


class ScoreBands(BaseModel):
    healthy_min: float
    watch_min: float
    at_risk_min: float


class OverrideCaps(BaseModel):
    watch: float
    at_risk: float
    critical: float


class OverrideThresholds(BaseModel):
    no_campaign_days_at_risk: int
    no_campaign_days_critical: int
    commitment_utilization_floor: float
    days_left_in_term_for_utilization_test: int
    tenure_days_before_sponsor_single_creator_caps: int
    open_escalation_days_at_risk: int


class OnboardingTarget(BaseModel):
    age_days_threshold: int
    target_campaigns_by_day_90: int


class Seasonality(BaseModel):
    min_months_history_for_yoy: int
    divergence_threshold: float


class RepeatRateRubric(BaseModel):
    high_min: float
    medium_min: float


class CampaignQualityConfig(BaseModel):
    use_percentile: bool
    percentile_min_cohort_size: int
    repeat_rate_rubric: RepeatRateRubric


class RelationshipCoverageConfig(BaseModel):
    points_per_check: float


class DimensionWeights(BaseModel):
    volume_trajectory: float
    breadth: float
    value_realisation: float
    campaign_quality: float
    relationship_coverage: float
    sentiment_friction: float

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> "DimensionWeights":
        total = (
            self.volume_trajectory
            + self.breadth
            + self.value_realisation
            + self.campaign_quality
            + self.relationship_coverage
            + self.sentiment_friction
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"dimension_weights must sum to 1.0, got {total}")
        return self

    def as_dict(self) -> dict[str, float]:
        return {
            "volume_trajectory": self.volume_trajectory,
            "breadth": self.breadth,
            "value_realisation": self.value_realisation,
            "campaign_quality": self.campaign_quality,
            "relationship_coverage": self.relationship_coverage,
            "sentiment_friction": self.sentiment_friction,
        }


class HealthModelConfig(BaseModel):
    version: str
    dimension_weights: DimensionWeights
    volume_trajectory_bands: list[VolumeTrajectoryBand]
    value_realisation_scores: ValueRealisationScores
    sentiment_friction_scores: SentimentFrictionScores
    score_bands: ScoreBands
    override_caps: OverrideCaps
    override_thresholds: OverrideThresholds
    onboarding_target: OnboardingTarget
    seasonality: Seasonality
    campaign_quality: CampaignQualityConfig
    relationship_coverage: RelationshipCoverageConfig


def load_config(path: str | Path | None = None) -> HealthModelConfig:
    with open(path or DEFAULT_CONFIG_PATH) as f:
        raw = yaml.safe_load(f)
    return HealthModelConfig.model_validate(raw)


@lru_cache(maxsize=1)
def default_config() -> HealthModelConfig:
    return load_config()
