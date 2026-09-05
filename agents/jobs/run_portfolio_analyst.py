"""Bridges real Postgres into the Portfolio Analyst. Self-paces: each of
the four report types is generated only once its own cadence has
elapsed since the last one (BUILD-PROMPT.md §7 — weekly/bi-weekly/
monthly/quarterly), not on every invocation. Entrypoint:
`python -m agents.jobs.run_portfolio_analyst`."""

import sys
import uuid
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.llm.config import provider_for
from agents.portfolio_analyst.agent import (
    AccountSnapshot,
    build_at_risk_critical_review,
    build_calibration_input,
    build_monthly_ceo_snapshot,
    build_watch_review,
    report_due,
)
from core.db import SessionLocal
from core.enums import ReportType
from core.jobs.fetch import fetch_campaign_facts, fetch_health_score_history
from core.models import Account, HealthScore, PlayRun, PortfolioReport, Signal
from evals.calibration import (
    RiskEpisode,
    assess_event,
    detect_event,
    detect_risk_episodes,
    false_alarm_rate,
    hit_rate,
    median_lead_time_days,
    surprises,
)
from metrics.derived import REVENUE_PER_DEPARTMENT_PROXY, departments_live


def _latest_report(session: Session, report_type: ReportType) -> PortfolioReport | None:
    return session.execute(
        select(PortfolioReport)
        .where(PortfolioReport.report_type == report_type)
        .order_by(PortfolioReport.generated_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _open_signal_counts(session: Session) -> dict:
    from sqlalchemy import func

    rows = session.execute(
        select(Signal.account_id, func.count(Signal.id)).where(Signal.resolved_at.is_(None)).group_by(Signal.account_id)
    ).all()
    return {account_id: count for account_id, count in rows}


def _latest_health_score(session: Session, account_id) -> HealthScore | None:
    return session.execute(
        select(HealthScore).where(HealthScore.account_id == account_id).order_by(HealthScore.scored_at.desc()).limit(1)
    ).scalar_one_or_none()


def _build_snapshots(session: Session, accounts: list[Account], as_of: date) -> list[AccountSnapshot]:
    open_counts = _open_signal_counts(session)
    snapshots = []
    for account in accounts:
        campaigns = fetch_campaign_facts(session, account.account_id)
        latest = _latest_health_score(session, account.account_id)
        revenue = departments_live(campaigns, as_of) * REVENUE_PER_DEPARTMENT_PROXY
        snapshots.append(AccountSnapshot(
            account_id=str(account.account_id), name=account.name, tier=account.tier.value,
            band=latest.band.value if latest and latest.band else None,
            final_score=latest.final_score if latest else None,
            open_signal_count=open_counts.get(account.account_id, 0),
            revenue_estimate=revenue, contract_start=account.contract_start,
        ))
    return snapshots


def _had_intervention(session: Session, account_id, start: date, end: date) -> bool:
    return session.execute(
        select(PlayRun.id).where(
            PlayRun.account_id == account_id,
            PlayRun.opened_at >= datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc),
            PlayRun.opened_at <= datetime.combine(end, datetime.max.time(), tzinfo=timezone.utc),
        ).limit(1)
    ).scalar_one_or_none() is not None


def _calibration_summary(session: Session, accounts: list[Account], as_of: date) -> dict:
    assessments = []
    episodes = []
    for account in accounts:
        campaigns = fetch_campaign_facts(session, account.account_id)
        history = fetch_health_score_history(session, account.account_id)

        event = detect_event(campaigns, as_of)
        if event is not None:
            event = replace(event, account_id=str(account.account_id))
            assessments.append(assess_event(event, history))

        for candidate in detect_risk_episodes(str(account.account_id), history):
            had_intervention = _had_intervention(
                session, account.account_id, candidate.flagged_at, candidate.recovered_at or as_of,
            )
            episodes.append(RiskEpisode(candidate=candidate, had_intervention=had_intervention))

    hit = hit_rate(assessments)
    false_alarm = false_alarm_rate(episodes)
    lead_time = median_lead_time_days(assessments)
    surprise_list = surprises(assessments)

    return {
        "event_count": len(assessments),
        "hit_rate": hit.value, "hit_rate_null_reason": hit.reason,
        "false_alarm_rate": false_alarm.value, "false_alarm_rate_null_reason": false_alarm.reason,
        "lead_time_days": lead_time.value, "lead_time_null_reason": lead_time.reason,
        "surprises": [
            {"account_id": a.event.account_id, "event_type": a.event.event_type,
             "event_date": a.event.event_date.isoformat(), "band_one_quarter_before": a.band_one_quarter_before,
             "band_two_quarters_before": a.band_two_quarters_before}
            for a in surprise_list
        ],
    }


def run(as_of: date | None = None) -> int:
    as_of = as_of or date.today()
    session = SessionLocal()
    try:
        accounts = session.execute(select(Account).where(Account.valid_to.is_(None))).scalars().all()
        drafter = provider_for("portfolio_analyst_synthesis")
        generated = []

        last_at_risk = _latest_report(session, ReportType.AT_RISK_CRITICAL_REVIEW)
        if report_due(ReportType.AT_RISK_CRITICAL_REVIEW, last_at_risk.generated_at if last_at_risk else None, as_of):
            snapshots = _build_snapshots(session, accounts, as_of)
            draft = build_at_risk_critical_review(snapshots, as_of, drafter)
            session.add(PortfolioReport(
                id=uuid.uuid4(), report_type=draft.report_type, period_start=draft.period_start,
                period_end=draft.period_end, generated_at=datetime.now(timezone.utc),
                data={**draft.data, "llm": draft.llm}, narrative=draft.narrative,
            ))
            generated.append(draft.report_type.value)

        last_watch = _latest_report(session, ReportType.WATCH_REVIEW)
        if report_due(ReportType.WATCH_REVIEW, last_watch.generated_at if last_watch else None, as_of):
            snapshots = _build_snapshots(session, accounts, as_of)
            draft = build_watch_review(snapshots, as_of, drafter)
            session.add(PortfolioReport(
                id=uuid.uuid4(), report_type=draft.report_type, period_start=draft.period_start,
                period_end=draft.period_end, generated_at=datetime.now(timezone.utc),
                data={**draft.data, "llm": draft.llm}, narrative=draft.narrative,
            ))
            generated.append(draft.report_type.value)

        last_monthly = _latest_report(session, ReportType.MONTHLY_CEO_SNAPSHOT)
        if report_due(ReportType.MONTHLY_CEO_SNAPSHOT, last_monthly.generated_at if last_monthly else None, as_of):
            snapshots = _build_snapshots(session, accounts, as_of)
            prior_as_of = as_of - timedelta(days=30)
            current_revenue, prior_revenue = {}, {}
            for account in accounts:
                campaigns = fetch_campaign_facts(session, account.account_id)
                current_revenue[str(account.account_id)] = departments_live(campaigns, as_of) * REVENUE_PER_DEPARTMENT_PROXY
                if account.contract_start <= prior_as_of:
                    prior_revenue[str(account.account_id)] = departments_live(campaigns, prior_as_of) * REVENUE_PER_DEPARTMENT_PROXY
            draft = build_monthly_ceo_snapshot(snapshots, current_revenue, prior_revenue, as_of, drafter)
            session.add(PortfolioReport(
                id=uuid.uuid4(), report_type=draft.report_type, period_start=draft.period_start,
                period_end=draft.period_end, generated_at=datetime.now(timezone.utc),
                data={**draft.data, "llm": draft.llm}, narrative=draft.narrative,
            ))
            generated.append(draft.report_type.value)

        last_calibration = _latest_report(session, ReportType.CALIBRATION_INPUT)
        if report_due(ReportType.CALIBRATION_INPUT, last_calibration.generated_at if last_calibration else None, as_of):
            summary = _calibration_summary(session, accounts, as_of)
            draft = build_calibration_input(summary, as_of, drafter)
            session.add(PortfolioReport(
                id=uuid.uuid4(), report_type=draft.report_type, period_start=draft.period_start,
                period_end=draft.period_end, generated_at=datetime.now(timezone.utc),
                data={**draft.data, "llm": draft.llm}, narrative=draft.narrative,
            ))
            generated.append(draft.report_type.value)

        session.commit()
        print(f"Generated reports: {generated or 'none due'}")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(run())
