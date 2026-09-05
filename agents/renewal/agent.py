"""The Renewal Agent (BUILD-PROMPT.md §7 Play 3) — a T-20 to T+7 state
machine, the same persisted-state-in-play_runs.exit_test_results pattern
as the Onboarding Agent. Advances at most one stage per invocation; a
job that starts late (the play_run can open anywhere from T-20 to T-0
depending on when the nightly job first sees it) falls through every
already-due stage across successive runs rather than skipping them.

Doc 06's "paper it" step (T-5, signing the actual contract) has no
system representation — it's an offline step with no data this system
could compute or draft, so it isn't modeled as a stage here; the
objections stage is the last agent-driven checkpoint before it."""

import json
from dataclasses import dataclass, field
from datetime import date

from agents.autonomy import resolve_autonomy
from agents.guardrails import check_volume_pushing
from agents.llm.base import LLMProvider, LLMUsage
from agents.prompts import load_prompt
from agents.renewal.diagnosis import assess_renewal_readiness
from core.enums import AutonomyLevel
from metrics.derived import departments_live, volume_ratio_90d
from signals.types import AccountContext, CampaignFact, StakeholderFact, ValueDocFact

VALUE_REVIEW_DAY = 15   # days-out threshold, i.e. days_out <= 15
GROWTH_PROPOSAL_DAY = 10
OBJECTIONS_DAY = 5
DEBRIEF_DAY = -7  # 7 days *past* the reference date


@dataclass(frozen=True)
class ActionDraft:
    agent: str
    type: str
    payload: dict
    reasoning: str
    autonomy_level: AutonomyLevel


@dataclass(frozen=True)
class RenewalAgentResult:
    stage: str
    actions: list[ActionDraft]
    exit_test_results: dict
    closes_play_run: bool
    outcome: str | None
    feedback_item: dict | None = None


def _usage_dict(usage: LLMUsage) -> dict:
    return {
        "provider": usage.provider, "model": usage.model, "latency_ms": usage.latency_ms,
        "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens, "cost_usd": usage.cost_usd,
    }


def _guardrail_gated(action_type: str, tier: str, promotion_count: int, response, config_path=None) -> tuple[AutonomyLevel, list[str]]:
    autonomy = resolve_autonomy(tier, action_type, promotion_count, config_path)
    violations = check_volume_pushing(response.text)
    if violations and autonomy == AutonomyLevel.AUTO:
        autonomy = AutonomyLevel.DRAFT
    return autonomy, violations


def run_renewal_agent(
    *,
    campaigns: list[CampaignFact],
    value_docs: list[ValueDocFact],
    stakeholders: list[StakeholderFact],
    account: AccountContext,
    reference_date: date,
    stated_objective: str | None,
    how_measured: str | None,
    tier: str,
    as_of: date,
    state: dict | None,
    brief_provider: LLMProvider,
    drafter: LLMProvider,
    promotion_counts: dict | None = None,
) -> RenewalAgentResult:
    state = dict(state or {})
    promotion_counts = promotion_counts or {}
    days_out = (reference_date - as_of).days
    consumed = sum(1 for c in campaigns if c.billable)

    # --- Stage 1: readiness (T-20, once) ---
    if not state.get("readiness_checked"):
        readiness = assess_renewal_readiness(
            value_docs=value_docs, consumed=consumed, campaigns=campaigns,
            stakeholders=stakeholders, account=account, as_of=as_of,
        )
        state["readiness_checked"] = True
        state["value_doc_current_at_open"] = readiness.value_doc_current
        state["reference_date_at_open"] = reference_date.isoformat()
        state["committed_volume_at_open"] = account.committed_volume

        feedback_item = None
        if readiness.utilization_status == "oversold_at_signing":
            feedback_item = {
                "source": "renewal_agent", "verbatim": (
                    f"Committed utilization at {readiness.utilization_pace:.0%} with term ending "
                    f"{reference_date.isoformat()} — usage has been low since the start of the term, "
                    f"not a recent decline. Likely oversold at signing."
                ),
                "tag": "oversold_commitment", "routed_to": "Sales",
            }

        return RenewalAgentResult(
            stage="readiness",
            actions=[ActionDraft(
                agent="renewal_agent", type="renewal_readiness_check",
                payload={"gaps": readiness.gaps, "utilization_status": readiness.utilization_status,
                          "utilization_pace": readiness.utilization_pace},
                reasoning=(
                    f"T-{days_out}: evidence/utilization/stakeholder check ahead of the renewal conversation."
                    + (f" Gaps: {', '.join(readiness.gaps)}." if readiness.gaps else " No gaps found.")
                ),
                autonomy_level=resolve_autonomy(tier, "internal_brief", 0),
            )],
            exit_test_results=state, closes_play_run=False, outcome=None,
            feedback_item=feedback_item,
        )

    # --- Stage 2: value review (T-15, once) ---
    if days_out <= VALUE_REVIEW_DAY and not state.get("value_review_drafted"):
        confirmed = [d for d in value_docs if d.confirmed_at is not None]
        result_text = max(confirmed, key=lambda d: d.confirmed_at).confirmed_by if confirmed else None
        evidence_json = json.dumps(
            {"days_out": days_out, "value_doc_confirmed": bool(confirmed), "confirmed_by": result_text,
             "stated_objective": stated_objective, "how_measured": how_measured},
            indent=2,
        )
        response = drafter.complete(
            system="You draft renewal value-review messages to economic buyers.",
            prompt=load_prompt(
                "renewal_value_review", evidence_json=evidence_json,
                stated_objective=stated_objective or "(not on file)",
                how_measured=how_measured or "(not on file)",
                baseline="(see account plan)",
            ),
        )
        state["value_review_drafted"] = True
        autonomy, violations = _guardrail_gated(
            "renewal_value_review", tier, promotion_counts.get("renewal_value_review", 0), response
        )
        return RenewalAgentResult(
            stage="value_review",
            actions=[ActionDraft(
                agent="renewal_agent", type="renewal_value_review",
                payload={"draft": response.text, "llm": _usage_dict(response.usage), "guardrail_violations": violations},
                reasoning=f"T-{days_out}: value review with the economic buyer, before any commercial ask.",
                autonomy_level=autonomy,
            )],
            exit_test_results=state, closes_play_run=False, outcome=None,
        )

    # --- Stage 3: growth proposal (T-10, once) ---
    if days_out <= GROWTH_PROPOSAL_DAY and not state.get("growth_proposal_drafted"):
        ratio = volume_ratio_90d(campaigns, as_of)
        evidence_json = json.dumps(
            {
                "days_out": days_out, "volume_ratio_90d": ratio.value,
                "departments_live": departments_live(campaigns, as_of),
                "stated_objective": stated_objective,
            },
            indent=2,
        )
        response = drafter.complete(
            system="You draft renewal growth-plan proposals to economic buyers.",
            prompt=load_prompt(
                "renewal_growth_proposal", evidence_json=evidence_json,
                stated_objective=stated_objective or "(not on file)",
            ),
        )
        state["growth_proposal_drafted"] = True
        autonomy, violations = _guardrail_gated(
            "renewal_commercial_proposal", tier, promotion_counts.get("renewal_commercial_proposal", 0), response
        )
        return RenewalAgentResult(
            stage="growth_proposal",
            actions=[ActionDraft(
                agent="renewal_agent", type="renewal_growth_proposal",
                payload={"draft": response.text, "llm": _usage_dict(response.usage), "guardrail_violations": violations},
                reasoning=f"T-{days_out}: next-period proposal, anchored on trajectory rather than last term's number.",
                autonomy_level=autonomy,
            )],
            exit_test_results=state, closes_play_run=False, outcome=None,
        )

    # --- Stage 4: surface objections (T-5, once) ---
    if days_out <= OBJECTIONS_DAY and not state.get("objections_drafted"):
        evidence_json = json.dumps({"days_out": days_out}, indent=2)
        response = drafter.complete(
            system="You draft short objection-surfacing messages to economic buyers ahead of renewal.",
            prompt=load_prompt("renewal_objection_check", evidence_json=evidence_json),
        )
        state["objections_drafted"] = True
        # Reuses the renewal_commercial_proposal autonomy row (same
        # commercial conversation, later checkpoint) — same precedent as
        # the Second-Creator Agent resolving against routine_check_in
        # while storing its own action.type.
        autonomy, violations = _guardrail_gated(
            "renewal_commercial_proposal", tier, promotion_counts.get("renewal_commercial_proposal", 0), response
        )
        return RenewalAgentResult(
            stage="objections",
            actions=[ActionDraft(
                agent="renewal_agent", type="renewal_objection_check",
                payload={"draft": response.text, "llm": _usage_dict(response.usage), "guardrail_violations": violations},
                reasoning=f"T-{days_out}: surfacing objections deliberately — silence at T-5 is not agreement.",
                autonomy_level=autonomy,
            )],
            exit_test_results=state, closes_play_run=False, outcome=None,
        )

    # --- Stage 5: post-renewal debrief (T+7) — always closes the play ---
    if days_out <= DEBRIEF_DAY:
        reference_date_at_open = date.fromisoformat(state["reference_date_at_open"])
        term_extended = reference_date is not None and reference_date > reference_date_at_open
        committed_volume_at_open = state.get("committed_volume_at_open")
        volume_held_or_grew = (
            committed_volume_at_open is None
            or account.committed_volume is None
            or account.committed_volume >= committed_volume_at_open
        )
        campaigns_since_reference = [
            c for c in campaigns if c.billable and c.created_at.date() > reference_date_at_open
        ]
        value_doc_current, _ = (True, None) if state.get("value_doc_current_at_open") else \
            (bool([d for d in value_docs if d.confirmed_at is not None]), None)
        growth_plan_presented = state.get("growth_proposal_drafted", False) and state.get("objections_drafted", False)

        if term_extended and volume_held_or_grew:
            outcome = "recommitment_secured"
        elif not campaigns_since_reference:
            outcome = "lost"
        else:
            outcome = "undetermined"  # still consuming, but no recorded contract extension — see README

        exit_test = {
            "recommitment_secured_at_or_above_prior_volume": term_extended and volume_held_or_grew,
            "value_doc_confirmed": value_doc_current,
            "growth_plan_presented": growth_plan_presented,
            "debrief_logged": True,
        }
        state.update(exit_test)
        return RenewalAgentResult(
            stage="debrief",
            actions=[ActionDraft(
                agent="renewal_agent", type="renewal_debrief",
                payload={"exit_test": exit_test, "outcome": outcome},
                reasoning=f"T+{-days_out}: post-renewal debrief — outcome classified as {outcome}.",
                autonomy_level=resolve_autonomy(tier, "internal_brief", 0),
            )],
            exit_test_results=state, closes_play_run=True, outcome=outcome,
        )

    return RenewalAgentResult(
        stage="waiting", actions=[], exit_test_results=state, closes_play_run=False, outcome=None,
    )
