"""The decay and play triggers from BUILD-PROMPT.md §6. Pure functions —
same discipline as /metrics: no network, no database. Each decay trigger
returns a SignalCandidate or None; the caller (signals/orchestrator.py)
handles dedup against already-open signals and attaches severity from
the account's tier (§6: the response SLA is a function of tier, not of
which trigger fired)."""

from datetime import date

from metrics.derived import (
    active_creators_by_department,
    commitment_pace,
    departments_live,
    single_threaded_department_ids,
    volume_ratio_90d,
)
from metrics.dimensions import seasonality_flag
from metrics.config import HealthModelConfig
from signals.types import (
    AccountContext,
    CampaignFact,
    DepartmentFact,
    SignalCandidate,
    StakeholderFact,
    UserFact,
)


def _seasonal_dip_explains_it(campaigns: list[CampaignFact], as_of: date, config: HealthModelConfig) -> bool:
    """True when the sequential dip diverges from a healthy YoY ratio —
    i.e. the account does this every year and it isn't real decay. This
    is what makes the seasonal_dip synthetic accounts correctly NOT fire
    the volume trigger (BUILD-PROMPT.md §15's named acceptance test)."""
    flag = seasonality_flag(campaigns, as_of, config)
    if not flag or not flag["diverges"]:
        return False
    return flag["yoy_ratio"] is not None and flag["yoy_ratio"] >= 0.85


def trigger_volume_ratio_below_085(
    campaigns: list[CampaignFact], contract_start: date, as_of: date, config: HealthModelConfig
) -> SignalCandidate | None:
    age_days = (as_of - contract_start).days
    if age_days < config.onboarding_target.age_days_threshold:
        return None  # too new for a trailing-90d comparison to mean anything
    result = volume_ratio_90d(campaigns, as_of)
    if result.value is None or result.value >= 0.85:
        return None
    if _seasonal_dip_explains_it(campaigns, as_of, config):
        return None
    return SignalCandidate(
        type="decay_volume_ratio_below_085",
        reason=f"90-day volume ratio {result.value:.2f} (<0.85)",
        evidence={"volume_ratio_90d": result.value},
    )


def trigger_zero_campaigns_30d(
    campaigns: list[CampaignFact], as_of: date, threshold_days: int = 30
) -> SignalCandidate | None:
    billable = [c for c in campaigns if c.billable]
    if not billable:
        return None  # never active — not "a previously active account"
    last = max(c.created_at.date() for c in billable)
    days_since = (as_of - last).days
    if days_since < threshold_days:
        return None
    return SignalCandidate(
        type="decay_zero_campaigns_30d",
        reason=f"no campaign in {days_since} days",
        evidence={"days_since_last_campaign": days_since},
    )


def trigger_dept_zero_creators(
    departments: list[DepartmentFact], users: list[UserFact], as_of: date
) -> list[SignalCandidate]:
    """A department that has ever run a campaign but now has zero
    non-deactivated users mapped to it. Returns one candidate per
    affected department — a decay event that only touches one department
    is still a decay event per department, not a single account-wide one."""
    candidates = []
    for dept in departments:
        dept_users = [u for u in users if u.department_id == dept.id]
        if not dept_users:
            continue  # never had anyone — not a department that "dropped to zero"
        active = [u for u in dept_users if u.deactivated_at is None]
        if not active:
            candidates.append(
                SignalCandidate(
                    type="decay_dept_zero_creators",
                    reason=f"department {dept.id} has no active (non-deactivated) users left",
                    evidence={"department_id": dept.id},
                )
            )
    return candidates


def trigger_single_creator_inactive_14d(
    campaigns: list[CampaignFact], users: list[UserFact], as_of: date, inactive_days: int = 14
) -> list[SignalCandidate]:
    single_threaded = single_threaded_department_ids(campaigns, as_of)
    users_by_id = {u.id: u for u in users}
    active_by_dept = active_creators_by_department(campaigns, as_of)

    candidates = []
    for dept_id in single_threaded:
        creator_ids = active_by_dept.get(dept_id, set())
        if len(creator_ids) != 1:
            continue
        creator = users_by_id.get(next(iter(creator_ids)))
        if creator is None or creator.last_active_at is None:
            continue
        days_inactive = (as_of - creator.last_active_at.date()).days
        if days_inactive >= inactive_days:
            candidates.append(
                SignalCandidate(
                    type="decay_single_creator_inactive_14d",
                    reason=f"sole creator in department {dept_id} inactive {days_inactive} days",
                    evidence={"department_id": dept_id, "days_inactive": days_inactive},
                )
            )
    return candidates


def trigger_commitment_pace_low(
    consumed: int, account: AccountContext, as_of: date, threshold: float = 0.70
) -> SignalCandidate | None:
    result = commitment_pace(
        consumed, account.committed_volume, account.contract_start, account.commitment_end, as_of
    )
    if result.value is None or result.value >= threshold:
        return None
    return SignalCandidate(
        type="decay_commitment_pace_low",
        reason=f"commitment pace {result.value:.0%} implies <70% consumption at term end",
        evidence={"commitment_pace": result.value},
    )


def trigger_champion_departure(stakeholders: list[StakeholderFact]) -> SignalCandidate | None:
    departed = [s for s in stakeholders if s.type == "champion" and s.departed_at is not None]
    if not departed:
        return None
    active_champion = any(s.type == "champion" and s.departed_at is None for s in stakeholders)
    if active_champion:
        return None  # a successor is already in place
    return SignalCandidate(
        type="decay_champion_departure",
        reason="champion departed, no successor identified",
        evidence={},
    )


# The six decay triggers above take different inputs (campaigns, users,
# consumed volume, stakeholders, ...), so there's no single signature to
# loop over generically — signals/jobs/evaluate_triggers.py calls each
# one explicitly. trigger_dept_zero_creators and
# trigger_single_creator_inactive_14d return a list (one candidate per
# affected department); the rest return at most one candidate.


# --- Play triggers ---------------------------------------------------


def trigger_contract_signed(account: AccountContext, as_of: date, grace_days: int = 3) -> SignalCandidate | None:
    age_days = (as_of - account.contract_start).days
    if 0 <= age_days <= grace_days:
        return SignalCandidate(
            type="play1_contract_signed", reason="contract signed", evidence={"age_days": age_days}
        )
    return None


def trigger_renewal_window(
    account: AccountContext, as_of: date, next_review_date: date | None, days_before: int = 20
) -> SignalCandidate | None:
    reference = account.commitment_end or next_review_date
    if reference is None:
        return None
    days_out = (reference - as_of).days
    if 0 <= days_out <= days_before:
        return SignalCandidate(
            type="play3_renewal_window",
            reason=f"{days_out} days from renewal/commitment end",
            evidence={"days_out": days_out, "reference_date": reference.isoformat()},
        )
    return None


def trigger_expansion_candidate(
    campaigns: list[CampaignFact],
    value_docs: list,
    account: AccountContext,
    health_band: str | None,
    as_of: date,
    confirmed_within_days: int = 180,
) -> SignalCandidate | None:
    if health_band != "healthy":
        return None
    if not account.potential_departments:
        return None
    live = departments_live(campaigns, as_of)
    if live >= account.potential_departments:
        return None  # no addressable department left
    confirmed = [d for d in value_docs if d.confirmed_at is not None]
    if not confirmed:
        return None
    most_recent = max(d.confirmed_at for d in confirmed)
    if (as_of - most_recent.date()).days > confirmed_within_days:
        return None
    return SignalCandidate(
        type="play4_expansion_candidate",
        reason=f"healthy, confirmed result, {account.potential_departments - live} addressable department(s) not live",
        evidence={"departments_live": live, "potential_departments": account.potential_departments},
    )
