"""Stage-transition tests for the Renewal Agent (T-20 readiness -> T-15
value review -> T-10 growth proposal -> T-5 objections -> T+7 debrief),
using FakeLLMProvider for exact-response control, same discipline as
test_decay_agent.py and test_onboarding_agent.py."""

from datetime import date, datetime, time, timedelta

from agents.llm.base import LLMResponse, LLMUsage
from agents.llm.fake import FakeLLMProvider
from agents.renewal.agent import (
    DEBRIEF_DAY,
    GROWTH_PROPOSAL_DAY,
    OBJECTIONS_DAY,
    VALUE_REVIEW_DAY,
    run_renewal_agent,
)
from core.enums import AutonomyLevel
from signals.types import AccountContext, CampaignFact, StakeholderFact, ValueDocFact

AS_OF = date(2026, 9, 5)
FAKE_USAGE = LLMUsage(provider="fake", model="fake", latency_ms=1.0, input_tokens=1, output_tokens=1, cost_usd=0.0)


def _text(s: str) -> LLMResponse:
    return LLMResponse(text=s, parsed=None, usage=FAKE_USAGE)


def _campaign(dept, creator, created_on: date):
    created = datetime.combine(created_on, time(10, 0))
    return CampaignFact(id=f"{dept}-{creator}-{created_on}", department_id=dept, creator_id=creator,
                          created_at=created, launched_at=created)


def _base_kwargs(reference_date, **overrides):
    kwargs = dict(
        campaigns=[],
        value_docs=[ValueDocFact(created_at=datetime(2026, 1, 1), confirmed_at=datetime(2026, 7, 1), confirmed_by="buyer@x.com")],
        stakeholders=[
            StakeholderFact(type="economic_buyer", last_contact_at=datetime(2026, 8, 1), departed_at=None),
            StakeholderFact(type="exec_sponsor", last_contact_at=datetime(2026, 8, 20), departed_at=None),
        ],
        account=AccountContext(contract_start=date(2025, 1, 1), commercial_model="committed",
                                  committed_volume=600, commitment_end=reference_date, potential_departments=3),
        reference_date=reference_date,
        stated_objective="Cut new-menu decision cycle from 3 weeks to 4 days",
        how_measured="Time from concept to go/no-go",
        tier="T2",
        as_of=AS_OF,
        state=None,
        promotion_counts={},
    )
    kwargs.update(overrides)
    return kwargs


def test_readiness_check_runs_first_and_never_closes_the_play():
    kwargs = _base_kwargs(reference_date=AS_OF + timedelta(days=20))
    brief_provider = FakeLLMProvider(responses=[])
    drafter = FakeLLMProvider(responses=[])  # must never be called at this stage

    result = run_renewal_agent(**kwargs, brief_provider=brief_provider, drafter=drafter)

    assert result.stage == "readiness"
    assert result.closes_play_run is False
    assert result.exit_test_results["readiness_checked"] is True
    assert result.actions[0].type == "renewal_readiness_check"


def test_oversold_utilization_creates_a_feedback_item_routed_to_sales():
    """Doc 06: 'if oversold at the point of sale, say so internally —
    that's a Sales-handoff finding, not a CS failure.' Low utilization
    from day one (no recent campaigns at all), not a recent decline."""
    kwargs = _base_kwargs(
        reference_date=AS_OF + timedelta(days=20),
        account=AccountContext(contract_start=date(2025, 1, 1), commercial_model="committed",
                                  committed_volume=1000, commitment_end=AS_OF + timedelta(days=20),
                                  potential_departments=3),
        campaigns=[],  # zero consumption the whole term -> pace 0%, no recent-decline signal either
    )

    result = run_renewal_agent(**kwargs, brief_provider=FakeLLMProvider(), drafter=FakeLLMProvider())

    assert result.feedback_item is not None
    assert result.feedback_item["tag"] == "oversold_commitment"
    assert result.feedback_item["routed_to"] == "Sales"


def test_decay_related_utilization_does_not_create_a_feedback_item():
    """A recent decline (not low utilization since day one) is a Play 2
    matter, not a Sales-handoff finding — no feedback_item should fire."""
    campaigns = [_campaign("d1", "u1", AS_OF - timedelta(days=d)) for d in range(100, 179, 5)]  # only prior-90d activity
    kwargs = _base_kwargs(
        reference_date=AS_OF + timedelta(days=20),
        account=AccountContext(contract_start=date(2025, 1, 1), commercial_model="committed",
                                  committed_volume=1000, commitment_end=AS_OF + timedelta(days=20),
                                  potential_departments=3),
        campaigns=campaigns,
    )

    result = run_renewal_agent(**kwargs, brief_provider=FakeLLMProvider(), drafter=FakeLLMProvider())

    assert result.feedback_item is None


def test_value_review_drafted_once_readiness_is_done_and_day_15_reached():
    state = {"readiness_checked": True, "value_doc_current_at_open": True,
             "reference_date_at_open": (AS_OF + timedelta(days=15)).isoformat(), "committed_volume_at_open": 600}
    kwargs = _base_kwargs(reference_date=AS_OF + timedelta(days=VALUE_REVIEW_DAY), state=state)
    drafter = FakeLLMProvider(responses=[_text("Here's the delta against your baseline.")])

    result = run_renewal_agent(**kwargs, brief_provider=FakeLLMProvider(), drafter=drafter)

    assert result.stage == "value_review"
    assert result.actions[0].type == "renewal_value_review"
    assert result.exit_test_results["value_review_drafted"] is True


def test_value_review_evidence_includes_stated_objective_in_the_json_block():
    state = {"readiness_checked": True, "value_doc_current_at_open": True,
             "reference_date_at_open": (AS_OF + timedelta(days=15)).isoformat(), "committed_volume_at_open": 600}
    kwargs = _base_kwargs(reference_date=AS_OF + timedelta(days=VALUE_REVIEW_DAY), state=state)
    drafter = FakeLLMProvider(responses=[_text("draft")])

    run_renewal_agent(**kwargs, brief_provider=FakeLLMProvider(), drafter=drafter)

    prompt = drafter.calls[0]["prompt"]
    assert '"stated_objective": "Cut new-menu decision cycle from 3 weeks to 4 days"' in prompt


def test_growth_proposal_drafted_at_day_10():
    state = {"readiness_checked": True, "value_doc_current_at_open": True, "value_review_drafted": True,
             "reference_date_at_open": (AS_OF + timedelta(days=10)).isoformat(), "committed_volume_at_open": 600}
    kwargs = _base_kwargs(reference_date=AS_OF + timedelta(days=GROWTH_PROPOSAL_DAY), state=state)
    drafter = FakeLLMProvider(responses=[_text("Growth plan.")])

    result = run_renewal_agent(**kwargs, brief_provider=FakeLLMProvider(), drafter=drafter)

    assert result.stage == "growth_proposal"
    assert result.actions[0].type == "renewal_growth_proposal"


def test_growth_proposal_uses_the_renewal_commercial_proposal_autonomy_row():
    """T1 renewal_commercial_proposal is human_writes per §9 — a compliant
    draft must still never reach auto/draft for T1."""
    state = {"readiness_checked": True, "value_doc_current_at_open": True, "value_review_drafted": True,
             "reference_date_at_open": (AS_OF + timedelta(days=10)).isoformat(), "committed_volume_at_open": 600}
    kwargs = _base_kwargs(
        reference_date=AS_OF + timedelta(days=GROWTH_PROPOSAL_DAY), state=state, tier="T1",
        promotion_counts={"renewal_commercial_proposal": 999},
    )
    drafter = FakeLLMProvider(responses=[_text("Growth plan.")])

    result = run_renewal_agent(**kwargs, brief_provider=FakeLLMProvider(), drafter=drafter)

    assert result.actions[0].autonomy_level == AutonomyLevel.HUMAN_WRITES


def test_objections_drafted_at_day_5():
    state = {"readiness_checked": True, "value_doc_current_at_open": True, "value_review_drafted": True,
             "growth_proposal_drafted": True,
             "reference_date_at_open": (AS_OF + timedelta(days=5)).isoformat(), "committed_volume_at_open": 600}
    kwargs = _base_kwargs(reference_date=AS_OF + timedelta(days=OBJECTIONS_DAY), state=state)
    drafter = FakeLLMProvider(responses=[_text("What would stop this from moving forward?")])

    result = run_renewal_agent(**kwargs, brief_provider=FakeLLMProvider(), drafter=drafter)

    assert result.stage == "objections"
    assert result.actions[0].type == "renewal_objection_check"


def test_debrief_closes_the_play_and_reports_recommitment_secured_when_term_extended():
    """The account's reference date has moved out relative to what it was
    when the play opened -> a real, code-derived recommitment signal."""
    reference_date_at_open = AS_OF - timedelta(days=30)  # the original renewal date this play opened against
    state = {
        "readiness_checked": True, "value_doc_current_at_open": True, "value_review_drafted": True,
        "growth_proposal_drafted": True, "objections_drafted": True,
        "reference_date_at_open": reference_date_at_open.isoformat(), "committed_volume_at_open": 600,
    }
    new_reference_date = reference_date_at_open + timedelta(days=365)  # term was extended a full year
    kwargs = _base_kwargs(
        reference_date=new_reference_date, state=state,
        account=AccountContext(contract_start=date(2025, 1, 1), commercial_model="committed",
                                  committed_volume=700, commitment_end=new_reference_date, potential_departments=3),
    )

    # as_of must be >= DEBRIEF_DAY days past whichever reference_date is passed in
    kwargs["as_of"] = new_reference_date - timedelta(days=DEBRIEF_DAY)

    result = run_renewal_agent(**kwargs, brief_provider=FakeLLMProvider(), drafter=FakeLLMProvider())

    assert result.stage == "debrief"
    assert result.closes_play_run is True
    assert result.outcome == "recommitment_secured"
    assert result.exit_test_results["recommitment_secured_at_or_above_prior_volume"] is True
    assert result.exit_test_results["debrief_logged"] is True


def test_debrief_reports_lost_when_term_not_extended_and_no_campaigns_since():
    reference_date = AS_OF - timedelta(days=5)  # already 5 days past
    state = {
        "readiness_checked": True, "value_doc_current_at_open": True, "value_review_drafted": True,
        "growth_proposal_drafted": True, "objections_drafted": True,
        "reference_date_at_open": reference_date.isoformat(), "committed_volume_at_open": 600,
    }
    kwargs = _base_kwargs(
        reference_date=reference_date, state=state,
        as_of=reference_date + timedelta(days=8),  # 8 days past -> DEBRIEF_DAY (-7) threshold crossed
        campaigns=[],  # nothing at all since the reference date
    )

    result = run_renewal_agent(**kwargs, brief_provider=FakeLLMProvider(), drafter=FakeLLMProvider())

    assert result.outcome == "lost"


def test_debrief_reports_undetermined_when_still_consuming_but_term_not_extended():
    reference_date = AS_OF - timedelta(days=5)
    state = {
        "readiness_checked": True, "value_doc_current_at_open": True, "value_review_drafted": True,
        "growth_proposal_drafted": True, "objections_drafted": True,
        "reference_date_at_open": reference_date.isoformat(), "committed_volume_at_open": 600,
    }
    kwargs = _base_kwargs(
        reference_date=reference_date, state=state,
        as_of=reference_date + timedelta(days=8),
        campaigns=[_campaign("d1", "u1", reference_date + timedelta(days=2))],
    )

    result = run_renewal_agent(**kwargs, brief_provider=FakeLLMProvider(), drafter=FakeLLMProvider())

    assert result.outcome == "undetermined"


def test_waits_between_stage_thresholds_without_redrafting():
    state = {"readiness_checked": True, "value_doc_current_at_open": True,
             "reference_date_at_open": (AS_OF + timedelta(days=18)).isoformat(), "committed_volume_at_open": 600}
    kwargs = _base_kwargs(reference_date=AS_OF + timedelta(days=18), state=state)  # not yet at day 15

    result = run_renewal_agent(**kwargs, brief_provider=FakeLLMProvider(), drafter=FakeLLMProvider())

    assert result.stage == "waiting"
    assert result.actions == []
