import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base
from core.enums import ReportType
from core.models.mixins import CreatedAtMixin, UUIDPrimaryKey, pg_enum


class PortfolioReport(Base, UUIDPrimaryKey, CreatedAtMixin):
    """Portfolio Analyst (weekly/bi-weekly/monthly/quarterly reviews) and
    VoC Router (ranked friction list) outputs — both non-customer-facing,
    "writes to the console, drafts nothing outbound" (BUILD-PROMPT.md
    §7). `data` holds the deterministic aggregates the report is built
    from; `narrative` is the LLM-synthesized write-up over that data —
    nullable because a re-run of the calibration harness, say, may be
    pure numbers with no synthesis step at all."""

    __tablename__ = "portfolio_reports"

    report_type: Mapped[ReportType] = mapped_column(
        pg_enum(ReportType, "report_type"), nullable=False, index=True
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    narrative: Mapped[str | None] = mapped_column(Text, nullable=True)
