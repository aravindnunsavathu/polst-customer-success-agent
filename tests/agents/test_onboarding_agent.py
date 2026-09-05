"""Exact-response stage-transition tests for the Onboarding Agent, using
FakeLLMProvider so each stage's prompt call is asserted precisely and a
stage that must not draft anything (a rejected handoff) fails loudly if
the drafter is ever invoked (empty response queue -> RuntimeError)."""

from datetime import date, datetime, time, timedelta

from agents.llm.base import LLMResponse, LLMUsage
from agents.llm.fake import FakeLLMProvider
from agents.onboarding.agent import STALL_DAYS, VALUE_CONFIRMATION_DAY, run_onboarding_agent
from core.enums import AutonomyLevel
from signals.types import AccountContext, CampaignFact, DepartmentFact, StakeholderFact, UserFact, ValueDocFact

AS_OF = date(2026, 9, 1)
FAKE_USAGE = LLMUsage(provider="fake", model="fake", latency_ms=1.0, input_tokens=1, output_tokens=1, cost_usd=0.0)


def _text(s: str) -> LLMResponse:
    return LLMResponse(text=s, parsed=None, usage=FAKE_USAGE)


def _campaign(dept, creator, days_ago, launched=True):
    created = datetime.combine(AS_OF - timedelta(days=days_ago), time(10, 0))
    return CampaignFact(id=f"{dept}-{creator}-{days_ago}", department_id=dept, creator_id=creator,
                          created_at=created, launched_at=created if launched else None)


def _base_kwargs(contract_start=date(2026, 8, 1), **overrides):
    kwargs = dict(
        campaigns=[],
        departments=[DepartmentFact(id="d1", created_at=datetime(2026, 8, 1))],
        users=[UserFact(id="u1", department_id="d1", created_at=datetime(2026, 8, 1),
                         last_active_at=datetime(2026, 8, 20), deactivated_at=None)],
        stakeholders=[StakeholderFact(type="economic_buyer", last_contact_at=None, departed_at=None)],
        value_docs=[],
        account=AccountContext(contract_start=contract_start, commercial_model="ad_hoc",
                                  committed_volume=None, commitment_end=None, potential_departments=2),
        stated_objective="Cut new-menu decision cycle from 3 weeks to 4 days",
        how_measured="Time from concept to go/no-go",
        baseline="3 weeks",
        tier="T2",
        as_of=AS_OF,
        state=None,
        promotion_counts={},
    )
    kwargs.update(overrides)
    return kwargs


def test_incomplete_handoff_is_returned_to_sales_and_closes_the_play_run():
    kwargs = _base_kwargs(stated_objective=None)
    brief_provider = FakeLLMProvider(responses=[])  # must never be called
    drafter = FakeLLMProvider(responses=[])  # must never be called

    result = run_onboarding_agent(**kwargs, brief_provider=brief_provider, drafter=drafter)

    assert result.stage == "handoff_review"
    assert result.closes_play_run is True
    assert result.outcome == "handoff_rejected"
    assert result.exit_test_results["handoff_accepted"] is False
    action = result.actions[0]
    assert action.type == "handoff_returned_to_sales"
    assert "stated_business_objective" in action.payload["missing"]


def test_accepted_handoff_falls_through_to_kickoff_in_the_same_run():
    kwargs = _base_kwargs()
    brief_provider = FakeLLMProvider(responses=[_text("Internal kickoff brief.")])
    drafter = FakeLLMProvider(responses=[_text("Here's what we agreed to measure success by...")])

    result = run_onboarding_agent(**kwargs, brief_provider=brief_provider, drafter=drafter)

    assert result.stage == "kickoff"
    assert result.closes_play_run is False
    assert result.exit_test_results["handoff_accepted"] is True
    assert result.exit_test_results["kickoff_brief_prepared"] is True
    types = {a.type for a in result.actions}
    assert types == {"kickoff_brief", "onboarding_success_criteria"}


def test_kickoff_success_criteria_draft_references_the_real_stated_objective():
    """Regression test for the evidence-JSON-block bug: stated_objective
    must be inside the JSON block HeuristicLLMProvider (and, by the same
    contract, a real model reading the prompt) actually parses — not
    only present as a separate template line."""
    kwargs = _base_kwargs()
    brief_provider = FakeLLMProvider(responses=[_text("brief")])
    drafter = FakeLLMProvider(responses=[_text("draft")])

    run_onboarding_agent(**kwargs, brief_provider=brief_provider, drafter=drafter)

    criteria_call = drafter.calls[0]
    assert '"stated_objective": "Cut new-menu decision cycle from 3 weeks to 4 days"' in criteria_call["prompt"]


def test_kickoff_is_not_redrafted_once_state_marks_it_prepared():
    state = {"handoff_reviewed": True, "handoff_accepted": True, "kickoff_brief_prepared": True}
    kwargs = _base_kwargs(state=state, contract_start=AS_OF - timedelta(days=10))
    brief_provider = FakeLLMProvider(responses=[])  # must never be called
    drafter = FakeLLMProvider(responses=[])  # must never be called

    result = run_onboarding_agent(**kwargs, brief_provider=brief_provider, drafter=drafter)

    assert result.stage == "waiting"
    assert result.actions == []


def test_value_confirmation_not_requested_before_day_40():
    state = {"handoff_reviewed": True, "handoff_accepted": True, "kickoff_brief_prepared": True}
    kwargs = _base_kwargs(
        state=state, contract_start=AS_OF - timedelta(days=VALUE_CONFIRMATION_DAY - 1),
    )
    drafter = FakeLLMProvider(responses=[])  # must never be called

    result = run_onboarding_agent(**kwargs, brief_provider=FakeLLMProvider(), drafter=drafter)

    assert result.stage == "waiting"
    assert result.actions == []


def test_value_confirmation_requested_at_day_40_when_result_unconfirmed():
    state = {"handoff_reviewed": True, "handoff_accepted": True, "kickoff_brief_prepared": True}
    kwargs = _base_kwargs(
        state=state, contract_start=AS_OF - timedelta(days=VALUE_CONFIRMATION_DAY),
    )
    drafter = FakeLLMProvider(responses=[_text("Hi — checking in on Cut new-menu decision cycle...")])

    result = run_onboarding_agent(**kwargs, brief_provider=FakeLLMProvider(), drafter=drafter)

    assert result.stage == "value_confirmation"
    assert result.exit_test_results["value_confirmation_requested"] is True
    action = result.actions[0]
    assert action.type == "value_confirmation_request"
    assert result.closes_play_run is False


def test_value_confirmation_draft_evidence_includes_stated_objective_and_baseline():
    """Same evidence-JSON-block regression, for the value-confirmation
    stage specifically (the bug fixed second, after kickoff)."""
    state = {"handoff_reviewed": True, "handoff_accepted": True, "kickoff_brief_prepared": True}
    kwargs = _base_kwargs(state=state, contract_start=AS_OF - timedelta(days=VALUE_CONFIRMATION_DAY))
    drafter = FakeLLMProvider(responses=[_text("draft")])

    run_onboarding_agent(**kwargs, brief_provider=FakeLLMProvider(), drafter=drafter)

    prompt = drafter.calls[0]["prompt"]
    assert '"stated_objective": "Cut new-menu decision cycle from 3 weeks to 4 days"' in prompt
    assert '"baseline": "3 weeks"' in prompt


def test_value_confirmation_not_requested_twice():
    state = {
        "handoff_reviewed": True, "handoff_accepted": True, "kickoff_brief_prepared": True,
        "value_confirmation_requested": True,
    }
    kwargs = _base_kwargs(state=state, contract_start=AS_OF - timedelta(days=VALUE_CONFIRMATION_DAY + 5))
    drafter = FakeLLMProvider(responses=[])  # must never be called

    result = run_onboarding_agent(**kwargs, brief_provider=FakeLLMProvider(), drafter=drafter)

    assert result.stage == "waiting"
    assert result.actions == []


def test_value_confirmation_skipped_once_result_is_already_confirmed():
    state = {"handoff_reviewed": True, "handoff_accepted": True, "kickoff_brief_prepared": True}
    kwargs = _base_kwargs(
        state=state, contract_start=AS_OF - timedelta(days=VALUE_CONFIRMATION_DAY),
        value_docs=[ValueDocFact(created_at=datetime(2026, 8, 5), confirmed_at=datetime(2026, 8, 20))],
    )
    drafter = FakeLLMProvider(responses=[])  # must never be called

    result = run_onboarding_agent(**kwargs, brief_provider=FakeLLMProvider(), drafter=drafter)

    assert result.exit_test_results["result_confirmed"] is True
    assert result.stage == "waiting"


def test_exit_test_never_closes_at_launch_alone():
    """"Do not let the agent close this play at launch" — a single
    launched campaign and nothing else must leave the play open."""
    state = {"handoff_reviewed": True, "handoff_accepted": True, "kickoff_brief_prepared": True}
    kwargs = _base_kwargs(
        state=state, contract_start=AS_OF - timedelta(days=10),
        campaigns=[_campaign("d1", "u1", 5)],
    )

    result = run_onboarding_agent(
        **kwargs, brief_provider=FakeLLMProvider(), drafter=FakeLLMProvider(),
    )

    assert result.closes_play_run is False
    assert result.stage != "exit_test" or result.outcome != "completed_successfully"


def test_exit_test_closes_successfully_once_all_four_conditions_are_met():
    state = {"handoff_reviewed": True, "handoff_accepted": True, "kickoff_brief_prepared": True}
    kwargs = _base_kwargs(
        state=state, contract_start=AS_OF - timedelta(days=50),
        users=[
            UserFact(id="u1", department_id="d1", created_at=datetime(2026, 8, 1),
                     last_active_at=datetime(2026, 8, 25), deactivated_at=None),
            UserFact(id="u2", department_id="d1", created_at=datetime(2026, 8, 1),
                     last_active_at=datetime(2026, 8, 25), deactivated_at=None),
        ],
        campaigns=[_campaign("d1", "u1", 20), _campaign("d1", "u2", 10)],
        value_docs=[ValueDocFact(
            created_at=datetime(2026, 8, 10), confirmed_at=datetime(2026, 8, 20), confirmed_by="buyer@customer.com",
        )],
    )

    result = run_onboarding_agent(
        **kwargs, brief_provider=FakeLLMProvider(), drafter=FakeLLMProvider(),
    )

    assert result.stage == "exit_test"
    assert result.closes_play_run is True
    assert result.outcome == "completed_successfully"


def test_exit_test_stalls_past_the_stall_window_if_still_unmet():
    state = {"handoff_reviewed": True, "handoff_accepted": True, "kickoff_brief_prepared": True,
             "value_confirmation_requested": True}
    kwargs = _base_kwargs(state=state, contract_start=AS_OF - timedelta(days=STALL_DAYS))

    result = run_onboarding_agent(
        **kwargs, brief_provider=FakeLLMProvider(), drafter=FakeLLMProvider(),
    )

    assert result.stage == "exit_test"
    assert result.closes_play_run is True
    assert result.outcome == "stalled"


def test_guardrail_downgrades_a_volume_pushing_draft_even_at_auto_tier():
    kwargs = _base_kwargs(tier="T3", promotion_counts={"onboarding_sequence": 30})
    brief_provider = FakeLLMProvider(responses=[_text("brief")])
    drafter = FakeLLMProvider(responses=[_text("Please run more campaigns this month to hit your target.")])

    result = run_onboarding_agent(**kwargs, brief_provider=brief_provider, drafter=drafter)

    criteria_action = next(a for a in result.actions if a.type == "onboarding_success_criteria")
    assert criteria_action.autonomy_level == AutonomyLevel.DRAFT
    assert criteria_action.payload["guardrail_violations"]


def test_compliant_draft_reaches_auto_once_promoted_on_a_t3_account():
    kwargs = _base_kwargs(tier="T3", promotion_counts={"onboarding_sequence": 30})
    brief_provider = FakeLLMProvider(responses=[_text("brief")])
    drafter = FakeLLMProvider(responses=[_text("Here's what we agreed to measure success by.")])

    result = run_onboarding_agent(**kwargs, brief_provider=brief_provider, drafter=drafter)

    criteria_action = next(a for a in result.actions if a.type == "onboarding_success_criteria")
    assert criteria_action.autonomy_level == AutonomyLevel.AUTO
