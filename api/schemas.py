"""Read-only API response shapes for the Phase 2 console. Deliberately
plain — these mirror what the Portfolio and Account screens (§8) need,
not the full canonical schema."""

from datetime import date, datetime

from pydantic import BaseModel


class HealthScoreSummary(BaseModel):
    scored_at: datetime
    final_score: float | None
    composite_score: float | None
    band: str | None
    volume_trajectory_score: float | None
    breadth_score: float | None
    value_realisation_score: float | None
    campaign_quality_score: float | None
    relationship_coverage_score: float | None
    sentiment_friction_score: float | None
    applied_overrides: list[str]
    null_reasons: dict[str, str]
    model_version: str


class AccountSummary(BaseModel):
    account_id: str
    name: str
    tier: str
    quadrant: str
    commercial_model: str
    latest_score: HealthScoreSummary | None
    trend: str | None  # "up" | "down" | "flat" | None (insufficient history)
    next_review_date: date | None
    open_signal_count: int


class SignalOut(BaseModel):
    id: str
    account_id: str
    account_name: str
    type: str
    reason: str
    evidence: dict
    severity: str
    fired_at: datetime
    sla_due_at: datetime | None
    priority_score: float


class PlayRunOut(BaseModel):
    id: str
    play: str
    opened_at: datetime
    closed_at: datetime | None
    outcome: str | None
    cause_classification: str | None


class ActionOut(BaseModel):
    id: str
    play_run_id: str | None
    agent: str
    type: str
    payload: dict
    reasoning: str
    autonomy_level: str
    status: str
    approved_by: str | None
    rejection_reason_category: str | None
    rejection_reason_detail: str | None
    created_at: datetime


class ApproveRequest(BaseModel):
    approved_by: str


class RejectRequest(BaseModel):
    rejection_reason_category: str
    rejection_reason_detail: str | None = None


class StakeholderOut(BaseModel):
    name: str
    role: str | None
    type: str
    relationship_strength: str
    last_contact_at: datetime | None
    departed_at: datetime | None
    reference_willing: bool


class DepartmentVolumeOut(BaseModel):
    department_id: str
    name: str
    live_last_90d: bool
    active_creators_last_90d: int
    campaigns_last_90d: int
    campaigns_prior_90d: int
    first_campaign_at: datetime | None


class ValueDocOut(BaseModel):
    result: str
    metric: str
    confirmed_by: str | None
    confirmed_at: datetime | None
    created_at: datetime


class AccountPlanOut(BaseModel):
    stated_objective: str | None
    stated_objective_missing: bool  # doc 05 §3 — the single most important gap, surfaced not hidden
    how_measured: str | None
    baseline: str | None
    top_risk: str | None
    top_opportunity: str | None
    last_refreshed: datetime | None


class AccountDetail(BaseModel):
    account_id: str
    name: str
    tier: str
    quadrant: str
    commercial_model: str
    contract_start: date
    committed_volume: int | None
    commitment_end: date | None
    next_review_date: date | None
    potential_departments: int | None
    latest_score: HealthScoreSummary | None
    health_history: list[HealthScoreSummary]
    stakeholders: list[StakeholderOut]
    departments: list[DepartmentVolumeOut]
    value_docs: list[ValueDocOut]
    account_plan: AccountPlanOut  # always present — missing objective is a flag, not a null
    open_signals: list[SignalOut]
    play_runs: list[PlayRunOut]


class PortfolioReportOut(BaseModel):
    id: str
    report_type: str
    period_start: date
    period_end: date
    generated_at: datetime
    data: dict
    narrative: str | None
