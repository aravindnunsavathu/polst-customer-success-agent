from datetime import date, datetime, time, timedelta

from agents.renewal.diagnosis import assess_renewal_readiness
from signals.types import AccountContext, CampaignFact, StakeholderFact, ValueDocFact

AS_OF = date(2026, 9, 5)


def _campaign(dept, creator, created_on: date):
    created = datetime.combine(created_on, time(10, 0))
    return CampaignFact(id=f"{dept}-{creator}-{created_on}", department_id=dept, creator_id=creator,
                          created_at=created, launched_at=created)


def _account(committed_volume=None, commitment_end=None):
    return AccountContext(
        contract_start=date(2025, 1, 1),
        commercial_model="committed" if committed_volume else "ad_hoc",
        committed_volume=committed_volume, commitment_end=commitment_end, potential_departments=3,
    )


def test_stale_value_doc_is_flagged_as_a_gap():
    readiness = assess_renewal_readiness(
        value_docs=[ValueDocFact(created_at=datetime(2025, 1, 1), confirmed_at=datetime(2025, 6, 1))],
        consumed=0, campaigns=[], stakeholders=[], account=_account(), as_of=AS_OF,
    )
    assert readiness.value_doc_current is False
    assert "value_doc" in readiness.gaps[0]


def test_recent_confirmed_value_doc_passes():
    readiness = assess_renewal_readiness(
        value_docs=[ValueDocFact(created_at=datetime(2026, 1, 1), confirmed_at=datetime(2026, 8, 1))],
        consumed=0, campaigns=[], stakeholders=[], account=_account(), as_of=AS_OF,
    )
    assert readiness.value_doc_current is True


def test_ad_hoc_account_has_no_utilization_status():
    readiness = assess_renewal_readiness(
        value_docs=[], consumed=0, campaigns=[], stakeholders=[], account=_account(), as_of=AS_OF,
    )
    assert readiness.utilization_status is None


def test_oversold_at_signing_when_utilization_low_from_the_start():
    account = _account(committed_volume=1000, commitment_end=AS_OF + timedelta(days=20))
    readiness = assess_renewal_readiness(
        value_docs=[], consumed=50, campaigns=[], stakeholders=[], account=account, as_of=AS_OF,
    )
    assert readiness.utilization_status == "oversold_at_signing"
    assert any("utilization" in g for g in readiness.gaps)


def test_decay_related_when_utilization_low_due_to_a_recent_decline():
    account = _account(committed_volume=200, commitment_end=AS_OF + timedelta(days=20))
    # heavy activity in the prior-90d window, nothing in the last 90d -> a recent decline
    campaigns = [_campaign("d1", "u1", AS_OF - timedelta(days=d)) for d in range(95, 179, 3)]
    readiness = assess_renewal_readiness(
        value_docs=[], consumed=100, campaigns=campaigns, stakeholders=[], account=account, as_of=AS_OF,
    )
    assert readiness.utilization_status == "decay_related"


def test_on_pace_utilization_is_not_a_gap():
    account = _account(committed_volume=100, commitment_end=AS_OF + timedelta(days=20))
    readiness = assess_renewal_readiness(
        value_docs=[], consumed=95, campaigns=[], stakeholders=[], account=account, as_of=AS_OF,
    )
    assert readiness.utilization_status == "on_pace"
    assert not any("utilization" in g for g in readiness.gaps)


def test_missing_economic_buyer_is_a_gap():
    readiness = assess_renewal_readiness(
        value_docs=[], consumed=0, campaigns=[], stakeholders=[], account=_account(), as_of=AS_OF,
    )
    assert readiness.economic_buyer_identified is False
    assert "no_economic_buyer_identified" in readiness.gaps


def test_exec_sponsor_engaged_this_quarter_is_detected():
    stakeholders = [StakeholderFact(type="exec_sponsor", last_contact_at=datetime(2026, 8, 20), departed_at=None)]
    readiness = assess_renewal_readiness(
        value_docs=[], consumed=0, campaigns=[], stakeholders=stakeholders, account=_account(), as_of=AS_OF,
    )
    assert readiness.exec_sponsor_engaged_this_quarter is True


def test_exec_sponsor_stale_contact_is_not_engaged():
    stakeholders = [StakeholderFact(type="exec_sponsor", last_contact_at=datetime(2025, 1, 1), departed_at=None)]
    readiness = assess_renewal_readiness(
        value_docs=[], consumed=0, campaigns=[], stakeholders=stakeholders, account=_account(), as_of=AS_OF,
    )
    assert readiness.exec_sponsor_engaged_this_quarter is False
    assert "exec_sponsor_not_engaged_this_quarter" in readiness.gaps
