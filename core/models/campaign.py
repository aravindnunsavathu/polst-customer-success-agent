import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base
from core.models.mixins import CreatedAtMixin, UUIDPrimaryKey


class Campaign(Base, UUIDPrimaryKey, CreatedAtMixin):
    """created_at (from CreatedAtMixin) is the campaign-created event time
    per doc 03's Tier 1 grain; launched_at is separate and nullable so the
    abandonment rate (created but never launched) is directly computable."""

    __tablename__ = "campaigns"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account_identities.id"), nullable=False, index=True
    )
    external_id: Mapped[str | None] = mapped_column(
        String, unique=True, nullable=True, index=True
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("departments.id"), nullable=False, index=True
    )
    creator_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    launched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    template_type: Mapped[str | None] = mapped_column(String, nullable=True)
    billable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CampaignOutcome(Base, UUIDPrimaryKey, CreatedAtMixin):
    __tablename__ = "campaign_outcomes"

    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id"), nullable=False, unique=True, index=True
    )
    response_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    completion_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    reach: Mapped[int | None] = mapped_column(Integer, nullable=True)


class BillingPeriod(Base, UUIDPrimaryKey, CreatedAtMixin):
    """Finance's billed count for the period — the reconciliation job in
    /ingest diffs this against campaigns computed from our own event
    stream and raises on divergence (BUILD-PROMPT.md §4)."""

    __tablename__ = "billing_periods"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account_identities.id"), nullable=False, index=True
    )
    period: Mapped[date] = mapped_column(Date, nullable=False)
    billable_campaign_count: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "account_id", "period", name="uq_billing_periods_account_period"
        ),
    )
