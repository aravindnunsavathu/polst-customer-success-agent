"""The Onboarding Agent (BUILD-PROMPT.md §7 Play 1) — a multi-week state
machine, not a single-shot decision. Advances at most one stage per
invocation, using play_runs.exit_test_results as persisted state across
nightly runs (same pattern the Decay Agent uses for its recovery
baseline). Never closes at launch — "the exit is the second
customer-initiated campaign," and all four exit-test conditions must be
true — or the play is left open until a generous stall window elapses,
so it doesn't stay open forever on a genuinely abandoned onboarding."""

import json
from dataclasses import dataclass, field
from datetime import date

from agents.autonomy import resolve_autonomy
from agents.guardrails import check_volume_pushing
from agents.llm.base import LLMProvider, LLMUsage
from agents.onboarding.handoff import review_handoff
from agents.prompts import load_prompt
from core.enums import AutonomyLevel
from metrics.derived import active_creators_by_department
from signals.types import AccountContext, CampaignFact, DepartmentFact, StakeholderFact, UserFact, ValueDocFact

# Past this many days with the exit test still unmet, stop waiting —
# BUILD-PROMPT.md doesn't specify a cutoff; this is our own addition so
# play_runs don't stay open forever on an onboarding that's genuinely
# not going to complete (§2.4: "every play run records an outcome").
STALL_DAYS = 120

VALUE_CONFIRMATION_DAY = 40  # "~day 45" per doc 06; start a few days early for the batch cadence


@dataclass(frozen=True)
class ActionDraft:
    agent: str
    type: str
    payload: dict
    reasoning: str
    autonomy_level: AutonomyLevel


@dataclass(frozen=True)
class OnboardingAgentResult:
    stage: str
    actions: list[ActionDraft]
    exit_test_results: dict
    closes_play_run: bool
    outcome: str | None


def _usage_dict(usage: LLMUsage) -> dict:
    return {
        "provider": usage.provider, "model": usage.model, "latency_ms": usage.latency_ms,
        "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens, "cost_usd": usage.cost_usd,
    }


def _exit_test_conditions(
    campaigns: list[CampaignFact], value_docs: list[ValueDocFact], as_of: date
) -> dict:
    """The four doc 06 Play 1 exit-test conditions. `buyer_has_seen_result`
    has no direct data source — a value doc with `confirmed_by` set is
    the closest proxy this schema supports (someone confirmed it, which
    doc 06's process routes through the economic buyer); a real system
    would want an explicit "shared with buyer" event."""
    confirmed_docs = [d for d in value_docs if d.confirmed_at is not None]
    active_by_dept = active_creators_by_department(campaigns, as_of)
    total_active_creators = {c for creators in active_by_dept.values() for c in creators}
    launched = [c for c in campaigns if c.billable and c.launched_at is not None]
    return {
        "result_confirmed": bool(confirmed_docs),
        "active_creators_ge_2": len(total_active_creators) >= 2,
        "second_campaign_customer_initiated": len(launched) >= 2,
        "buyer_has_seen_result": any(d.confirmed_by for d in value_docs),
    }


def _guardrail_gated(action_type: str, tier: str, promotion_count: int, response, config_path=None) -> tuple[AutonomyLevel, list[str]]:
    autonomy = resolve_autonomy(tier, action_type, promotion_count, config_path)
    violations = check_volume_pushing(response.text)
    if violations and autonomy == AutonomyLevel.AUTO:
        autonomy = AutonomyLevel.DRAFT
    return autonomy, violations


def run_onboarding_agent(
    *,
    campaigns: list[CampaignFact],
    departments: list[DepartmentFact],
    users: list[UserFact],
    stakeholders: list[StakeholderFact],
    value_docs: list[ValueDocFact],
    account: AccountContext,
    stated_objective: str | None,
    how_measured: str | None,
    baseline: str | None,
    tier: str,
    as_of: date,
    state: dict | None,
    brief_provider: LLMProvider,
    drafter: LLMProvider,
    promotion_counts: dict | None = None,
) -> OnboardingAgentResult:
    state = dict(state or {})
    promotion_counts = promotion_counts or {}
    age_days = (as_of - account.contract_start).days

    # --- Stage 1: handoff review (day -3, once) ---
    if not state.get("handoff_reviewed"):
        review = review_handoff(
            stated_objective=stated_objective, stakeholders=stakeholders,
            departments=departments, users=users, account=account,
        )
        state["handoff_reviewed"] = True
        state["handoff_accepted"] = review.accepted
        if not review.accepted:
            return OnboardingAgentResult(
                stage="handoff_review",
                actions=[ActionDraft(
                    agent="onboarding_agent", type="handoff_returned_to_sales",
                    payload={"missing": review.missing, "unverifiable": review.unverifiable},
                    reasoning=(
                        f"Handoff incomplete — missing: {', '.join(review.missing)}. "
                        f"Returned to Sales rather than starting onboarding on an incomplete basis."
                    ),
                    autonomy_level=resolve_autonomy(tier, "internal_brief", 0),
                )],
                exit_test_results=state, closes_play_run=True, outcome="handoff_rejected",
            )

    # --- Stage 2: kickoff brief + written success criteria (day 0-1, once) ---
    if not state.get("kickoff_brief_prepared"):
        base_evidence = {
            "account_age_days": age_days,
            "departments": [d.id for d in departments],
            "creator_count": len(users),
        }
        # stated_objective/how_measured folded into the JSON block itself
        # (not just the template's separate $stated_objective line) so a
        # JSON-block parser — a real LLM, or HeuristicLLMProvider's regex
        # — reliably sees it. Same fix as the Decay Agent's draft step.
        criteria_evidence_json = json.dumps(
            {**base_evidence, "stated_objective": stated_objective, "how_measured": how_measured}, indent=2
        )

        brief = brief_provider.complete(
            system="You write internal CS kickoff briefs.",
            prompt=load_prompt("onboarding_kickoff_brief", evidence_json=json.dumps(base_evidence, indent=2)),
        )
        criteria = drafter.complete(
            system="You draft customer-facing success-criteria confirmations.",
            prompt=load_prompt(
                "onboarding_success_criteria", evidence_json=criteria_evidence_json,
                stated_objective=stated_objective or "(not on file)",
                how_measured=how_measured or "(not on file)",
            ),
        )
        state["kickoff_brief_prepared"] = True
        criteria_autonomy, criteria_violations = _guardrail_gated(
            "onboarding_sequence", tier, promotion_counts.get("onboarding_sequence", 0), criteria
        )
        return OnboardingAgentResult(
            stage="kickoff",
            actions=[
                ActionDraft(
                    agent="onboarding_agent", type="kickoff_brief",
                    payload={"brief": brief.text, "llm": _usage_dict(brief.usage)},
                    reasoning="Kickoff brief prepared ahead of the day-0 call.",
                    autonomy_level=resolve_autonomy(tier, "internal_brief", 0),
                ),
                ActionDraft(
                    agent="onboarding_agent", type="onboarding_success_criteria",
                    payload={
                        "draft": criteria.text, "llm": _usage_dict(criteria.usage),
                        "guardrail_violations": criteria_violations,
                    },
                    reasoning="Written success criteria drafted for the customer to confirm in writing.",
                    autonomy_level=criteria_autonomy,
                ),
            ],
            exit_test_results=state, closes_play_run=False, outcome=None,
        )

    # --- Live exit-test conditions, recomputed every run from current data ---
    conditions = _exit_test_conditions(campaigns, value_docs, as_of)
    state.update(conditions)

    # --- Stage 3: value confirmation request (~day 45, once, only if not yet confirmed) ---
    if (
        age_days >= VALUE_CONFIRMATION_DAY
        and not state.get("value_confirmation_requested")
        and not conditions["result_confirmed"]
    ):
        evidence_json = json.dumps(
            {
                "account_age_days": age_days, **conditions,
                "stated_objective": stated_objective, "how_measured": how_measured, "baseline": baseline,
            },
            indent=2,
        )
        response = drafter.complete(
            system="You draft value-confirmation requests to economic buyers.",
            prompt=load_prompt(
                "onboarding_value_confirmation", evidence_json=evidence_json,
                stated_objective=stated_objective or "(not on file)",
                how_measured=how_measured or "(not on file)",
                baseline=baseline or "(not on file)",
            ),
        )
        state["value_confirmation_requested"] = True
        autonomy, violations = _guardrail_gated(
            "value_confirmation_request", tier, promotion_counts.get("value_confirmation_request", 0), response
        )
        return OnboardingAgentResult(
            stage="value_confirmation",
            actions=[ActionDraft(
                agent="onboarding_agent", type="value_confirmation_request",
                payload={"draft": response.text, "llm": _usage_dict(response.usage), "guardrail_violations": violations},
                reasoning=f"Day {age_days}: no confirmed result yet — requesting value confirmation from the economic buyer.",
                autonomy_level=autonomy,
            )],
            exit_test_results=state, closes_play_run=False, outcome=None,
        )

    # --- Stage 4: exit test ---
    if all(conditions.values()):
        return OnboardingAgentResult(
            stage="exit_test", actions=[], exit_test_results=state,
            closes_play_run=True, outcome="completed_successfully",
        )
    if age_days >= STALL_DAYS:
        return OnboardingAgentResult(
            stage="exit_test", actions=[], exit_test_results=state,
            closes_play_run=True, outcome="stalled",
        )
    return OnboardingAgentResult(
        stage="waiting", actions=[], exit_test_results=state, closes_play_run=False, outcome=None,
    )
