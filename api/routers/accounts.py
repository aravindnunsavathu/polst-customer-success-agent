"""Read-only Portfolio and Account endpoints (BUILD-PROMPT.md §8, Phase
2's "read-only" scope — nothing here writes anything). Queries the
canonical schema directly; no agent, no LLM, no write path."""

import uuid
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.schemas import (
    AccountDetail,
    AccountPlanOut,
    AccountSummary,
    DepartmentVolumeOut,
    HealthScoreSummary,
    PlayRunOut,
    SignalOut,
    StakeholderOut,
    ValueDocOut,
)
from core.db import get_db
from core.jobs.fetch import fetch_campaign_facts
from core.models import (
    Account,
    AccountIdentity,
    AccountPlan,
    Campaign,
    Department,
    HealthScore,
    PlayRun,
    Signal,
    Stakeholder,
    ValueDoc,
)
from metrics.derived import REVENUE_PER_DEPARTMENT_PROXY, departments_live
from signals.orchestrator import priority_score

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _health_score_summary(hs: HealthScore) -> HealthScoreSummary:
    return HealthScoreSummary(
        scored_at=hs.scored_at,
        final_score=hs.final_score,
        composite_score=hs.composite_score,
        band=hs.band.value if hs.band else None,
        volume_trajectory_score=hs.volume_trajectory_score,
        breadth_score=hs.breadth_score,
        value_realisation_score=hs.value_realisation_score,
        campaign_quality_score=hs.campaign_quality_score,
        relationship_coverage_score=hs.relationship_coverage_score,
        sentiment_friction_score=hs.sentiment_friction_score,
        applied_overrides=hs.applied_overrides or [],
        null_reasons=hs.null_reasons or {},
        model_version=hs.model_version,
    )


def _trend(latest: HealthScore | None, previous: HealthScore | None) -> str | None:
    if latest is None or previous is None:
        return None
    if latest.final_score is None or previous.final_score is None:
        return None
    if latest.final_score > previous.final_score:
        return "up"
    if latest.final_score < previous.final_score:
        return "down"
    return "flat"


def _latest_two_scores(db: Session, account_id) -> list[HealthScore]:
    return list(
        db.execute(
            select(HealthScore)
            .where(HealthScore.account_id == account_id)
            .order_by(HealthScore.scored_at.desc())
            .limit(2)
        ).scalars()
    )


def _open_signal_counts(db: Session) -> dict:
    from sqlalchemy import func

    rows = db.execute(
        select(Signal.account_id, func.count(Signal.id)).where(Signal.resolved_at.is_(None)).group_by(Signal.account_id)
    ).all()
    return {account_id: count for account_id, count in rows}


@router.get("", response_model=list[AccountSummary])
def list_accounts(db: Session = Depends(get_db)) -> list[AccountSummary]:
    accounts = db.execute(select(Account).where(Account.valid_to.is_(None))).scalars().all()
    open_counts = _open_signal_counts(db)
    out = []
    for account in accounts:
        scores = _latest_two_scores(db, account.account_id)
        latest = scores[0] if scores else None
        previous = scores[1] if len(scores) > 1 else None
        out.append(
            AccountSummary(
                account_id=str(account.account_id),
                name=account.name,
                tier=account.tier.value,
                quadrant=account.quadrant.value,
                commercial_model=account.commercial_model.value,
                latest_score=_health_score_summary(latest) if latest else None,
                trend=_trend(latest, previous),
                next_review_date=account.next_review_date,
                open_signal_count=open_counts.get(account.account_id, 0),
            )
        )
    return out


@router.get("/{account_id}", response_model=AccountDetail)
def get_account(account_id: str, db: Session = Depends(get_db)) -> AccountDetail:
    try:
        identity_id = uuid.UUID(account_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="account_id must be a UUID")

    identity = db.get(AccountIdentity, identity_id)
    if identity is None:
        raise HTTPException(status_code=404, detail="account not found")

    account = db.execute(
        select(Account).where(Account.account_id == identity.id, Account.valid_to.is_(None))
    ).scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="account has no current version")

    health_history = list(
        db.execute(
            select(HealthScore)
            .where(HealthScore.account_id == identity.id)
            .order_by(HealthScore.scored_at.desc())
        ).scalars()
    )
    latest = health_history[0] if health_history else None
    previous = health_history[1] if len(health_history) > 1 else None

    stakeholders = db.execute(
        select(Stakeholder).where(
            Stakeholder.account_id == identity.id, Stakeholder.valid_to.is_(None)
        )
    ).scalars().all()

    departments = db.execute(
        select(Department).where(Department.account_id == identity.id)
    ).scalars().all()
    campaigns = db.execute(
        select(Campaign).where(Campaign.account_id == identity.id)
    ).scalars().all()

    as_of = date.today()
    last_90_start = as_of - timedelta(days=89)
    prior_90_start = as_of - timedelta(days=179)
    prior_90_end = as_of - timedelta(days=90)

    dept_rows = []
    for dept in departments:
        dept_campaigns = [c for c in campaigns if c.department_id == dept.id and c.billable]
        last_90 = [c for c in dept_campaigns if last_90_start <= c.created_at.date() <= as_of]
        prior_90 = [
            c for c in dept_campaigns if prior_90_start <= c.created_at.date() <= prior_90_end
        ]
        dept_rows.append(
            DepartmentVolumeOut(
                department_id=str(dept.id),
                name=dept.name,
                live_last_90d=len(last_90) > 0,
                active_creators_last_90d=len({c.creator_user_id for c in last_90}),
                campaigns_last_90d=len(last_90),
                campaigns_prior_90d=len(prior_90),
                first_campaign_at=dept.first_campaign_at,
            )
        )

    value_docs = db.execute(
        select(ValueDoc).where(ValueDoc.account_id == identity.id).order_by(ValueDoc.created_at.desc())
    ).scalars().all()

    open_signals = db.execute(
        select(Signal)
        .where(Signal.account_id == identity.id, Signal.resolved_at.is_(None))
        .order_by(Signal.fired_at.desc())
    ).scalars().all()
    account_revenue = departments_live(fetch_campaign_facts(db, identity.id), as_of) * REVENUE_PER_DEPARTMENT_PROXY
    signal_priority = priority_score(account.tier.value, len(open_signals), account_revenue)
    open_signal_rows = [
        SignalOut(
            id=str(s.id), account_id=str(identity.id), account_name=account.name,
            type=s.type, reason=s.reason, evidence=s.evidence or {},
            severity=s.severity.value, fired_at=s.fired_at, sla_due_at=s.sla_due_at,
            priority_score=signal_priority,
        )
        for s in open_signals
    ]

    play_runs = db.execute(
        select(PlayRun).where(PlayRun.account_id == identity.id).order_by(PlayRun.opened_at.desc())
    ).scalars().all()
    play_run_rows = [
        PlayRunOut(
            id=str(p.id), play=p.play.value, opened_at=p.opened_at, closed_at=p.closed_at,
            outcome=p.outcome, cause_classification=p.cause_classification,
        )
        for p in play_runs
    ]

    plan = db.execute(
        select(AccountPlan)
        .where(AccountPlan.account_id == identity.id)
        .order_by(AccountPlan.last_refreshed.desc())
        .limit(1)
    ).scalar_one_or_none()

    return AccountDetail(
        account_id=str(identity.id),
        name=account.name,
        tier=account.tier.value,
        quadrant=account.quadrant.value,
        commercial_model=account.commercial_model.value,
        contract_start=account.contract_start,
        committed_volume=account.committed_volume,
        commitment_end=account.commitment_end,
        next_review_date=account.next_review_date,
        potential_departments=account.potential_departments,
        latest_score=_health_score_summary(latest) if latest else None,
        health_history=[_health_score_summary(hs) for hs in health_history],
        stakeholders=[
            StakeholderOut(
                name=s.name,
                role=s.role,
                type=s.type.value,
                relationship_strength=s.relationship_strength.value,
                last_contact_at=s.last_contact_at,
                departed_at=s.departed_at,
                reference_willing=s.reference_willing,
            )
            for s in stakeholders
        ],
        departments=dept_rows,
        value_docs=[
            ValueDocOut(
                result=v.result, metric=v.metric, confirmed_by=v.confirmed_by,
                confirmed_at=v.confirmed_at, created_at=v.created_at,
            )
            for v in value_docs
        ],
        account_plan=AccountPlanOut(
            stated_objective=plan.stated_objective if plan else None,
            stated_objective_missing=not (plan and plan.stated_objective),
            how_measured=plan.how_measured if plan else None,
            baseline=plan.baseline if plan else None,
            top_risk=plan.top_risk if plan else None,
            top_opportunity=plan.top_opportunity if plan else None,
            last_refreshed=plan.last_refreshed if plan else None,
        ),
        open_signals=open_signal_rows,
        play_runs=play_run_rows,
    )
