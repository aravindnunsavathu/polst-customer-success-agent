"""Coverage-elevation triggers, doc 04 §6. Each temporarily bumps an
account's effective touch level by one tier, time-boxed so an account
never stays elevated forever (the brief's explicit warning). Two of the
six triggers ("until first value", "duration of project") don't map to
anything currently tracked at the right grain — no per-department value
confirmation, no reference/case-study project entity — so those use a
fixed, documented duration as a pragmatic stand-in rather than a precise
condition. The other four use their literal doc 04 duration."""

from datetime import date

from signals.types import CoverageElevationCandidate, DepartmentFact, StakeholderFact

TIER_ORDER = ["T4", "T3", "T2", "T1"]  # low to high touch

# Approximations for the two open-ended durations doc 04 §6 specifies
# ("until first value", "duration of project") — see module docstring.
NEW_DEPARTMENT_APPROX_DAYS = 60
REFERENCE_CANDIDATE_APPROX_DAYS = 90


def effective_tier(account_tier: str, has_active_elevation: bool) -> str:
    if not has_active_elevation:
        return account_tier
    idx = TIER_ORDER.index(account_tier) if account_tier in TIER_ORDER else 0
    return TIER_ORDER[min(idx + 1, len(TIER_ORDER) - 1)]


def check_first_90_days(account_tier: str, contract_start: date, as_of: date) -> CoverageElevationCandidate | None:
    if account_tier not in ("T1", "T2"):
        return None
    age_days = (as_of - contract_start).days
    if 0 <= age_days <= 90:
        return CoverageElevationCandidate(
            trigger="first_90_days", reason="first 90 days on a T1/T2 account", duration_days=90
        )
    return None


def check_health_critical(band: str | None) -> CoverageElevationCandidate | None:
    if band != "critical":
        return None
    return CoverageElevationCandidate(
        trigger="health_critical", reason="health is Critical", duration_days=None
    )


def check_champion_departure(stakeholders: list[StakeholderFact]) -> CoverageElevationCandidate | None:
    departed = [s for s in stakeholders if s.type == "champion" and s.departed_at is not None]
    if not departed:
        return None
    return CoverageElevationCandidate(
        trigger="champion_departure", reason="champion departure detected", duration_days=30
    )


def check_new_department_launching(
    departments: list[DepartmentFact], as_of: date, recent_days: int = 14
) -> CoverageElevationCandidate | None:
    for dept in departments:
        if 0 <= (as_of - dept.created_at.date()).days <= recent_days:
            return CoverageElevationCandidate(
                trigger="new_department_launching",
                reason=f"department {dept.id} launched {(as_of - dept.created_at.date()).days} days ago",
                duration_days=NEW_DEPARTMENT_APPROX_DAYS,
            )
    return None


def check_renewal_within_90_days(
    commitment_end: date | None, next_review_date: date | None, as_of: date
) -> CoverageElevationCandidate | None:
    reference = commitment_end or next_review_date
    if reference is None:
        return None
    days_out = (reference - as_of).days
    if 0 <= days_out <= 90:
        return CoverageElevationCandidate(
            trigger="renewal_within_90_days",
            reason=f"renewal/commitment end in {days_out} days",
            duration_days=days_out,  # "through renewal" — expires exactly at the renewal date
        )
    return None


def check_reference_candidate(band: str | None, stakeholders: list[StakeholderFact]) -> CoverageElevationCandidate | None:
    """No reference/case-study project entity exists — a Healthy account
    with a reference-willing champion is the closest proxy this schema
    supports (Stakeholder.reference_willing, doc 05's coverage checklist)."""
    if band != "healthy":
        return None
    if not any(s.type == "champion" and s.reference_willing and s.departed_at is None for s in stakeholders):
        return None
    return CoverageElevationCandidate(
        trigger="reference_candidate",
        reason="healthy account with a reference-willing champion",
        duration_days=REFERENCE_CANDIDATE_APPROX_DAYS,
    )


# Each check takes different inputs (tier, band, departments, ...), so
# there's no single uniform signature to loop over generically — the
# orchestrator calls all six of the functions above explicitly.
