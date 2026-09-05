"""Sales handoff review is a data-completeness check, not a judgment
call (agents/onboarding/handoff.py's docstring) — every case here is
plain input/output, no LLM involved."""

from datetime import datetime

from agents.onboarding.handoff import review_handoff
from core.enums import CommercialModel
from signals.types import AccountContext, DepartmentFact, StakeholderFact, UserFact

COMPLETE_KWARGS = dict(
    stated_objective="Cut new-menu decision cycle from 3 weeks to 4 days",
    stakeholders=[StakeholderFact(type="economic_buyer", last_contact_at=None, departed_at=None)],
    departments=[DepartmentFact(id="d1", created_at=datetime(2026, 1, 1))],
    users=[UserFact(id="u1", department_id="d1", created_at=datetime(2026, 1, 1),
                     last_active_at=None, deactivated_at=None)],
    account=AccountContext(contract_start=datetime(2026, 1, 1).date(), commercial_model="ad_hoc",
                              committed_volume=None, commitment_end=None, potential_departments=2),
)


def test_complete_handoff_is_accepted():
    review = review_handoff(**COMPLETE_KWARGS)
    assert review.accepted is True
    assert review.missing == []


def test_unverifiable_promise_check_is_always_surfaced_even_when_accepted():
    review = review_handoff(**COMPLETE_KWARGS)
    assert "nothing_overpromised_during_sale" in review.unverifiable


def test_missing_stated_objective_is_rejected():
    kwargs = {**COMPLETE_KWARGS, "stated_objective": None}
    review = review_handoff(**kwargs)
    assert review.accepted is False
    assert "stated_business_objective" in review.missing


def test_missing_economic_buyer_is_rejected():
    kwargs = {**COMPLETE_KWARGS, "stakeholders": []}
    review = review_handoff(**kwargs)
    assert "named_economic_buyer" in review.missing


def test_departed_economic_buyer_does_not_count():
    kwargs = {**COMPLETE_KWARGS, "stakeholders": [
        StakeholderFact(type="economic_buyer", last_contact_at=None, departed_at=datetime(2026, 2, 1))
    ]}
    review = review_handoff(**kwargs)
    assert "named_economic_buyer" in review.missing


def test_no_named_creators_is_rejected():
    kwargs = {**COMPLETE_KWARGS, "users": []}
    review = review_handoff(**kwargs)
    assert "named_creators" in review.missing


def test_no_departments_in_scope_is_rejected():
    kwargs = {**COMPLETE_KWARGS, "departments": []}
    review = review_handoff(**kwargs)
    assert "departments_in_scope" in review.missing


def test_committed_account_without_committed_volume_is_rejected():
    account = AccountContext(contract_start=datetime(2026, 1, 1).date(), commercial_model=CommercialModel.COMMITTED.value,
                                committed_volume=None, commitment_end=None, potential_departments=2)
    kwargs = {**COMPLETE_KWARGS, "account": account}
    review = review_handoff(**kwargs)
    assert "commercial_terms" in review.missing


def test_committed_account_with_committed_volume_passes_that_check():
    account = AccountContext(contract_start=datetime(2026, 1, 1).date(), commercial_model=CommercialModel.COMMITTED.value,
                                committed_volume=500, commitment_end=None, potential_departments=2)
    kwargs = {**COMPLETE_KWARGS, "account": account}
    review = review_handoff(**kwargs)
    assert "commercial_terms" not in review.missing


def test_multiple_missing_criteria_are_all_reported():
    review = review_handoff(
        stated_objective=None, stakeholders=[], departments=[], users=[],
        account=AccountContext(contract_start=datetime(2026, 1, 1).date(), commercial_model="ad_hoc",
                                  committed_volume=None, commitment_end=None, potential_departments=2),
    )
    assert set(review.missing) == {
        "stated_business_objective", "named_economic_buyer", "named_creators", "departments_in_scope",
    }
