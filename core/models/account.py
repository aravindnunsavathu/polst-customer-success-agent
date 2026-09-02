import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base
from core.enums import CommercialModel, Quadrant, Tier
from core.models.mixins import CreatedAtMixin, TemporalMixin, UUIDPrimaryKey, pg_enum


class AccountIdentity(Base, UUIDPrimaryKey, CreatedAtMixin):
    """Stable identity row that an account's versioned attribute rows (see
    Account below) and every other table's account_id foreign key point
    to. Exists only because a foreign key needs a non-versioned target —
    `accounts.account_id` is not unique on its own once a second version
    of an account exists.

    external_id is the source system's stable ID for this account (e.g.
    the product DB's account primary key) — ingestion adapters (/ingest)
    upsert by this, not by name, so a nightly sync never creates a
    duplicate account for the same source row."""

    __tablename__ = "account_identities"

    external_id: Mapped[str | None] = mapped_column(
        String, unique=True, nullable=True, index=True
    )


class Account(Base, UUIDPrimaryKey, TemporalMixin, CreatedAtMixin):
    """Versioned account attributes. One row per version; valid_to IS NULL
    marks the current version (enforced by the partial unique index below).
    A new row is inserted and the prior one closed out (valid_to set)
    whenever a mutable dimension changes — tier, quadrant, commercial
    model, commitment terms — so retrospective scoring (BUILD-PROMPT.md
    §10) can answer what the system believed at any past point in time."""

    __tablename__ = "accounts"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account_identities.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    contract_start: Mapped[date] = mapped_column(Date, nullable=False)
    term: Mapped[str] = mapped_column(String, nullable=False)
    plan: Mapped[str | None] = mapped_column(String, nullable=True)
    commercial_model: Mapped[CommercialModel] = mapped_column(
        pg_enum(CommercialModel, "commercial_model"), nullable=False
    )
    committed_volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commitment_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Synthetic renewal-touch anchor for ad-hoc/monthly accounts that have
    # no real commitment_end to count down from (see the implementation
    # plan's "renewal trigger" resolution). Defaults to a quarterly cadence
    # from contract_start; Play 3 (Phase 3+) fires 20 days before whichever
    # of this or a real commitment_end applies.
    next_review_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    tier: Mapped[Tier] = mapped_column(pg_enum(Tier, "tier"), nullable=False)
    quadrant: Mapped[Quadrant] = mapped_column(
        pg_enum(Quadrant, "quadrant"), nullable=False
    )
    potential_departments: Mapped[int | None] = mapped_column(Integer, nullable=True)
    potential_creators_per_dept: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    potential_campaigns_per_creator: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    __table_args__ = (
        Index(
            "ux_accounts_current",
            "account_id",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
        ),
    )


class Department(Base, UUIDPrimaryKey, CreatedAtMixin):
    __tablename__ = "departments"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("account_identities.id"), nullable=False, index=True
    )
    external_id: Mapped[str | None] = mapped_column(
        String, unique=True, nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    first_campaign_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
