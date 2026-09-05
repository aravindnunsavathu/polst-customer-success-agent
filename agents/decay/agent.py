"""The Decay Agent (BUILD-PROMPT.md §7, Play 2) — "the highest-value
agent in the system." Sequence matters: diagnose (deterministic) before
classifying cause (LLM) before ever drafting outreach (LLM, gated by
autonomy + a guardrail check). Pure orchestration — no database, no
ORM. The caller (agents/jobs/run_decay_agent.py) turns this function's
plain-dict result into real Action/FeedbackItem/PlayRun rows, filling in
IDs this function has no business knowing about."""

import json
from dataclasses import dataclass
from datetime import date

from agents.autonomy import resolve_autonomy
from agents.decay.diagnosis import DecayDiagnosis, diagnose_decay
from agents.guardrails import check_volume_pushing
from agents.llm.base import LLMProvider, LLMUsage
from agents.prompts import load_prompt
from core.enums import AutonomyLevel
from signals.types import AccountContext, CampaignFact, DepartmentFact, StakeholderFact, UserFact

CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "cause": {
            "type": "string",
            "enum": [
                "person_left",
                "never_got_value",
                "product_friction",
                "seasonal",
                "budget_priority_shift",
                "competitive_displacement",
            ],
        },
        "confidence": {"type": "string"},
    },
    "required": ["cause", "confidence"],
}

# doc 06's cause table: creator-level causes get a creator draft;
# product friction is routed internally, not a customer contact at all;
# budget/competitive causes get the stricter exec-to-exec autonomy row
# (§9), not the generic "decay outreach — buyer level" row. Seasonal is
# handled as a first-class branch before this mapping is even consulted.
CAUSE_TO_ACTION_TYPE = {
    "person_left": "decay_outreach_creator",
    "never_got_value": "decay_outreach_creator",
    "product_friction": "route_to_product",
    "budget_priority_shift": "exec_to_exec_budget_or_displacement",
    "competitive_displacement": "exec_to_exec_budget_or_displacement",
}

CLASSIFICATION_SYSTEM = (
    "You classify customer decay causes from structured evidence. Never invent facts not given."
)
DRAFTING_SYSTEM = (
    "You draft short, warm customer check-ins. Never mention internal usage statistics "
    "or ask the customer to run more campaigns."
)


@dataclass(frozen=True)
class ActionDraft:
    agent: str
    type: str
    payload: dict
    reasoning: str
    autonomy_level: AutonomyLevel


@dataclass(frozen=True)
class FeedbackItemDraft:
    source: str
    verbatim: str
    tag: str
    routed_to: str


@dataclass(frozen=True)
class DecayAgentResult:
    outcome: str  # "no_intervention_seasonal" | "action_created" | "routed_internally"
    cause: str
    diagnosis: DecayDiagnosis
    action: ActionDraft | None
    feedback_item: FeedbackItemDraft | None
    cause_classification: str
    exit_test_results: dict
    closes_play_run: bool


def _usage_dict(usage: LLMUsage) -> dict:
    return {
        "provider": usage.provider,
        "model": usage.model,
        "latency_ms": usage.latency_ms,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cost_usd": usage.cost_usd,
    }


def _baseline_fields(diagnosis: DecayDiagnosis) -> dict:
    """What the recovery-closure job (agents/jobs/run_decay_agent.py)
    needs later to answer "is volume back to >=90% of baseline within 90
    days" — the play's named exit-test condition and metric (§7)."""
    return {
        "department_id": diagnosis.department_id,
        "baseline_prior_90d_count": diagnosis.evidence["scoped_prior_90d_count"],
        "onset_date": diagnosis.onset_date.isoformat(),
    }


def run_decay_agent(
    *,
    campaigns: list[CampaignFact],
    departments: list[DepartmentFact],
    users: list[UserFact],
    stakeholders: list[StakeholderFact],
    account: AccountContext,
    stated_objective: str | None,
    how_measured: str | None,
    tier: str,
    as_of: date,
    classifier: LLMProvider,
    drafter: LLMProvider,
    approved_without_edit_count: int = 0,
) -> DecayAgentResult:
    diagnosis = diagnose_decay(
        campaigns=campaigns, departments=departments, users=users,
        stakeholders=stakeholders, account=account, as_of=as_of,
    )

    classify_response = classifier.complete(
        system=CLASSIFICATION_SYSTEM,
        prompt=load_prompt("decay_cause_classification", evidence_json=json.dumps(diagnosis.evidence, indent=2)),
        response_schema=CLASSIFICATION_SCHEMA,
    )
    cause = classify_response.parsed["cause"]
    llm_meta = {"classification": _usage_dict(classify_response.usage)}

    if cause == "seasonal":
        return DecayAgentResult(
            outcome="no_intervention_seasonal",
            cause=cause,
            diagnosis=diagnosis,
            action=None,
            feedback_item=None,
            cause_classification=cause,
            exit_test_results={
                "cause_classified": True,
                "action_agreed_with_date": False,
                "note": "seasonal pattern — no intervention, baseline adjusted",
            },
            closes_play_run=True,
        )

    if cause == "product_friction":
        action = ActionDraft(
            agent="decay_agent",
            type="route_to_product",
            payload={"evidence": diagnosis.evidence, "llm": llm_meta},
            reasoning=(
                f"Classified as product friction (onset {diagnosis.onset_date}, "
                f"abandonment rate {diagnosis.evidence.get('abandonment_rate')}). "
                f"Routed to Product with evidence rather than contacting the customer — "
                f"this is an internal fix/workaround, not a CS conversation."
            ),
            autonomy_level=resolve_autonomy(tier, "internal_brief", approved_without_edit_count),
        )
        feedback_item = FeedbackItemDraft(
            source="decay_agent",
            verbatim=(
                f"Decay diagnosed as product friction in department {diagnosis.department_id} "
                f"(onset {diagnosis.onset_date}): abandonment rate "
                f"{diagnosis.evidence.get('abandonment_rate')}."
            ),
            tag="product_friction",
            routed_to="Product",
        )
        return DecayAgentResult(
            outcome="routed_internally",
            cause=cause,
            diagnosis=diagnosis,
            action=action,
            feedback_item=feedback_item,
            cause_classification=cause,
            exit_test_results={
                "cause_classified": True,
                "action_agreed_with_date": False,
                **_baseline_fields(diagnosis),
            },
            closes_play_run=False,
        )

    action_type = CAUSE_TO_ACTION_TYPE[cause]
    autonomy = resolve_autonomy(tier, action_type, approved_without_edit_count)

    draft_text = None
    guardrail_violations: list[str] = []
    if autonomy not in (AutonomyLevel.HUMAN_WRITES, AutonomyLevel.NEVER):
        # Folded into the evidence dict (not just the template's separate
        # $stated_objective line) so a JSON-block parser — a real LLM
        # reading it, or HeuristicLLMProvider's regex — reliably sees it.
        draft_evidence = {
            **diagnosis.evidence,
            "stated_objective": stated_objective,
            "how_measured": how_measured,
        }
        draft_prompt = load_prompt(
            "decay_outreach_creator",
            evidence_json=json.dumps(draft_evidence, indent=2),
            stated_objective=stated_objective or "(not on file)",
            how_measured=how_measured or "(not on file)",
        )
        draft_response = drafter.complete(system=DRAFTING_SYSTEM, prompt=draft_prompt)
        draft_text = draft_response.text
        llm_meta["drafting"] = _usage_dict(draft_response.usage)
        guardrail_violations = check_volume_pushing(draft_text)
        if guardrail_violations and autonomy == AutonomyLevel.AUTO:
            # Never let a flagged draft go out un-reviewed, regardless of
            # the promotion status of this action type.
            autonomy = AutonomyLevel.DRAFT

    reasoning = (
        f"Classified as {cause} (onset {diagnosis.onset_date}, "
        f"department {diagnosis.department_id or 'account-wide'}"
        + (f", creator {diagnosis.creator_id}" if diagnosis.creator_id else "")
        + f"). {classify_response.parsed.get('confidence', '')}"
    )
    if guardrail_violations:
        reasoning += f" GUARDRAIL FLAGGED: draft matched volume-pushing phrases {guardrail_violations}."

    action = ActionDraft(
        agent="decay_agent",
        type=action_type,
        payload={
            "draft": draft_text,
            "evidence": diagnosis.evidence,
            "llm": llm_meta,
            "guardrail_violations": guardrail_violations,
        },
        reasoning=reasoning,
        autonomy_level=autonomy,
    )
    return DecayAgentResult(
        outcome="action_created",
        cause=cause,
        diagnosis=diagnosis,
        action=action,
        feedback_item=None,
        cause_classification=cause,
        exit_test_results={
            "cause_classified": True,
            "action_agreed_with_date": False,
            **_baseline_fields(diagnosis),
        },
        closes_play_run=False,
    )
