"""Nightly trigger evaluation (BUILD-PROMPT.md §6): the bridge between
real Postgres and the pure trigger/orchestrator/coverage logic in
/signals. Entrypoint: `python -m signals.jobs.evaluate_triggers`."""

import sys
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import SessionLocal
from core.enums import PlayType, SignalSeverity
from core.jobs.fetch import (
    account_context,
    fetch_campaign_facts,
    fetch_department_facts,
    fetch_stakeholder_facts,
    fetch_user_facts,
    fetch_value_doc_facts,
)
from core.models import Account, CoverageElevation, HealthScore, PlayRun, Signal
from metrics.config import default_config
from signals import coverage
from signals.orchestrator import decide
from signals.sla import sla_due_at
from signals.triggers import (
    trigger_champion_departure,
    trigger_commitment_pace_low,
    trigger_contract_signed,
    trigger_dept_zero_creators,
    trigger_expansion_candidate,
    trigger_renewal_window,
    trigger_single_creator_inactive_14d,
    trigger_volume_ratio_below_085,
    trigger_zero_campaigns_30d,
)


def _latest_health_score(session: Session, account_id) -> HealthScore | None:
    return session.execute(
        select(HealthScore)
        .where(HealthScore.account_id == account_id)
        .order_by(HealthScore.scored_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _open_signal_types(session: Session, account_id) -> set[str]:
    rows = session.execute(
        select(Signal.type).where(Signal.account_id == account_id, Signal.resolved_at.is_(None))
    ).scalars().all()
    return set(rows)


def _has_open_play_run(session: Session, account_id) -> bool:
    return (
        session.execute(
            select(PlayRun.id).where(PlayRun.account_id == account_id, PlayRun.closed_at.is_(None)).limit(1)
        ).scalar_one_or_none()
        is not None
    )


def _active_coverage_elevations(session: Session, account_id) -> list[CoverageElevation]:
    return session.execute(
        select(CoverageElevation).where(
            CoverageElevation.account_id == account_id, CoverageElevation.resolved_at.is_(None)
        )
    ).scalars().all()


def evaluate_decay_and_play_candidates(session: Session, account: Account, as_of: date, config):
    campaigns = fetch_campaign_facts(session, account.account_id)
    departments = fetch_department_facts(session, account.account_id)
    users = fetch_user_facts(session, account.account_id)
    stakeholders = fetch_stakeholder_facts(session, account.account_id)
    value_docs = fetch_value_doc_facts(session, account.account_id)
    ctx = account_context(account)
    consumed = sum(1 for c in campaigns if c.billable)
    band = _latest_health_score(session, account.account_id)
    band_value = band.band.value if band and band.band else None

    candidates = []
    single = trigger_volume_ratio_below_085(campaigns, ctx.contract_start, as_of, config)
    if single:
        candidates.append(single)
    single = trigger_zero_campaigns_30d(campaigns, as_of)
    if single:
        candidates.append(single)
    single = trigger_commitment_pace_low(consumed, ctx, as_of)
    if single:
        candidates.append(single)
    single = trigger_champion_departure(stakeholders)
    if single:
        candidates.append(single)
    candidates.extend(trigger_dept_zero_creators(departments, users, as_of))
    candidates.extend(trigger_single_creator_inactive_14d(campaigns, users, as_of))

    single = trigger_contract_signed(ctx, as_of)
    if single:
        candidates.append(single)
    single = trigger_renewal_window(ctx, as_of, account.next_review_date)
    if single:
        candidates.append(single)
    single = trigger_expansion_candidate(campaigns, value_docs, ctx, band_value, as_of)
    if single:
        candidates.append(single)

    return candidates, band_value, departments, stakeholders


def process_account(session: Session, account: Account, as_of: date, config) -> dict:
    candidates, band_value, departments, stakeholders = evaluate_decay_and_play_candidates(
        session, account, as_of, config
    )

    already_open = _open_signal_types(session, account.account_id)
    has_open_play = _has_open_play_run(session, account.account_id)
    decision = decide(candidates, already_open, has_open_play)

    now = datetime.now(timezone.utc)
    tier = account.tier.value
    for candidate in decision.new_signals:
        session.add(
            Signal(
                id=uuid.uuid4(),
                account_id=account.account_id,
                type=candidate.type,
                reason=candidate.reason,
                evidence=candidate.evidence,
                severity=SignalSeverity(tier),
                fired_at=now,
                sla_due_at=sla_due_at(tier, now),
            )
        )

    if decision.play_to_open:
        session.add(
            PlayRun(
                id=uuid.uuid4(),
                account_id=account.account_id,
                play=PlayType(decision.play_to_open),
                opened_at=now,
                exit_test_results={},
            )
        )

    # --- Coverage elevations: open new ones, close out expired/resolved ones ---
    active = _active_coverage_elevations(session, account.account_id)
    active_triggers = {e.trigger for e in active}

    def _maybe_open(candidate, elevated_at=now):
        if candidate is None or candidate.trigger in active_triggers:
            return
        expires_at = (
            elevated_at + timedelta(days=candidate.duration_days)
            if candidate.duration_days is not None
            else None
        )
        session.add(
            CoverageElevation(
                id=uuid.uuid4(),
                account_id=account.account_id,
                trigger=candidate.trigger,
                elevated_at=elevated_at,
                expires_at=expires_at,
            )
        )

    _maybe_open(coverage.check_first_90_days(tier, account.contract_start, as_of))
    _maybe_open(coverage.check_health_critical(band_value))
    _maybe_open(coverage.check_champion_departure(stakeholders))
    _maybe_open(coverage.check_new_department_launching(departments, as_of))
    _maybe_open(coverage.check_renewal_within_90_days(account.commitment_end, account.next_review_date, as_of))
    _maybe_open(coverage.check_reference_candidate(band_value, stakeholders))

    closed = 0
    for elevation in active:
        if elevation.expires_at is not None and now >= elevation.expires_at:
            elevation.resolved_at = now
            elevation.resolution = "expired"
            closed += 1
        elif elevation.trigger == "health_critical" and band_value != "critical":
            elevation.resolved_at = now
            elevation.resolution = "health_no_longer_critical"
            closed += 1

    return {
        "new_signals": len(decision.new_signals),
        "play_opened": decision.play_to_open,
        "coverage_closed": closed,
    }


def run(as_of: date | None = None) -> int:
    as_of = as_of or date.today()
    config = default_config()
    session = SessionLocal()
    try:
        accounts = session.execute(select(Account).where(Account.valid_to.is_(None))).scalars().all()
        totals = {"new_signals": 0, "plays_opened": 0, "coverage_closed": 0}
        play_counts: dict[str, int] = {}
        for account in accounts:
            result = process_account(session, account, as_of, config)
            totals["new_signals"] += result["new_signals"]
            totals["coverage_closed"] += result["coverage_closed"]
            if result["play_opened"]:
                totals["plays_opened"] += 1
                play_counts[result["play_opened"]] = play_counts.get(result["play_opened"], 0) + 1
        session.commit()
        print(
            f"Evaluated {len(accounts)} accounts: {totals['new_signals']} new signals, "
            f"{totals['plays_opened']} play_runs opened {play_counts}, "
            f"{totals['coverage_closed']} coverage elevations closed."
        )
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(run())
