from pathlib import Path

from sqlalchemy import select, update

from core.models import BillingPeriod
from ingest.fixture_adapter import FixtureAdapter
from ingest.loader import load
from ingest.reconciliation import run_reconciliation

FIXTURE = Path(__file__).parent.parent / "fixtures" / "product_export_sample.json"


def test_no_discrepancies_when_billing_matches_computed(db_session):
    load(FixtureAdapter(FIXTURE), db_session)
    assert run_reconciliation(db_session) == []


def test_detects_a_deliberate_mismatch(db_session):
    load(FixtureAdapter(FIXTURE), db_session)

    # Corrupt the billed count so it no longer matches the 3 campaigns
    # actually recorded for that account/period.
    db_session.execute(update(BillingPeriod).values(billable_campaign_count=99))
    db_session.commit()

    discrepancies = run_reconciliation(db_session)

    assert len(discrepancies) == 1
    assert discrepancies[0].computed_count == 3
    assert discrepancies[0].billed_count == 99
