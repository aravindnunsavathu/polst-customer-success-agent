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
