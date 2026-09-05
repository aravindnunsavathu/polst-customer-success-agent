"""The Second-Creator Agent (BUILD-PROMPT.md §7): "detect single-threaded
live departments, and drive a seeding sequence before the creator
leaves. It is the cheapest prevention in the whole model." A background
scan across every account's live departments each night — not tied to a
play_run or signal the way Decay/Onboarding are, since single-threading
is a standing risk, not a discrete triggering event."""

import json
from dataclasses import dataclass

from agents.autonomy import resolve_autonomy
from agents.guardrails import check_volume_pushing
from agents.llm.base import LLMProvider, LLMUsage
from agents.prompts import load_prompt
from core.enums import AutonomyLevel
from metrics.derived import active_creators_by_department
from signals.types import CampaignFact, UserFact


@dataclass(frozen=True)
class ActionDraft:
    agent: str
    type: str
    payload: dict
    reasoning: str
    autonomy_level: AutonomyLevel


@dataclass(frozen=True)
class SecondCreatorCandidate:
    department_id: str
    sole_creator_id: str


def _usage_dict(usage: LLMUsage) -> dict:
    return {
        "provider": usage.provider, "model": usage.model, "latency_ms": usage.latency_ms,
        "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens, "cost_usd": usage.cost_usd,
    }


def find_single_threaded_departments(campaigns: list[CampaignFact], as_of) -> list[SecondCreatorCandidate]:
    active_by_dept = active_creators_by_department(campaigns, as_of)
    return [
        SecondCreatorCandidate(department_id=dept_id, sole_creator_id=next(iter(creators)))
        for dept_id, creators in active_by_dept.items()
        if len(creators) == 1
    ]


def draft_seeding_action(
    *,
    candidate: SecondCreatorCandidate,
    tier: str,
    drafter: LLMProvider,
    promotion_count: int = 0,
) -> ActionDraft:
    evidence_json = json.dumps(
        {"department_id": candidate.department_id, "creator_id": candidate.sole_creator_id}, indent=2
    )
    response = drafter.complete(
        system="You draft short messages asking a Polst power user to bring in a colleague.",
        prompt=load_prompt("second_creator_seeding", evidence_json=evidence_json),
    )
    autonomy = resolve_autonomy(tier, "routine_check_in", promotion_count)
    violations = check_volume_pushing(response.text)
    if violations and autonomy == AutonomyLevel.AUTO:
        autonomy = AutonomyLevel.DRAFT

    return ActionDraft(
        agent="second_creator_agent",
        type="second_creator_seeding",
        payload={
            "draft": response.text,
            "department_id": candidate.department_id,
            "llm": _usage_dict(response.usage),
            "guardrail_violations": violations,
        },
        reasoning=(
            f"Department {candidate.department_id} is single-threaded "
            f"(sole active creator {candidate.sole_creator_id}) — seeding a second creator "
            f"before they leave, the cheapest prevention in the model."
        ),
        autonomy_level=autonomy,
    )
