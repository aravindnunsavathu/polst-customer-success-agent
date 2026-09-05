"""Read-only endpoints for the Portfolio Analyst's four cadenced reviews
and the VoC Router's ranked list (BUILD-PROMPT.md §7 Phase 7). Both
"write to the console, draft nothing outbound" — there is no approval
queue here, just a read path onto what's already in `portfolio_reports`.

No console page consumes this yet (matching the precedent set by
Phases 4-6: the console stayed at its Phase 3 shape while the agent
layer grew) — this is the read path a future Calibration/Reports screen
would call."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.schemas import PortfolioReportOut
from core.db import get_db
from core.enums import ReportType
from core.models import PortfolioReport

router = APIRouter(prefix="/reports", tags=["reports"])


def _to_out(report: PortfolioReport) -> PortfolioReportOut:
    return PortfolioReportOut(
        id=str(report.id),
        report_type=report.report_type.value,
        period_start=report.period_start,
        period_end=report.period_end,
        generated_at=report.generated_at,
        data=report.data or {},
        narrative=report.narrative,
    )


@router.get("", response_model=list[PortfolioReportOut])
def list_reports(type: str | None = None, db: Session = Depends(get_db)) -> list[PortfolioReportOut]:
    query = select(PortfolioReport)
    if type:
        try:
            query = query.where(PortfolioReport.report_type == ReportType(type))
        except ValueError:
            valid = ", ".join(t.value for t in ReportType)
            raise HTTPException(status_code=400, detail=f"type must be one of: {valid}")
    reports = db.execute(query.order_by(PortfolioReport.generated_at.desc())).scalars().all()
    return [_to_out(r) for r in reports]


@router.get("/{report_id}", response_model=PortfolioReportOut)
def get_report(report_id: str, db: Session = Depends(get_db)) -> PortfolioReportOut:
    try:
        report_uuid = uuid.UUID(report_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="report_id must be a UUID")
    report = db.get(PortfolioReport, report_uuid)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    return _to_out(report)
