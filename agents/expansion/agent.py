"""The Expansion Agent (BUILD-PROMPT.md §7 Play 4). Doc 06: "never run
this before a documented result exists... expanding on a fragile base
multiplies fragility." The gate (agents/expansion/gate.py) is checked in
code before anything else — the play_run the signals layer opens on the
simple 3-condition trigger gets re-validated here against the full
6-point gate, and closes immediately, undrafted, if it doesn't clear.

After the gate: a new budget holder hands to Sales (doc 06); the same
holder means CS runs it, starting with the champion's internal case.
Once the target department is actually live, this agent tracks doc 06's
four-point exit test and, on success, signals that a fresh Play 1 should
open for the new department — "a new department triggers a full Play 1
run, not an extension of the existing one" (doc 06 / BUILD-PROMPT §7)."""

import json
from dataclasses import dataclass, field
from datetime import date, timedelta

from agents.autonomy import resolve_autonomy
from agents.expansion.gate import check_expansion_gate
from agents.guardrails import check_volume_pushing
from agents.llm.base import LLMProvider, LLMUsage
from agents.prompts import load_prompt
from core.enums import AutonomyLevel
from metrics.derived import active_creators_by_department
from signals.types import CampaignFact, DepartmentFact, StakeholderFact, ValueDocFact

# No department ever went live for the target after this many days since
# the champion's internal case was drafted — this pilot isn't happening.
# Not in the brief; our own addition, same rationale as Onboarding's
# STALL_DAYS (§2.4: every play run needs a logged outcome).
NO_LAUNCH_STALL_DAYS = 180

# A department went live but never met the exit test — "a department
# added and lost is worse than neutral" (doc 06's own words). Generous
# past the 90-day sustain check to give it a real chance.
DID_NOT_STICK_STALL_DAYS = 270

FIRST_CAMPAIGN_WITHIN_DAYS = 21
SUSTAIN_WINDOW_DAYS = 90


@dataclass(frozen=True)
class ActionDraft:
    agent: str
    type: str
    payload: dict
    reasoning: str
    autonomy_level: AutonomyLevel


@dataclass(frozen=True)
class ExpansionAgentResult:
    stage: str
    actions: list[ActionDraft]
    exit_test_results: dict
    closes_play_run: bool
    outcome: str | None
    opens_onboarding_play_run: bool = False


def _usage_dict(usage: LLMUsage) -> dict:
    return {
        "provider": usage.provider, "model": usage.model, "latency_ms": usage.latency_ms,
        "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens, "cost_usd": usage.cost_usd,
    }


def _find_target_department(departments: list[DepartmentFact], target_department: str | None) -> DepartmentFact | None:
    if not target_department:
        return None
    needle = target_department.strip().lower()
    for dept in departments:
        if dept.name and dept.name.strip().lower() == needle:
            return dept
    return None


def run_expansion_agent(
    *,
    campaigns: list[CampaignFact],
    departments: list[DepartmentFact],
    stakeholders: list[StakeholderFact],
    value_docs: list[ValueDocFact],
    health_score_history: list[tuple[date, str | None]],
    target_department: str | None,
    target_owner: str | None,
    champion_introduction: bool,
    new_budget_holder: bool | None,
    stated_objective: str | None,
    tier: str,
    as_of: date,
    state: dict | None,
    drafter: LLMProvider,
    promotion_counts: dict | None = None,
) -> ExpansionAgentResult:
    state = dict(state or {})
    promotion_counts = promotion_counts or {}

    # --- Stage 1: gate check (once) — enforced in code, not the prompt ---
    if not state.get("gate_checked"):
        gate = check_expansion_gate(
            value_docs=value_docs, campaigns=campaigns, stakeholders=stakeholders,
            health_score_history=health_score_history, target_department=target_department,
            target_owner=target_owner, champion_introduction=champion_introduction,
            new_budget_holder=new_budget_holder, as_of=as_of,
        )
        state["gate_checked"] = True
        state["gate_qualified"] = gate.qualified

        if not gate.qualified:
            return ExpansionAgentResult(
                stage="gate_check",
                actions=[ActionDraft(
                    agent="expansion_agent", type="expansion_gate_not_met",
                    payload={"missing": gate.missing},
                    reasoning=f"Qualification gate not met — missing: {', '.join(gate.missing)}.",
                    autonomy_level=resolve_autonomy(tier, "internal_brief", 0),
                )],
                exit_test_results=state, closes_play_run=True, outcome="gate_not_met",
            )

        if new_budget_holder:
            return ExpansionAgentResult(
                stage="gate_check",
                actions=[ActionDraft(
                    agent="expansion_agent", type="expansion_route_to_sales",
                    payload={"target_department": target_department, "target_owner": target_owner},
                    reasoning="Gate cleared, but a new budget holder is involved — hands to Sales per doc 01 §4.",
                    autonomy_level=resolve_autonomy(tier, "internal_brief", 0),
                )],
                exit_test_results=state, closes_play_run=True, outcome="routed_to_sales",
            )
        # Same budget holder — CS runs it. Fall through to stage 2 below,
        # same pattern as the Onboarding Agent's accepted-handoff fallthrough.
        state["cs_runs_expansion"] = True
        state["stage_1_completed_at"] = as_of.isoformat()

    # --- Stage 2: build the internal case with the champion (once) ---
    if not state.get("champion_case_drafted"):
        evidence_json = json.dumps(
            {"target_department": target_department, "target_owner": target_owner,
             "stated_objective": stated_objective},
            indent=2,
        )
        response = drafter.complete(
            system="You draft messages asking a champion to make an internal introduction.",
            prompt=load_prompt(
                "expansion_champion_case", evidence_json=evidence_json,
                stated_objective=stated_objective or "(not on file)",
            ),
        )
        state["champion_case_drafted"] = True
        state["champion_case_drafted_at"] = as_of.isoformat()
        autonomy = resolve_autonomy(tier, "expansion_champion_case", promotion_counts.get("expansion_champion_case", 0))
        violations = check_volume_pushing(response.text)
        if violations and autonomy == AutonomyLevel.AUTO:
            autonomy = AutonomyLevel.DRAFT
        return ExpansionAgentResult(
            stage="champion_case",
            actions=[ActionDraft(
                agent="expansion_agent", type="expansion_champion_case",
                payload={"draft": response.text, "llm": _usage_dict(response.usage), "guardrail_violations": violations},
                reasoning=f"Qualified — asking the champion to make the introduction to {target_department}.",
                autonomy_level=autonomy,
            )],
            exit_test_results=state, closes_play_run=False, outcome=None,
        )

    # --- Stage 3: track the pilot until the target department is live ---
    dept = _find_target_department(departments, target_department)
    if dept is None:
        since = date.fromisoformat(state["champion_case_drafted_at"])
        if (as_of - since).days >= NO_LAUNCH_STALL_DAYS:
            return ExpansionAgentResult(
                stage="pilot_tracking", actions=[], exit_test_results=state,
                closes_play_run=True, outcome="stalled_department_never_launched",
            )
        return ExpansionAgentResult(
            stage="pilot_tracking", actions=[], exit_test_results=state, closes_play_run=False, outcome=None,
        )

    if not state.get("department_live_logged"):
        state["department_live_logged"] = True
        state["department_live_since"] = dept.created_at.date().isoformat()
        first_action = [ActionDraft(
            agent="expansion_agent", type="expansion_department_live",
            payload={"department_id": dept.id, "department_name": dept.name},
            reasoning=f"Target department {target_department} is now live — tracking against the Play 4 exit test.",
            autonomy_level=resolve_autonomy(tier, "internal_brief", 0),
        )]
    else:
        first_action = []

    active_by_dept = active_creators_by_department(campaigns, as_of)
    dept_creators = active_by_dept.get(dept.id, set())
    dept_campaigns = [c for c in campaigns if c.department_id == dept.id and c.billable]
    launched = [c for c in dept_campaigns if c.launched_at is not None]
    first_launch = min((c.launched_at for c in launched), default=None)
    confirmed_after_launch = [d for d in value_docs if d.confirmed_at is not None and d.confirmed_at.date() >= dept.created_at.date()]
    dept_age_days = (as_of - dept.created_at.date()).days

    exit_test = {
        "new_department_creators_ge_2": len(dept_creators) >= 2,
        "first_campaign_within_21_days": (
            first_launch is not None and (first_launch.date() - dept.created_at.date()).days <= FIRST_CAMPAIGN_WITHIN_DAYS
        ),
        # No per-department account plan exists to check "documented" directly
        # (see README) — a value doc confirmed since the department launched
        # is the closest available evidence of a documented result.
        "departmental_success_criteria_documented": bool(confirmed_after_launch),
        "volume_sustained_past_90_days": dept_age_days >= SUSTAIN_WINDOW_DAYS and len(dept_creators) >= 1,
    }
    state.update(exit_test)

    if all(exit_test.values()):
        return ExpansionAgentResult(
            stage="exit_test", actions=first_action, exit_test_results=state,
            closes_play_run=True, outcome="completed_successfully", opens_onboarding_play_run=True,
        )
    if dept_age_days >= DID_NOT_STICK_STALL_DAYS:
        return ExpansionAgentResult(
            stage="exit_test", actions=first_action, exit_test_results=state,
            closes_play_run=True, outcome="stalled_department_did_not_stick",
        )
    return ExpansionAgentResult(
        stage="pilot_tracking", actions=first_action, exit_test_results=state, closes_play_run=False, outcome=None,
    )
