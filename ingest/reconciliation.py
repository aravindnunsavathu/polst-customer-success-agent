"""Nightly billing reconciliation (BUILD-PROMPT.md §4): the campaign count
this system reports must equal what Finance bills, or every conversation
about volume becomes a debate about the data. Pure query + diff — no
opinion about what to do with a discrepancy beyond reporting it; that's
the job entrypoint's concern (see ingest/jobs/reconcile_billing.py)."""

import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import BillingPeriod, Campaign


@dataclass(frozen=True)
class ReconciliationDiscrepancy:
    account_id: uuid.UUID
    period: date
    computed_count: int
    billed_count: int


def run_reconciliation(session: Session) -> list[ReconciliationDiscrepancy]:
    # Bucketed in Python, not SQL date_trunc — matches exactly how
    # seed/builder.py buckets billing periods when generating synthetic
    # data, and sidesteps a Postgres GROUP BY gotcha where two bind
    # parameters carrying the same value ('month') aren't recognized as
    # the same GROUP BY expression.
    rows = session.execute(
        select(Campaign.account_id, Campaign.created_at).where(Campaign.billable.is_(True))
    ).all()
    computed = Counter((row.account_id, row.created_at.date().replace(day=1)) for row in rows)

    billed_rows = session.execute(
        select(
            BillingPeriod.account_id, BillingPeriod.period, BillingPeriod.billable_campaign_count
        )
    ).all()
    billed = {(row.account_id, row.period): row.billable_campaign_count for row in billed_rows}

    discrepancies = []
    for key in set(computed) | set(billed):
        computed_count = computed.get(key, 0)
        billed_count = billed.get(key, 0)
        if computed_count != billed_count:
            discrepancies.append(
                ReconciliationDiscrepancy(
                    account_id=key[0],
                    period=key[1],
                    computed_count=computed_count,
                    billed_count=billed_count,
                )
            )
    return sorted(discrepancies, key=lambda d: (str(d.account_id), d.period))
