import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base
from core.models.mixins import CreatedAtMixin, UUIDPrimaryKey


class CoverageElevation(Base, UUIDPrimaryKey, CreatedAtMixin):
    """A temporary one-level bump in touch level (doc 04 §6), separate
    from the account's permanent `tier` — e.g. a T3 account gets T2-level
    attention for its first 90 days without actually being re-tiered.
    Time-boxed by construction: `expires_at` when the trigger has a fixed
    duration (90 days, 30 days, through a renewal date); null when the
    trigger is condition-based ("until Watch or exit", "until first
    value") — those are closed out by the nightly job checking the
    condition directly, not a calendar date. Either way, `resolved_at`
    being set is the one source of truth for "no longer active" — nothing
    reads expires_at directly except the job that sets resolved_at from
    it, so accounts can never stay elevated forever by accident."""

    __tablename__ = "coverage_elevations"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account_identities.id"), nullable=False, index=True
    )
    trigger: Mapped[str] = mapped_column(String, nullable=False, index=True)
    elevated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String, nullable=True)
