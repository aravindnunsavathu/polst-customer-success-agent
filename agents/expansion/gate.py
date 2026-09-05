"""Play 4's hard qualification gate (BUILD-PROMPT.md §7): "Enforce this
gate in code, not in the prompt." All six doc-06 conditions are computed
here from data, never asserted by an LLM. Three come from usage/scoring
history already in the schema; three (named target department + owner,
champion willing to introduce, budget path understood) are CS judgment
recorded on the account plan by a human — same status as tier/quadrant/
commercial_model, never inferred (see account_plans' migration note)."""

from dataclasses import dataclass, field
from datetime import date

from metrics.derived import single_threaded_department_ids
from signals.types import CampaignFact, StakeholderFact, ValueDocFact


@dataclass(frozen=True)
class ExpansionGateResult:
    qualified: bool
    missing: list[str] = field(default_factory=list)


def healthy_streak_days(history: list[tuple[date, str | None]]) -> int | None:
    """Days the account has been continuously Healthy, ending at the most
    recent health_scores row. None if there's no scoring history at all
    (fail loud, per CLAUDE.md — never treated as "not healthy enough" and
    never treated as "healthy," since neither is true)."""
    if not history:
        return None
    ordered = sorted(history, key=lambda pair: pair[0])
    latest_date, latest_band = ordered[-1]
    if latest_band != "healthy":
        return 0
    streak_start = latest_date
    for scored_at, band in reversed(ordered):
        if band != "healthy":
            break
        streak_start = scored_at
    return (latest_date - streak_start).days


def check_expansion_gate(
    *,
    value_docs: list[ValueDocFact],
    campaigns: list[CampaignFact],
    stakeholders: list[StakeholderFact],
    health_score_history: list[tuple[date, str | None]],
    target_department: str | None,
    target_owner: str | None,
    champion_introduction: bool,
    new_budget_holder: bool | None,
    as_of: date,
    confirmed_within_days: int = 180,
    healthy_min_days: int = 60,
) -> ExpansionGateResult:
    missing = []

    confirmed = [d for d in value_docs if d.confirmed_at is not None]
    if not confirmed or (as_of - max(d.confirmed_at for d in confirmed).date()).days > confirmed_within_days:
        missing.append("no_confirmed_result_in_last_2_quarters")

    streak = healthy_streak_days(health_score_history)
    if streak is None:
        missing.append("no_health_score_history")
    elif streak < healthy_min_days:
        missing.append("not_healthy_for_60_days")

    if single_threaded_department_ids(campaigns, as_of):
        missing.append("has_single_threaded_departments")

    if not target_department or not target_owner:
        missing.append("no_named_target_department_or_owner")

    active_champion = any(s.type == "champion" and s.departed_at is None for s in stakeholders)
    if not champion_introduction or not active_champion:
        missing.append("champion_not_willing_or_departed")

    if new_budget_holder is None:
        missing.append("budget_path_not_understood")

    return ExpansionGateResult(qualified=not missing, missing=missing)
