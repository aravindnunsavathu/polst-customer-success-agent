"""Exact-response branching tests for the Decay Agent, using
FakeLLMProvider so each cause's path is tested precisely rather than
relying on the heuristic provider's thresholds. A drafter given zero
queued responses that gets called anyway raises — an implicit assertion
that causes routed away from drafting (product_friction, exec-to-exec)
never actually invoke the drafter."""

import json
from datetime import date, datetime, time, timedelta

from agents.decay.agent import run_decay_agent
from agents.llm.base import LLMResponse, LLMUsage
from agents.llm.fake import FakeLLMProvider
from core.enums import AutonomyLevel
from signals.types import AccountContext, CampaignFact, DepartmentFact, StakeholderFact, UserFact

AS_OF = date(2026, 9, 1)
FAKE_USAGE = LLMUsage(provider="fake", model="fake", latency_ms=1.0, input_tokens=1, output_tokens=1, cost_usd=0.0)


def _classify(cause: str, confidence: str = "high") -> LLMResponse:
    parsed = {"cause": cause, "confidence": confidence}
    return LLMResponse(text=json.dumps(parsed), parsed=parsed, usage=FAKE_USAGE)


def _draft(text: str) -> LLMResponse:
    return LLMResponse(text=text, parsed=None, usage=FAKE_USAGE)


def _campaign(dept, creator, days_ago):
    created = datetime.combine(AS_OF - timedelta(days=days_ago), time(10, 0))
    return CampaignFact(id=f"{dept}-{creator}-{days_ago}", department_id=dept, creator_id=creator,
                          created_at=created, launched_at=created)


def _base_kwargs(tier="T2", approved_without_edit_count=0):
    campaigns = [_campaign("d1", "u1", d) for d in range(0, 89, 30)]
    campaigns += [_campaign("d1", "u1", d) for d in range(95, 179, 10)]
    return dict(
        campaigns=campaigns,
        departments=[DepartmentFact(id="d1", created_at=datetime(2024, 1, 1))],
        users=[UserFact(id="u1", department_id="d1", created_at=datetime(2024, 1, 1),
                         last_active_at=datetime(2026, 8, 20), deactivated_at=None)],
        stakeholders=[],
        account=AccountContext(contract_start=date(2024, 1, 1), commercial_model="ad_hoc",
                                  committed_volume=None, commitment_end=None, potential_departments=2),
        stated_objective="5-day distribution", how_measured="audit cycle time",
        tier=tier, as_of=AS_OF, approved_without_edit_count=approved_without_edit_count,
    )


def test_seasonal_closes_play_run_with_no_action_and_no_draft():
    classifier = FakeLLMProvider(responses=[_classify("seasonal")])
    drafter = FakeLLMProvider(responses=[])  # must never be called

    result = run_decay_agent(**_base_kwargs(), classifier=classifier, drafter=drafter)

    assert result.outcome == "no_intervention_seasonal"
    assert result.action is None
    assert result.closes_play_run is True


def test_person_left_creates_creator_level_draft():
    classifier = FakeLLMProvider(responses=[_classify("person_left")])
    drafter = FakeLLMProvider(responses=[_draft("Hi — checking in on 5-day distribution. Still on track?")])

    result = run_decay_agent(**_base_kwargs(), classifier=classifier, drafter=drafter)

    assert result.outcome == "action_created"
    assert result.action.type == "decay_outreach_creator"
    assert "5-day distribution" in result.action.payload["draft"]
    assert result.closes_play_run is False


def test_never_got_value_creates_creator_level_draft():
    classifier = FakeLLMProvider(responses=[_classify("never_got_value")])
    drafter = FakeLLMProvider(responses=[_draft("Hi — how's the rollout going?")])

    result = run_decay_agent(**_base_kwargs(), classifier=classifier, drafter=drafter)

    assert result.action.type == "decay_outreach_creator"


def test_product_friction_routes_internally_with_feedback_item_and_no_draft():
    classifier = FakeLLMProvider(responses=[_classify("product_friction")])
    drafter = FakeLLMProvider(responses=[])  # must never be called

    result = run_decay_agent(**_base_kwargs(), classifier=classifier, drafter=drafter)

    assert result.outcome == "routed_internally"
    assert result.action.type == "route_to_product"
    assert result.action.payload["draft"] is None if "draft" in result.action.payload else True
    assert result.feedback_item is not None
    assert result.feedback_item.tag == "product_friction"
    assert result.feedback_item.routed_to == "Product"
    assert result.closes_play_run is False


def test_budget_priority_shift_uses_exec_to_exec_autonomy_with_no_draft():
    classifier = FakeLLMProvider(responses=[_classify("budget_priority_shift")])
    drafter = FakeLLMProvider(responses=[])  # human_writes at T1 -> drafter must never be called

    result = run_decay_agent(**_base_kwargs(tier="T1"), classifier=classifier, drafter=drafter)

    assert result.action.type == "exec_to_exec_budget_or_displacement"
    assert result.action.autonomy_level == AutonomyLevel.HUMAN_WRITES
    assert result.action.payload["draft"] is None


def test_competitive_displacement_uses_exec_to_exec_autonomy():
    classifier = FakeLLMProvider(responses=[_classify("competitive_displacement")])
    drafter = FakeLLMProvider(responses=[])

    result = run_decay_agent(**_base_kwargs(tier="T2"), classifier=classifier, drafter=drafter)

    assert result.action.type == "exec_to_exec_budget_or_displacement"
    assert result.action.autonomy_level == AutonomyLevel.NEVER


def test_guardrail_violation_downgrades_promoted_auto_to_draft():
    # T3 + 30 approved-without-edit -> decay_outreach_creator would
    # normally resolve to AUTO, but a flagged draft must never auto-send.
    classifier = FakeLLMProvider(responses=[_classify("person_left")])
    drafter = FakeLLMProvider(responses=[_draft("You should run more campaigns this month!")])

    result = run_decay_agent(
        **_base_kwargs(tier="T3", approved_without_edit_count=30), classifier=classifier, drafter=drafter
    )

    assert result.action.autonomy_level == AutonomyLevel.DRAFT
    assert result.action.payload["guardrail_violations"]
    assert "GUARDRAIL FLAGGED" in result.action.reasoning


def test_clean_draft_at_promoted_t3_stays_auto():
    classifier = FakeLLMProvider(responses=[_classify("person_left")])
    drafter = FakeLLMProvider(responses=[_draft("Hi — checking in on your rollout, still on track?")])

    result = run_decay_agent(
        **_base_kwargs(tier="T3", approved_without_edit_count=30), classifier=classifier, drafter=drafter
    )

    assert result.action.autonomy_level == AutonomyLevel.AUTO
