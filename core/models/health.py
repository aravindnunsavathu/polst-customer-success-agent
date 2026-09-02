import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base
from core.enums import HealthBand
from core.models.mixins import CreatedAtMixin, UUIDPrimaryKey, pg_enum


class HealthScore(Base, UUIDPrimaryKey, CreatedAtMixin):
    """One row per scoring run per account — append-only by construction,
    which is what makes retrospective scoring (BUILD-PROMPT.md §10) a
    plain query rather than a special case. Dimension scores and the
    composite are nullable: a null with a reason in null_reasons beats a
    confident score built on absent data (§2's fail-loud rule). Computed
    in /metrics (Phase 2) — this module only defines the shape."""

    __tablename__ = "health_scores"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account_identities.id"), nullable=False, index=True
    )
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    volume_trajectory_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    breadth_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_realisation_score: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    campaign_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    relationship_coverage_score: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    sentiment_friction_score: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    composite_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    band: Mapped[HealthBand | None] = mapped_column(
        pg_enum(HealthBand, "health_band"), nullable=True
    )
    applied_overrides: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list
    )
    null_reasons: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    model_version: Mapped[str] = mapped_column(String, nullable=False)
