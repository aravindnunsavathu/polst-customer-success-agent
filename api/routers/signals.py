"""Open-signals endpoint — the portfolio-wide worklist (BUILD-PROMPT.md
§7's "priority by tier x severity x revenue at risk"), read-only."""

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.schemas import SignalOut
from core.db import get_db
from core.jobs.fetch import fetch_campaign_facts
from core.models import Account, Signal
from metrics.derived import REVENUE_PER_DEPARTMENT_PROXY, departments_live
from signals.orchestrator import priority_score

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("", response_model=list[SignalOut])
def list_open_signals(db: Session = Depends(get_db)) -> list[SignalOut]:
    rows = db.execute(
        select(Signal, Account)
        .join(Account, Account.account_id == Signal.account_id)
        .where(Signal.resolved_at.is_(None), Account.valid_to.is_(None))
    ).all()

    # Group by account once so priority_score's revenue proxy and open
    # count aren't recomputed per-signal for accounts with several open.
    by_account: dict = {}
    for signal, account in rows:
        by_account.setdefault(account.account_id, {"account": account, "signals": []})
        by_account[account.account_id]["signals"].append(signal)

    out = []
    for account_id, group in by_account.items():
        account = group["account"]
        campaigns = fetch_campaign_facts(db, account_id)
        revenue = departments_live(campaigns, date.today()) * REVENUE_PER_DEPARTMENT_PROXY
        score = priority_score(account.tier.value, len(group["signals"]), revenue)
        for signal in group["signals"]:
            out.append(
                SignalOut(
                    id=str(signal.id),
                    account_id=str(account_id),
                    account_name=account.name,
                    type=signal.type,
                    reason=signal.reason,
                    evidence=signal.evidence or {},
                    severity=signal.severity.value,
                    fired_at=signal.fired_at,
                    sla_due_at=signal.sla_due_at,
                    priority_score=score,
                )
            )

    out.sort(key=lambda s: s.priority_score, reverse=True)
    return out
