import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base
from core.enums import SignalSeverity
from core.models.mixins import CreatedAtMixin, UUIDPrimaryKey, pg_enum


class Signal(Base, UUIDPrimaryKey, CreatedAtMixin):
    """`type` is a free-string catalogue (decay_volume_ratio,
    champion_departed, renewal_window, ...) owned and enforced by /signals
    (Phase 3) rather than a DB enum here, so adding a new trigger type
    never requires a migration."""

    __tablename__ = "signals"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account_identities.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    severity: Mapped[SignalSeverity] = mapped_column(
        pg_enum(SignalSeverity, "signal_severity"), nullable=False
    )
    fired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    sla_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
