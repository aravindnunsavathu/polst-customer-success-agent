"""Deterministic decay diagnosis (BUILD-PROMPT.md §7: "the agent must
localise the decay to department and creator, identify onset date").
This is factual computation from data we already have, not judgment —
per CLAUDE.md's "scoring is deterministic; judgment is LLM," only the
cause classification that follows (agents/decay/agent.py) is an LLM
step. Zero LLM/DB dependency; same discipline as /metrics and /signals."""

from dataclasses import dataclass
from datetime import date, timedelta

from metrics.config import HealthModelConfig, default_config
from metrics.derived import (
    abandonment_rate,
    active_creators_by_department,
    billable_in_window,
    commitment_pace,
    creator_repeat_rate,
    single_threaded_department_ids,
    volume_ratio_90d,
)
from metrics.dimensions import seasonality_flag
from signals.types import AccountContext, CampaignFact, DepartmentFact, StakeholderFact, UserFact


@dataclass(frozen=True)
class DecayDiagnosis:
    department_id: str | None  # None when the decline is account-wide, not localized to one dept
    creator_id: str | None  # set only when that department is single-threaded
    onset_date: date
    evidence: dict


def _month_starts(as_of: date, months_back: int) -> list[date]:
    result = []
    y, m = as_of.year, as_of.month
    for i in range(months_back, -1, -1):
        mm = m - i
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        result.append(date(yy, mm, 1))
    return result


def localize_decay(campaigns: list[CampaignFact], departments: list[DepartmentFact], as_of: date) -> str | None:
    """The department whose last-90d/prior-90d ratio dropped the most,
    among departments that actually had prior-period volume to decline
    from. None if no department has a meaningful prior baseline —
    decay reads as account-wide in that case."""
    candidates = []
    for dept in departments:
        dept_campaigns = [c for c in campaigns if c.department_id == dept.id]
        last_90 = len(billable_in_window(dept_campaigns, as_of - timedelta(days=89), as_of))
        prior_90 = len(
            billable_in_window(dept_campaigns, as_of - timedelta(days=179), as_of - timedelta(days=90))
        )
        if prior_90 == 0:
            continue
        candidates.append((dept.id, last_90 / prior_90))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[1])
    return candidates[0][0]


def estimate_onset_date(campaigns: list[CampaignFact], as_of: date) -> date:
    """First-of-month boundary, among the last 6 months, where the
    monthly count first drops below half the average of the 3 months
    before it. Falls back to the start of the trailing-90-day window (the
    same boundary the decay trigger itself used) when no clear
    single-month inflection is found — still a concrete, defensible
    date, just a coarser one. A heuristic, not changepoint detection;
    good enough to give the cause classifier something concrete to
    reason from."""
    months = _month_starts(as_of, 6)  # 7 boundaries -> 6 full months + the current partial one
    monthly = []
    for i in range(len(months) - 1):
        start, end = months[i], months[i + 1] - timedelta(days=1)
        monthly.append(len(billable_in_window(campaigns, start, end)))
    monthly.append(len(billable_in_window(campaigns, months[-1], as_of)))

    for i in range(3, len(monthly)):
        baseline = sum(monthly[i - 3 : i]) / 3
        if baseline > 0 and monthly[i] < baseline * 0.5:
            return months[i]
    return as_of - timedelta(days=89)


def diagnose_decay(
    *,
    campaigns: list[CampaignFact],
    departments: list[DepartmentFact],
    users: list[UserFact],
    stakeholders: list[StakeholderFact],
    account: AccountContext,
    as_of: date,
    config: HealthModelConfig | None = None,
) -> DecayDiagnosis:
    config = config or default_config()
    department_id = localize_decay(campaigns, departments, as_of)
    scoped_campaigns = (
        [c for c in campaigns if c.department_id == department_id] if department_id else campaigns
    )
    onset = estimate_onset_date(scoped_campaigns, as_of)
    # The scoped prior-90d count is the baseline the recovery-closure job
    # (agents/jobs/run_decay_agent.py) compares future volume against —
    # "volume back to >=90% of baseline within 90 days" is the play's
    # named exit-test condition and metric (§7).
    scoped_prior_90d_count = len(
        billable_in_window(scoped_campaigns, as_of - timedelta(days=179), as_of - timedelta(days=90))
    )

    single_threaded = set(single_threaded_department_ids(campaigns, as_of))
    creator_id = None
    if department_id in single_threaded:
        active = active_creators_by_department(campaigns, as_of).get(department_id, set())
        if len(active) == 1:
            creator_id = next(iter(active))
    creator = next((u for u in users if u.id == creator_id), None) if creator_id else None

    ratio = volume_ratio_90d(campaigns, as_of)
    pace = commitment_pace(
        sum(1 for c in campaigns if c.billable), account.committed_volume,
        account.contract_start, account.commitment_end, as_of,
    )
    abandonment = abandonment_rate(scoped_campaigns)
    repeat = creator_repeat_rate(campaigns, as_of)
    departed_champion = next(
        (s for s in stakeholders if s.type == "champion" and s.departed_at is not None), None
    )
    active_champion = any(s.type == "champion" and s.departed_at is None for s in stakeholders)
    seasonality = seasonality_flag(campaigns, as_of, config)

    evidence = {
        "department_id": department_id,
        "creator_id": creator_id,
        "onset_date": onset.isoformat(),
        "volume_ratio_90d": ratio.value,
        "scoped_prior_90d_count": scoped_prior_90d_count,
        "seasonality": seasonality,
        "creator_deactivated": bool(creator and creator.deactivated_at),
        "creator_last_active_days_ago": (
            (as_of - creator.last_active_at.date()).days if creator and creator.last_active_at else None
        ),
        "commitment_pace": pace.value,
        "abandonment_rate": abandonment.value,
        "creator_repeat_rate": repeat.value,
        "champion_departed_no_successor": bool(departed_champion and not active_champion),
        "single_threaded_department": department_id in single_threaded if department_id else False,
    }
    return DecayDiagnosis(
        department_id=department_id, creator_id=creator_id, onset_date=onset, evidence=evidence
    )
