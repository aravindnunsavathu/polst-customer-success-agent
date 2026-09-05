const API_URL = process.env.API_URL ?? "http://localhost:8000";

export type HealthScoreSummary = {
  scored_at: string;
  final_score: number | null;
  composite_score: number | null;
  band: string | null;
  volume_trajectory_score: number | null;
  breadth_score: number | null;
  value_realisation_score: number | null;
  campaign_quality_score: number | null;
  relationship_coverage_score: number | null;
  sentiment_friction_score: number | null;
  applied_overrides: string[];
  null_reasons: Record<string, string>;
  model_version: string;
};

export type AccountSummary = {
  account_id: string;
  name: string;
  tier: string;
  quadrant: string;
  commercial_model: string;
  latest_score: HealthScoreSummary | null;
  trend: "up" | "down" | "flat" | null;
  next_review_date: string | null;
  open_signal_count: number;
};

export type SignalOut = {
  id: string;
  account_id: string;
  account_name: string;
  type: string;
  reason: string;
  evidence: Record<string, unknown>;
  severity: string;
  fired_at: string;
  sla_due_at: string | null;
  priority_score: number;
};

export type PlayRunOut = {
  id: string;
  play: string;
  opened_at: string;
  closed_at: string | null;
  outcome: string | null;
  cause_classification: string | null;
};

export type ActionOut = {
  id: string;
  play_run_id: string | null;
  agent: string;
  type: string;
  payload: Record<string, unknown>;
  reasoning: string;
  autonomy_level: string;
  status: string;
  approved_by: string | null;
  rejection_reason_category: string | null;
  rejection_reason_detail: string | null;
  created_at: string;
};

export type StakeholderOut = {
  name: string;
  role: string | null;
  type: string;
  relationship_strength: string;
  last_contact_at: string | null;
  departed_at: string | null;
  reference_willing: boolean;
};

export type DepartmentVolumeOut = {
  department_id: string;
  name: string;
  live_last_90d: boolean;
  active_creators_last_90d: number;
  campaigns_last_90d: number;
  campaigns_prior_90d: number;
  first_campaign_at: string | null;
};

export type ValueDocOut = {
  result: string;
  metric: string;
  confirmed_by: string | null;
  confirmed_at: string | null;
  created_at: string;
};

export type AccountPlanOut = {
  stated_objective: string | null;
  stated_objective_missing: boolean;
  how_measured: string | null;
  baseline: string | null;
  top_risk: string | null;
  top_opportunity: string | null;
  last_refreshed: string | null;
};

export type AccountDetail = AccountSummary & {
  contract_start: string;
  committed_volume: number | null;
  commitment_end: string | null;
  potential_departments: number | null;
  health_history: HealthScoreSummary[];
  stakeholders: StakeholderOut[];
  departments: DepartmentVolumeOut[];
  value_docs: ValueDocOut[];
  account_plan: AccountPlanOut;
  open_signals: SignalOut[];
  play_runs: PlayRunOut[];
};

export async function fetchPortfolio(): Promise<AccountSummary[]> {
  const res = await fetch(`${API_URL}/accounts`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch portfolio: ${res.status}`);
  return res.json();
}

export async function fetchAccount(id: string): Promise<AccountDetail> {
  const res = await fetch(`${API_URL}/accounts/${id}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch account ${id}: ${res.status}`);
  return res.json();
}

export async function fetchSignals(): Promise<SignalOut[]> {
  const res = await fetch(`${API_URL}/signals`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch signals: ${res.status}`);
  return res.json();
}

export async function fetchActions(status?: string): Promise<ActionOut[]> {
  const url = new URL(`${API_URL}/actions`);
  if (status) url.searchParams.set("status", status);
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch actions: ${res.status}`);
  return res.json();
}

export type PlayLogActionOut = {
  id: string;
  agent: string;
  type: string;
  autonomy_level: string;
  status: string;
  reasoning: string;
  created_at: string;
};

export type PlayRunLogOut = {
  id: string;
  account_id: string;
  account_name: string;
  tier: string;
  play: string;
  opened_at: string;
  closed_at: string | null;
  outcome: string | null;
  cause_classification: string | null;
  exit_test_results: Record<string, unknown>;
  actions: PlayLogActionOut[];
};

export async function fetchPlays(params?: { play?: string; status?: string }): Promise<PlayRunLogOut[]> {
  const url = new URL(`${API_URL}/plays`);
  if (params?.play) url.searchParams.set("play", params.play);
  if (params?.status) url.searchParams.set("status", params.status);
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch plays: ${res.status}`);
  return res.json();
}

export type PortfolioReportOut = {
  id: string;
  report_type: string;
  period_start: string;
  period_end: string;
  generated_at: string;
  data: Record<string, any>;
  narrative: string | null;
};

export async function fetchReports(type?: string): Promise<PortfolioReportOut[]> {
  const url = new URL(`${API_URL}/reports`);
  if (type) url.searchParams.set("type", type);
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch reports: ${res.status}`);
  return res.json();
}
