"""Pure input/output shapes for trigger evaluation. Reuses metrics'
already-pure dataclasses where the shape matches (CampaignFact,
StakeholderFact, ValueDocFact, AccountContext, UserFact) rather than
duplicating them — /signals depends on /metrics, never the reverse."""

from dataclasses import dataclass, field
from datetime import datetime

from metrics.types import (  # noqa: F401 — re-exported for callers
    AccountContext,
    CampaignFact,
    StakeholderFact,
    UserFact,
    ValueDocFact,
)


@dataclass(frozen=True)
class DepartmentFact:
    id: str
    created_at: datetime
    # Only the Expansion Agent needs this — matching an account plan's
    # free-text expansion_target_department against a live department by
    # name, since play_runs/signals have no department_id to key off.
    # Optional so every other DepartmentFact() call site is unaffected.
    name: str | None = None


@dataclass(frozen=True)
class SignalCandidate:
    """What a trigger function found — not yet a DB row. Severity isn't
    part of this: per BUILD-PROMPT.md §6 the response SLA is purely a
    function of account tier, not the trigger itself, so the caller
    (signals/orchestrator.py) attaches severity from the account."""

    type: str
    reason: str
    evidence: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CoverageElevationCandidate:
    trigger: str
    reason: str
    duration_days: int | None  # None = condition-based, not calendar-based
