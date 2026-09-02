**Instrumentation Requirements for Customer Success**

**To:** VP Product

**From:** VP Customer Success

**Date:** [DATE]

**Ask:** the data below, exposed in a queryable form, so CS can detect revenue decay before it hits the P&L.

# **Why this is urgent rather than nice-to-have**

Polst prices per campaign. That means churn does not arrive as a cancellation — it arrives as a gradual decline in campaign volume, often 2–3 quarters before anyone mentions a contract. Without volume trend data at the account, department, and creator level, CS cannot see decay until it is already priced in.

This is also the longest-lead-time dependency in the CS build. Everything else in the CS plan can be done with a spreadsheet and a calendar; this cannot.

**Minimum viable ask:** Tier 1 below. Six fields. If nothing else is possible this quarter, Tier 1 alone unblocks the health model.

# **Tier 1 — Blocking (needed to operate at all)**

| **#** | **Data** | **Grain** | **Refresh** | **Notes** |
| --- | --- | --- | --- | --- |
| 1 | Campaign created | Event, with account_id, department_id, creator_user_id, timestamp | Daily | The core event. Everything derives from it. |
| 2 | Campaign launched | Same, plus launched_at | Daily | Distinguishing created-vs-launched gives the abandonment rate |
| 3 | Account roster | account_id, name, contract start, term, plan/tier | Daily | Needed to compute tenure and stage |
| 4 | Department roster | department_id, account_id, name, created date, first campaign date | Daily | Term 1 of the revenue driver tree |
| 5 | User roster | user_id, account_id, department_id, role, created, last active | Daily | Term 2. Needed to detect single-threading |
| 6 | Billable campaign count per account per billing period | Account × period | Per billing cycle | Must reconcile to what Finance bills |

**Reconciliation requirement:** the campaign count CS sees must equal the campaign count Finance bills. If those diverge, every CS conversation about volume becomes a debate about the data. Please confirm which system is the source of truth.

# **Tier 2 — High value (needed for leading indicators)**

| **#** | **Data** | **Grain** | **Why** |
| --- | --- | --- | --- |
| 7 | Campaign abandoned / left in draft >[14] days | Event | Friction signal; often the first sign of a struggling new creator |
| 8 | Campaign outcome metric — *whichever of these **Polst** has*: delivery/reach, response/engagement rate, completion | Campaign | The quality guardrail. Volume without this is unsafe to optimize. **Need Product's input on which metric is meaningful.** |
| 9 | User last active timestamp | User | Detects a champion going quiet before they leave |
| 10 | User deactivated / removed | Event | **Highest-signal single event you can give me.** A departing creator in a single-creator department is an imminent revenue loss. |
| 11 | Feature usage breadth — which features/templates a campaign used | Campaign | Depth-of-use proxy |
| 12 | Time from campaign creation → launch | Derived | Friction trend |

# **Tier 3 — Valuable (optimi****z****ation and segmentation)**

| **#** | **Data** | **Why** |
| --- | --- | --- |
| 13 | Committed vs. consumed campaign volume, and commitment end date | Utilization risk — a prepaid account at 20% utilization is a renewal risk with healthy-looking revenue |
| 14 | Campaign template / type taxonomy | Which use cases drive repeat behavior |
| 15 | In-product error and failure events per account | Silent friction |
| 16 | Invitation sent / accepted | Measures whether seeding a second creator is working |
| 17 | Cost-to-serve per campaign | Whether volume growth is margin-impacting |

# **Derived metrics CS will compute (no need to build these — just the inputs)**

| **Metric** | **Formula** |
| --- | --- |
| 90-day volume ratio | campaigns(last 90d) ÷ campaigns(prior 90d) |
| Creator repeat rate | creators with ≥2 campaigns in 60d ÷ creators with ≥1 |
| Departments live | departments with ≥1 campaign in last 90d |
| Single-threaded departments | live departments with exactly 1 active creator |
| Campaign abandonment rate | created but not launched ÷ created |
| Time to first campaign | first campaign launch − contract start |
| NRR | current-period revenue from prior cohort ÷ prior-period revenue |

# **Delivery preference**

In descending order of preference:

- A CS-facing dashboard with account drill-down, refreshed daily

- Read access to a reporting DB / warehouse table, refreshed daily

- A scheduled CSV export of Tier 1 to a shared location, weekly

- A manual export on request *(acceptable only as a stopgap — please treat as temporary)*

Even option 3 unblocks the health model. **The bottleneck is the data existing and being exportable, not the interface.**

# **Requested response**

| **Item** | **Requested** |
| --- | --- |
| Which Tier 1 fields exist today and can be exported this month? |  |
| Which require new event tracking? |  |
| Rough effort estimate for Tier 1 |  |
| Source of truth for billable campaign count |  |
| Which of the #8 outcome metrics is meaningful for a Polst campaign? |  |
| Proposed delivery mechanism and date |  |
| Owner |  |

# **What CS will do with it**

So the ask is not abstract:

- Score every account weekly on the health model and act on At-risk / Critical within a week

- Detect single-threaded departments and seed a second creator before the first one leaves

- Give Product a ranked, evidence-backed list of friction points rather than anecdotes

- Give Finance a forecastable view of consumption rather than a trailing actual

- Prove, at renewal, what the customer actually got

	Polst CS · Instrumentation Requirements	Page 1 of 2