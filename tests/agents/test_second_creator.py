from datetime import date, datetime, time, timedelta

from agents.llm.base import LLMResponse, LLMUsage
from agents.llm.fake import FakeLLMProvider
from agents.second_creator.agent import draft_seeding_action, find_single_threaded_departments
from core.enums import AutonomyLevel

AS_OF = date(2026, 9, 1)
FAKE_USAGE = LLMUsage(provider="fake", model="fake", latency_ms=1.0, input_tokens=1, output_tokens=1, cost_usd=0.0)


def _campaign(dept, creator, days_ago):
    created = datetime.combine(AS_OF - timedelta(days=days_ago), time(10, 0))
    from signals.types import CampaignFact
    return CampaignFact(id=f"{dept}-{creator}-{days_ago}", department_id=dept, creator_id=creator,
                          created_at=created, launched_at=created)


def test_finds_a_department_with_exactly_one_active_creator():
    campaigns = [_campaign("d1", "solo", d) for d in range(0, 89, 20)]
    candidates = find_single_threaded_departments(campaigns, AS_OF)
    assert len(candidates) == 1
    assert candidates[0].department_id == "d1"
    assert candidates[0].sole_creator_id == "solo"


def test_ignores_departments_with_two_or_more_active_creators():
    campaigns = [_campaign("d1", "a", 10), _campaign("d1", "b", 10)]
    assert find_single_threaded_departments(campaigns, AS_OF) == []


def test_ignores_departments_with_no_activity_in_the_window():
    campaigns = [_campaign("d1", "solo", 200)]  # outside the 90-day window
    assert find_single_threaded_departments(campaigns, AS_OF) == []


def test_drafted_action_asks_to_bring_in_a_colleague_and_avoids_risk_language():
    from agents.second_creator.agent import SecondCreatorCandidate
    candidate = SecondCreatorCandidate(department_id="d1", sole_creator_id="solo")
    drafter = FakeLLMProvider(responses=[
        LLMResponse(text="Would you like to bring in a colleague to help out?", parsed=None, usage=FAKE_USAGE)
    ])

    action = draft_seeding_action(candidate=candidate, tier="T2", drafter=drafter)

    assert action.type == "second_creator_seeding"
    assert action.payload["department_id"] == "d1"
    assert action.payload["guardrail_violations"] == []
    assert action.autonomy_level == AutonomyLevel.DRAFT  # T2 routine_check_in is draft


def test_guardrail_downgrades_a_volume_pushing_draft_at_auto_tier():
    from agents.second_creator.agent import SecondCreatorCandidate
    candidate = SecondCreatorCandidate(department_id="d1", sole_creator_id="solo")
    drafter = FakeLLMProvider(responses=[
        LLMResponse(text="Run more campaigns this month with a colleague's help!", parsed=None, usage=FAKE_USAGE)
    ])

    action = draft_seeding_action(candidate=candidate, tier="T3", drafter=drafter)  # T3 routine_check_in is auto

    assert action.autonomy_level == AutonomyLevel.DRAFT
    assert action.payload["guardrail_violations"]


def test_heuristic_provider_drafts_a_seeding_specific_message_not_a_value_check_in():
    """Regression test: HeuristicLLMProvider's _draft used to fall back to
    the decay/onboarding "checking in on your objective" template for
    every prompt, including second-creator seeding, which has no
    objective to check in on at all and contradicts the prompt's own
    instruction to ask the customer to bring in a colleague."""
    from agents.llm.fake import HeuristicLLMProvider
    from agents.second_creator.agent import SecondCreatorCandidate

    candidate = SecondCreatorCandidate(department_id="d1", sole_creator_id="solo")
    action = draft_seeding_action(candidate=candidate, tier="T2", drafter=HeuristicLLMProvider())

    draft = action.payload["draft"].lower()
    assert "colleague" in draft
    assert "checking in on the result you were working toward" not in draft
