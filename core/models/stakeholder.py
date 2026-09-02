import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base
from core.enums import RelationshipStrength, StakeholderType
from core.models.mixins import CreatedAtMixin, TemporalMixin, UUIDPrimaryKey, pg_enum


class Stakeholder(Base, UUIDPrimaryKey, TemporalMixin, CreatedAtMixin):
    """Versioned like Account (see core/models/account.py) — relationship
    strength and departure status change over time and nothing else in the
    schema holds a foreign key to a specific stakeholder row, so this
    stays self-contained without needing its own identity table."""

    __tablename__ = "stakeholders"

    stakeholder_id: Mapped[uuid.UUID] = mapped_column(
        default=uuid.uuid4, nullable=False, index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account_identities.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str | None] = mapped_column(String, nullable=True)
    type: Mapped[StakeholderType] = mapped_column(
        pg_enum(StakeholderType, "stakeholder_type"), nullable=False
    )
    relationship_strength: Mapped[RelationshipStrength] = mapped_column(
        pg_enum(RelationshipStrength, "relationship_strength"),
        nullable=False,
        default=RelationshipStrength.UNKNOWN,
    )
    last_contact_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    departed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # doc 05's stakeholder coverage checklist: "champion would take a
    # reference call" — one of the five +20-point relationship coverage
    # checks (doc 02 §5 dimension 5). Only meaningful for CHAMPION-type
    # rows; defaults to False rather than null since "not asked yet" and
    # "asked and declined" are both "not yet a reference," and dimension 5
    # needs a boolean, not a null, to award or withhold the +20.
    reference_willing: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    __table_args__ = (
        Index(
            "ux_stakeholders_current",
            "stakeholder_id",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
        ),
    )


class AccountPlan(Base, UUIDPrimaryKey, CreatedAtMixin):
    """Append-only: each refresh inserts a new row. 'Current' is simply the
    latest by last_refreshed — no valid_to needed since there's never a
    need to represent two overlapping plans, only a history of refreshes."""

    __tablename__ = "account_plans"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account_identities.id"), nullable=False, index=True
    )
    # A null stated_objective is the single most important gap in the
    # account (doc 05 §3) — the console (Phase 2+) surfaces it as a red
    # prompt, not a blank cell. Nullable here for exactly that reason.
    stated_objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    how_measured: Mapped[str | None] = mapped_column(Text, nullable=True)
    baseline: Mapped[str | None] = mapped_column(Text, nullable=True)
    potential_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    top_risk: Mapped[str | None] = mapped_column(Text, nullable=True)
    top_opportunity: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_refreshed: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class ValueDoc(Base, UUIDPrimaryKey, CreatedAtMixin):
    __tablename__ = "value_docs"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account_identities.id"), nullable=False, index=True
    )
    result: Mapped[str] = mapped_column(Text, nullable=False)
    metric: Mapped[str] = mapped_column(String, nullable=False)
    confirmed_by: Mapped[str | None] = mapped_column(String, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    evidence_url: Mapped[str | None] = mapped_column(String, nullable=True)
