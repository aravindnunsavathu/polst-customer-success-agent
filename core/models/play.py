import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base
from core.enums import ActionStatus, AutonomyLevel, PlayType, RejectionReasonCategory
from core.models.mixins import CreatedAtMixin, UUIDPrimaryKey, pg_enum


class PlayRun(Base, UUIDPrimaryKey, CreatedAtMixin):
    __tablename__ = "play_runs"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account_identities.id"), nullable=False, index=True
    )
    play: Mapped[PlayType] = mapped_column(
        pg_enum(PlayType, "play_type"), nullable=False
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    exit_test_results: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    outcome: Mapped[str | None] = mapped_column(String, nullable=True)
    cause_classification: Mapped[str | None] = mapped_column(String, nullable=True)


class Action(Base, UUIDPrimaryKey, CreatedAtMixin):
    """Rejection reasons are training data (BUILD-PROMPT.md §8) — the
    category is mandatory whenever status is 'rejected', enforced with a
    CHECK constraint rather than trusted to application code."""

    __tablename__ = "actions"

    play_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("play_runs.id"), nullable=True, index=True
    )
    agent: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    autonomy_level: Mapped[AutonomyLevel] = mapped_column(
        pg_enum(AutonomyLevel, "autonomy_level"), nullable=False
    )
    status: Mapped[ActionStatus] = mapped_column(
        pg_enum(ActionStatus, "action_status"),
        nullable=False,
        default=ActionStatus.PENDING,
    )
    approved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    rejection_reason_category: Mapped[RejectionReasonCategory | None] = mapped_column(
        pg_enum(RejectionReasonCategory, "rejection_reason_category"),
        nullable=True,
    )
    rejection_reason_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status != 'rejected' OR rejection_reason_category IS NOT NULL",
            name="rejection_reason_required",
        ),
    )
