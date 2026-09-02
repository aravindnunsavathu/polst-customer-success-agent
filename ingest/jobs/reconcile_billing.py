"""Entrypoint: `python -m ingest.jobs.reconcile_billing`. Exits non-zero
on any discrepancy so this can run as a scheduled ECS task (EventBridge
Scheduler, per BUILD-PROMPT.md §11) with a CloudWatch alarm on job
failure — the alarm IS the "raises a blocking alert" from §4."""

import sys

from core.db import SessionLocal
from ingest.reconciliation import run_reconciliation


def main() -> int:
    session = SessionLocal()
    try:
        discrepancies = run_reconciliation(session)
    finally:
        session.close()

    if discrepancies:
        print(f"BLOCKING: {len(discrepancies)} billing reconciliation discrepancies found:")
        for d in discrepancies:
            print(
                f"  account={d.account_id} period={d.period} "
                f"computed={d.computed_count} billed={d.billed_count}"
            )
        return 1

    print("Billing reconciliation clean — computed and billed campaign counts match.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
