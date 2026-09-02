"""The seven score-independent overrides, doc 02 §3 / BUILD-PROMPT.md §5.
Each caps the composite regardless of the weighted result. Every check is
a pure function of already-fetched data; the aggregator at the bottom
combines them by taking the most severe (lowest) cap among whichever
fired — a champion departure (At risk, cap 49) alongside 90 days of
silence (Critical, cap 29) correctly lands at Critical."""

from datetime import date, timedelta

from metrics.config import HealthModelConfig
from metrics.derived import billable_in_window
from metrics.types import AccountContext, CampaignFact, EscalationFact, OverrideResult, StakeholderFact


def check_champion_departed_no_successor(stakeholders: list[StakeholderFact], config: HealthModelConfig) -> OverrideResult:
    departed = [s for s in stakeholders if s.type == "champion" and s.departed_at is not None]
    if not departed:
        return OverrideResult("champion_departed_no_successor", False)
    active_champion = any(s.type == "champion" and s.departed_at is None for s in stakeholders)
    if active_champion:
        return OverrideResult("champion_departed_no_successor", False)
    return OverrideResult(
        "champion_departed_no_successor", True, config.override_caps.at_risk,
        "champion departed, no successor identified",
    )


def check_zero_campaigns_45d(
    campaigns: list[CampaignFact], contract_start: date, as_of: date, config: HealthModelConfig
) -> OverrideResult:
    last = max((c.created_at.date() for c in campaigns if c.billable), default=None)
    days_since = (as_of - (last or contract_start)).days
    if days_since >= config.override_thresholds.no_campaign_days_at_risk:
        return OverrideResult(
            "zero_campaigns_45d", True, config.override_caps.at_risk, f"no campaign in {days_since} days"
        )
    return OverrideResult("zero_campaigns_45d", False)


def check_zero_campaigns_90d(
    campaigns: list[CampaignFact], contract_start: date, as_of: date, config: HealthModelConfig
) -> OverrideResult:
    last = max((c.created_at.date() for c in campaigns if c.billable), default=None)
    days_since = (as_of - (last or contract_start)).days
    if days_since >= config.override_thresholds.no_campaign_days_critical:
        return OverrideResult(
            "zero_campaigns_90d", True, config.override_caps.critical, f"no campaign in {days_since} days"
        )
    return OverrideResult("zero_campaigns_90d", False)


def check_no_exec_sponsor_after_90_days(
    stakeholders: list[StakeholderFact], contract_start: date, as_of: date, config: HealthModelConfig
) -> OverrideResult:
    age_days = (as_of - contract_start).days
    threshold = config.override_thresholds.tenure_days_before_sponsor_single_creator_caps
    if age_days < threshold:
        return OverrideResult("no_exec_sponsor_after_90_days", False)
    has_sponsor = any(s.type == "exec_sponsor" and s.departed_at is None for s in stakeholders)
    if has_sponsor:
        return OverrideResult("no_exec_sponsor_after_90_days", False)
    return OverrideResult(
        "no_exec_sponsor_after_90_days", True, config.override_caps.watch,
        f"no exec sponsor identified after {age_days} days",
    )


def check_committed_utilization_floor(
    consumed: int, account: AccountContext, as_of: date, config: HealthModelConfig
) -> OverrideResult:
    if account.commercial_model != "committed" or not account.committed_volume or not account.commitment_end:
        return OverrideResult("committed_utilization_floor", False)
    days_left = (account.commitment_end - as_of).days
    if days_left > config.override_thresholds.days_left_in_term_for_utilization_test:
        return OverrideResult("committed_utilization_floor", False)
    utilization = consumed / account.committed_volume
    if utilization < config.override_thresholds.commitment_utilization_floor:
        return OverrideResult(
            "committed_utilization_floor", True, config.override_caps.at_risk,
            f"{utilization:.0%} utilization with {days_left}d left in term",
        )
    return OverrideResult("committed_utilization_floor", False)


def check_single_creator_whole_account(
    campaigns: list[CampaignFact], contract_start: date, as_of: date, config: HealthModelConfig
) -> OverrideResult:
    age_days = (as_of - contract_start).days
    threshold = config.override_thresholds.tenure_days_before_sponsor_single_creator_caps
    if age_days < threshold:
        return OverrideResult("single_creator_whole_account", False)
    window = billable_in_window(campaigns, as_of - timedelta(days=89), as_of)
    creators = {c.creator_id for c in window}
    if len(creators) == 1:
        return OverrideResult(
            "single_creator_whole_account", True, config.override_caps.watch,
            "single creator across the whole account past day 90",
        )
    return OverrideResult("single_creator_whole_account", False)


def check_open_escalation_unresolved(
    escalations: list[EscalationFact], as_of: date, config: HealthModelConfig
) -> OverrideResult:
    """Structurally never fires today — no escalation/ticket data source
    exists (see metrics/dimensions.py's sentiment_friction docstring).
    Real code, correct the moment that data exists."""
    threshold = config.override_thresholds.open_escalation_days_at_risk
    for e in escalations:
        if e.resolved_at is None:
            days_open = (as_of - e.opened_at.date()).days
            if days_open > threshold:
                return OverrideResult(
                    "open_escalation_unresolved", True, config.override_caps.at_risk,
                    f"escalation open {days_open} days",
                )
    return OverrideResult("open_escalation_unresolved", False)


def apply_overrides(
    *,
    campaigns: list[CampaignFact],
    stakeholders: list[StakeholderFact],
    escalations: list[EscalationFact],
    account: AccountContext,
    consumed: int,
    as_of: date,
    config: HealthModelConfig,
) -> tuple[float | None, list[OverrideResult]]:
    """Returns (cap, fired) — cap is the lowest (most severe) cap among
    fired overrides, or None if none fired."""
    checks = [
        check_champion_departed_no_successor(stakeholders, config),
        check_zero_campaigns_45d(campaigns, account.contract_start, as_of, config),
        check_zero_campaigns_90d(campaigns, account.contract_start, as_of, config),
        check_no_exec_sponsor_after_90_days(stakeholders, account.contract_start, as_of, config),
        check_committed_utilization_floor(consumed, account, as_of, config),
        check_single_creator_whole_account(campaigns, account.contract_start, as_of, config),
        check_open_escalation_unresolved(escalations, as_of, config),
    ]
    fired = [c for c in checks if c.fired]
    cap = min((c.cap for c in fired), default=None)
    return cap, fired
