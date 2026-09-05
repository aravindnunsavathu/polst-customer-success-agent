"""CLI entrypoint: `python -m seed.cli [--reset] [--seed N]`. This is the
"one config flag" §13 refers to for switching the app onto synthetic
data — everything upstream of this module is pure and DB-free; this is
the one place that opens a connection and writes."""

import argparse
import sys

from sqlalchemy import text

from core.db import SessionLocal
from core.models import (
    Account,
    AccountIdentity,
    AccountPlan,
    Action,
    BillingPeriod,
    Campaign,
    CampaignOutcome,
    CoverageElevation,
    Department,
    FeedbackItem,
    HealthScore,
    PlayRun,
    ProductError,
    Signal,
    Stakeholder,
    User,
    UserEvent,
    ValueDoc,
)
from seed.generator import generate_portfolio

# Child-to-parent order matters for readability only — TRUNCATE ... CASCADE
# resolves the actual dependency order regardless.
ALL_TABLES = [
    Action, PlayRun, Signal, CoverageElevation, HealthScore, FeedbackItem, ValueDoc,
    AccountPlan, Stakeholder, ProductError, UserEvent, CampaignOutcome, Campaign,
    BillingPeriod, User, Department, Account, AccountIdentity,
]

# Parent-to-child order — this DOES matter. None of these models declare
# an ORM relationship() to each other (deliberately, to keep the seeder a
# plain object graph), so SQLAlchemy's unit-of-work has no way to infer
# that e.g. account_identities must be inserted before accounts. Flushing
# level by level makes each FK target exist before it's referenced.
INSERT_ORDER = [
    AccountIdentity,
    Account,
    Department,
    Stakeholder,
    AccountPlan,
    ValueDoc,
    BillingPeriod,
    User,
    Campaign,
    UserEvent,
    CampaignOutcome,
]


def reset(session) -> None:
    table_names = ", ".join(m.__tablename__ for m in ALL_TABLES)
    session.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
    session.commit()


def write_portfolio(session, objects: list) -> None:
    for cls in INSERT_ORDER:
        batch = [o for o in objects if isinstance(o, cls)]
        if batch:
            session.add_all(batch)
            session.flush()
    session.commit()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the synthetic Polst CS portfolio")
    parser.add_argument("--reset", action="store_true", help="Truncate existing data first")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed (default 42)")
    args = parser.parse_args(argv)

    session = SessionLocal()
    try:
        if args.reset:
            reset(session)
        objects = generate_portfolio(seed=args.seed)
        write_portfolio(session, objects)

        n_accounts = sum(1 for o in objects if isinstance(o, Account))
        n_campaigns = sum(1 for o in objects if isinstance(o, Campaign))
        n_departments = sum(1 for o in objects if isinstance(o, Department))
        print(
            f"Seeded {n_accounts} accounts, {n_departments} departments, "
            f"{n_campaigns} campaigns ({len(objects)} rows total)."
        )
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
