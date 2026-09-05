"""Stage-transition tests for the Expansion Agent, mirroring
test_onboarding_agent.py's style: FakeLLMProvider for exact drafting
control, and explicit assertions that the gate closes the play
immediately (undrafted) when it isn't met — the "enforced in code, not
the prompt" requirement from BUILD-PROMPT.md §7."""

from datetime import date, datetime, time, timedelta

from agents.expansion.agent import (
    DID_NOT_STICK_STALL_DAYS,
    NO_LAUNCH_STALL_DAYS,
    run_expansion_agent,
)
from agents.llm.base import LLMResponse, LLMUsage
from agents.llm.fake import FakeLLMProvider
from core.enums import AutonomyLevel
from signals.types import CampaignFact, DepartmentFact, StakeholderFact, ValueDocFact

AS_OF = date(2026, 9, 5)
FAKE_USAGE = LLMUsage(provider="fake", model="fake", latency_ms=1.0, input_tokens=1, output_tokens=1, cost_usd=0.0)


def _text(s: str) -> LLMResponse:
    return LLMResponse(text=s, parsed=None, usage=FAKE_USAGE)


def _campaign(dept, creator, created_on: date):
    created = datetime.combine(created_on, time(10, 0))
    return CampaignFact(id=f"{dept}-{creator}-{created_on}", department_id=dept, creator_id=creator,
                          created_at=created, launched_at=created)


def _qualifying_kwargs(**overrides):
    kwargs = dict(
        campaigns=[_campaign("d1", "a", AS_OF - timedelta(days=5)), _campaign("d1", "b", AS_OF - timedelta(days=3))],
        departments=[DepartmentFact(id="d1", created_at=datetime(2025, 1, 1), name="Menu Innovation")],
        stakeholders=[StakeholderFact(type="champion", last_contact_at=datetime(2026, 8, 1), departed_at=None)],
        value_docs=[ValueDocFact(created_at=datetime(2026, 1, 1), confirmed_at=datetime(2026, 7, 1))],
        health_score_history=[(AS_OF - timedelta(days=d), "healthy") for d in range(0, 70, 7)],
        target_department="Franchise Relations",
        target_owner="Jamie Lee",
        champion_introduction=True,
        new_budget_holder=False,
        stated_objective="Faster, evidence-based pricing decisions",
        tier="T1",
        as_of=AS_OF,
        state=None,
        promotion_counts={},
    )
    kwargs.update(overrides)
    return kwargs


def test_gate_not_met_closes_the_play_immediately_without_drafting():
    kwargs = _qualifying_kwargs(value_docs=[])  # no confirmed result -> gate fails
    drafter = FakeLLMProvider(responses=[])  # must never be called

    result = run_expansion_agent(**kwargs, drafter=drafter)

    assert result.stage == "gate_check"
    assert result.closes_play_run is True
    assert result.outcome == "gate_not_met"
    assert result.actions[0].type == "expansion_gate_not_met"
    assert "no_confirmed_result_in_last_2_quarters" in result.actions[0].payload["missing"]


def test_new_budget_holder_routes_to_sales_without_drafting():
    kwargs = _qualifying_kwargs(new_budget_holder=True)
    drafter = FakeLLMProvider(responses=[])  # must never be called

    result = run_expansion_agent(**kwargs, drafter=drafter)

    assert result.closes_play_run is True
    assert result.outcome == "routed_to_sales"
    assert result.actions[0].type == "expansion_route_to_sales"


def test_qualified_same_budget_holder_falls_through_to_champion_case_draft():
    kwargs = _qualifying_kwargs()
    drafter = FakeLLMProvider(responses=[_text("Bring this to Franchise Relations.")])

    result = run_expansion_agent(**kwargs, drafter=drafter)

    assert result.stage == "champion_case"
    assert result.closes_play_run is False
    assert result.exit_test_results["gate_qualified"] is True
    assert result.actions[0].type == "expansion_champion_case"


def test_champion_case_evidence_includes_target_department_and_objective():
    kwargs = _qualifying_kwargs()
    drafter = FakeLLMProvider(responses=[_text("draft")])

    run_expansion_agent(**kwargs, drafter=drafter)

    prompt = drafter.calls[0]["prompt"]
    assert '"target_department": "Franchise Relations"' in prompt
    assert '"stated_objective": "Faster, evidence-based pricing decisions"' in prompt


def test_champion_case_not_redrafted_once_state_marks_it_done():
    state = {"gate_checked": True, "gate_qualified": True, "cs_runs_expansion": True,
             "stage_1_completed_at": AS_OF.isoformat(), "champion_case_drafted": True,
             "champion_case_drafted_at": AS_OF.isoformat()}
    kwargs = _qualifying_kwargs(state=state)
    drafter = FakeLLMProvider(responses=[])  # must never be called

    result = run_expansion_agent(**kwargs, drafter=drafter)

    assert result.stage == "pilot_tracking"
    assert result.actions == []


def test_stalls_if_target_department_never_launches():
    state = {"gate_checked": True, "gate_qualified": True, "cs_runs_expansion": True,
             "stage_1_completed_at": AS_OF.isoformat(), "champion_case_drafted": True,
             "champion_case_drafted_at": (AS_OF - timedelta(days=NO_LAUNCH_STALL_DAYS)).isoformat()}
    kwargs = _qualifying_kwargs(state=state, departments=[])  # target department still doesn't exist

    result = run_expansion_agent(**kwargs, drafter=FakeLLMProvider())

    assert result.closes_play_run is True
    assert result.outcome == "stalled_department_never_launched"


def test_department_live_logged_once_when_first_detected():
    state = {"gate_checked": True, "gate_qualified": True, "cs_runs_expansion": True,
             "stage_1_completed_at": AS_OF.isoformat(), "champion_case_drafted": True,
             "champion_case_drafted_at": (AS_OF - timedelta(days=10)).isoformat()}
    departments = [DepartmentFact(id="d2", created_at=datetime(2026, 8, 20), name="Franchise Relations")]
    kwargs = _qualifying_kwargs(state=state, departments=departments, campaigns=[])

    result = run_expansion_agent(**kwargs, drafter=FakeLLMProvider())

    assert result.exit_test_results["department_live_logged"] is True
    assert result.actions[0].type == "expansion_department_live"
    assert result.closes_play_run is False  # exit test not met yet (just launched)


def test_exit_test_closes_successfully_when_all_four_conditions_hold():
    dept_created = AS_OF - timedelta(days=100)  # past the 90-day sustain window
    state = {"gate_checked": True, "gate_qualified": True, "cs_runs_expansion": True,
             "stage_1_completed_at": AS_OF.isoformat(), "champion_case_drafted": True,
             "champion_case_drafted_at": dept_created.isoformat(), "department_live_logged": True,
             "department_live_since": dept_created.isoformat()}
    departments = [DepartmentFact(id="d2", created_at=datetime.combine(dept_created, time(9, 0)), name="Franchise Relations")]
    campaigns = [
        _campaign("d2", "u1", AS_OF - timedelta(days=5)),
        _campaign("d2", "u2", AS_OF - timedelta(days=3)),
        _campaign("d2", "u1", dept_created + timedelta(days=10)),  # launched within 21 days of dept creation
    ]
    value_docs = [ValueDocFact(
        created_at=datetime.combine(dept_created, time(9, 0)),
        confirmed_at=datetime.combine(dept_created + timedelta(days=30), time(9, 0)),
    )]
    kwargs = _qualifying_kwargs(state=state, departments=departments, campaigns=campaigns, value_docs=value_docs)

    result = run_expansion_agent(**kwargs, drafter=FakeLLMProvider())

    assert result.exit_test_results["new_department_creators_ge_2"] is True
    assert result.exit_test_results["first_campaign_within_21_days"] is True
    assert result.exit_test_results["departmental_success_criteria_documented"] is True
    assert result.exit_test_results["volume_sustained_past_90_days"] is True
    assert result.closes_play_run is True
    assert result.outcome == "completed_successfully"
    assert result.opens_onboarding_play_run is True


def test_exit_test_not_yet_met_keeps_the_play_open():
    dept_created = AS_OF - timedelta(days=10)
    state = {"gate_checked": True, "gate_qualified": True, "cs_runs_expansion": True,
             "stage_1_completed_at": AS_OF.isoformat(), "champion_case_drafted": True,
             "champion_case_drafted_at": dept_created.isoformat(), "department_live_logged": True,
             "department_live_since": dept_created.isoformat()}
    departments = [DepartmentFact(id="d2", created_at=datetime.combine(dept_created, time(9, 0)), name="Franchise Relations")]
    campaigns = [_campaign("d2", "u1", AS_OF - timedelta(days=5))]  # only one creator so far
    kwargs = _qualifying_kwargs(state=state, departments=departments, campaigns=campaigns, value_docs=[])

    result = run_expansion_agent(**kwargs, drafter=FakeLLMProvider())

    assert result.closes_play_run is False
    assert result.opens_onboarding_play_run is False


def test_stalls_if_department_launched_but_never_sticks():
    dept_created = AS_OF - timedelta(days=DID_NOT_STICK_STALL_DAYS)
    state = {"gate_checked": True, "gate_qualified": True, "cs_runs_expansion": True,
             "stage_1_completed_at": AS_OF.isoformat(), "champion_case_drafted": True,
             "champion_case_drafted_at": dept_created.isoformat(), "department_live_logged": True,
             "department_live_since": dept_created.isoformat()}
    departments = [DepartmentFact(id="d2", created_at=datetime.combine(dept_created, time(9, 0)), name="Franchise Relations")]
    kwargs = _qualifying_kwargs(state=state, departments=departments, campaigns=[], value_docs=[])

    result = run_expansion_agent(**kwargs, drafter=FakeLLMProvider())

    assert result.closes_play_run is True
    assert result.outcome == "stalled_department_did_not_stick"


def test_champion_case_uses_its_own_autonomy_row():
    kwargs = _qualifying_kwargs(tier="T3", promotion_counts={"expansion_champion_case": 999})
    drafter = FakeLLMProvider(responses=[_text("Bring this to Franchise Relations.")])

    result = run_expansion_agent(**kwargs, drafter=drafter)

    assert result.actions[0].autonomy_level == AutonomyLevel.AUTO  # T3 expansion_champion_case is auto
