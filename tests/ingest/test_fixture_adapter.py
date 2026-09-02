from pathlib import Path

from sqlalchemy import select

from core.enums import Tier
from core.models import Account, AccountIdentity, Campaign, Department
from ingest.fixture_adapter import FixtureAdapter
from ingest.loader import load

FIXTURE = Path(__file__).parent.parent / "fixtures" / "product_export_sample.json"


def test_fixture_adapter_parses_normalized_records():
    adapter = FixtureAdapter(FIXTURE)
    accounts = list(adapter.fetch_accounts())
    campaigns = list(adapter.fetch_campaigns())
    assert len(accounts) == 1
    assert accounts[0].external_id == "acct-001"
    assert len(campaigns) == 3


def test_load_creates_canonical_rows(db_session):
    summary = load(FixtureAdapter(FIXTURE), db_session)

    assert summary.accounts_created == 1
    assert summary.departments_created == 2
    assert summary.users_created == 2
    assert summary.campaigns_created == 3
    assert summary.billing_periods_created == 1

    identity = db_session.execute(
        select(AccountIdentity).where(AccountIdentity.external_id == "acct-001")
    ).scalar_one()
    account = db_session.execute(
        select(Account).where(Account.account_id == identity.id, Account.valid_to.is_(None))
    ).scalar_one()
    assert account.name == "Northfield Health"
    assert account.tier == Tier.T3  # ingestion never sets CS judgment fields — defaults apply

    dept = db_session.execute(
        select(Department).where(Department.external_id == "dept-001")
    ).scalar_one()
    assert dept.first_campaign_at is not None

    campaign = db_session.execute(
        select(Campaign).where(Campaign.external_id == "camp-002")
    ).scalar_one()
    assert campaign.launched_at is None  # abandoned campaign, per the fixture


def test_load_is_idempotent(db_session):
    load(FixtureAdapter(FIXTURE), db_session)
    second = load(FixtureAdapter(FIXTURE), db_session)

    assert second.accounts_created == 0
    assert second.departments_created == 0
    assert second.users_created == 0
    assert second.campaigns_created == 0
    assert second.billing_periods_created == 0

    account_count = db_session.execute(select(AccountIdentity)).scalars().all()
    assert len(account_count) == 1


def test_changed_account_field_versions_instead_of_overwriting(db_session, tmp_path):
    load(FixtureAdapter(FIXTURE), db_session)

    renamed = tmp_path / "renamed.json"
    renamed.write_text(FIXTURE.read_text().replace("Northfield Health", "Northfield Health System"))
    summary = load(FixtureAdapter(renamed), db_session)

    assert summary.accounts_versioned == 1
    assert summary.accounts_created == 0

    identity = db_session.execute(
        select(AccountIdentity).where(AccountIdentity.external_id == "acct-001")
    ).scalar_one()
    versions = db_session.execute(
        select(Account).where(Account.account_id == identity.id).order_by(Account.valid_from)
    ).scalars().all()

    assert len(versions) == 2
    assert versions[0].name == "Northfield Health"
    assert versions[0].valid_to is not None
    assert versions[1].name == "Northfield Health System"
    assert versions[1].valid_to is None
