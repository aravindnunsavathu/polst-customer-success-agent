"""Pure input/output shapes for the metrics engine. Zero ORM or database
dependency by design — /metrics must be importable and testable with no
network, no credentials, no AWS client (BUILD-PROMPT.md §11). Whatever
bridges real Postgres rows into these types lives outside this package
(see core/jobs/score_portfolio.py)."""

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class CampaignFact:
    id: str
    department_id: str
    creator_id: str
    created_at: datetime
    launched_at: datetime | None
    billable: bool = True


@dataclass(frozen=True)
class DepartmentFact:
    id: str
    created_at: datetime


@dataclass(frozen=True)
class UserFact:
    id: str
    department_id: str | None
    created_at: datetime
    last_active_at: datetime | None
    deactivated_at: datetime | None


@dataclass(frozen=True)
class StakeholderFact:
    type: str  # economic_buyer | exec_sponsor | champion | creator | blocker
    last_contact_at: datetime | None
    departed_at: datetime | None
    reference_willing: bool = False


@dataclass(frozen=True)
class ValueDocFact:
    created_at: datetime
    confirmed_at: datetime | None


@dataclass(frozen=True)
class EscalationFact:
    """No schema table backs this yet — every caller passes an empty list
    until Support/CS instruments escalations. See dimensions.py and
    overrides.py for how absence is handled (never defaulted to "clean")."""

    opened_at: datetime
    resolved_at: datetime | None


@dataclass(frozen=True)
class AccountContext:
    contract_start: date
    commercial_model: str  # "ad_hoc" | "committed"
    committed_volume: int | None
    commitment_end: date | None
    potential_departments: int | None


@dataclass(frozen=True)
class MetricResult:
    """A derived metric's value, or None with a named reason — never a
    default (CLAUDE.md's fail-loud rule)."""

    value: float | None
    reason: str | None = None


@dataclass(frozen=True)
class OverrideResult:
    name: str
    fired: bool
    cap: float | None = None
    reason: str | None = None


@dataclass(frozen=True)
class DimensionScore:
    """A health-score dimension's 0-100 score, or None with a named
    reason. `basis` is an optional human-readable note on which rule
    produced a non-null score (e.g. "onboarding target" vs "sequential
    ratio") — useful for the account screen's audit trail, never used for
    scoring logic itself."""

    score: float | None
    reason: str | None = None
    basis: str | None = None


@dataclass(frozen=True)
class HealthScoreResult:
    dimension_scores: dict[str, DimensionScore]
    composite_score: float | None
    final_score: float | None
    band: str | None
    applied_overrides: list[OverrideResult]
    null_reasons: dict[str, str]
    seasonality: dict | None
    model_version: str
