# Claude Code Build Prompt — Polst CS Agent Platform

> **How to use this file.** Paste the whole thing into Claude Code as your opening message, with the Polst CS Foundations Pack (docs 00–06) and the two trackers attached to the session. Edit the five bracketed `[DECIDE]` items first — they are the only places where I have guessed on your behalf.
>
> **Target environment: AWS.** See §11 for the deployment shape and §11a for model strategy. §16.6 is the one platform decision I need from you before the agent layer is built.

---

## 0. Before you write any code

You are the founding engineer on an internal platform. Do these three things first, in order:

1. Read the attached CS Foundations Pack (docs 00–06) end to end. It is the functional specification. This prompt is the technical brief; where the two conflict, ask rather than assume.
2. Produce a written implementation plan — architecture, data model, milestone breakdown, and a list of every assumption you are making. Stop and wait for my approval.
3. Then build in the phases at §12, one phase at a time, with a working demo at the end of each.

Do not scaffold a full application in one pass. I would rather review four small correct systems than one large plausible one.

---

## 1. What we are building and why

Polst is a seed-stage company selling a binary-poll product used by restaurant, QSR, and enterprise teams to make menu, pricing, promotion, and internal decisions. **It prices per campaign — roughly $8,000/month per department for 50 campaigns.** That single fact determines the whole design:

- **Churn is not an event, it is decay.** An account that falls from 40 campaigns/quarter to 8 has lost 80% of its value while still appearing on the retained-logo list. The alarm is a volume trend against the account's own baseline, not a renewal date.
- **Retention and expansion are one variable:** campaign volume over time.
- **Revenue has a driver tree:** `departments live × active creators per department × campaigns per creator × price`. Each term is a distinct motion.
- **Single-threading is the dominant silent failure.** A department with one active creator is a department whose revenue leaves when that person does.

We are building the system that detects all of this early and does most of the resulting work, so that one VP of CS can cover a portfolio that would otherwise need a team.

**What the system is:** an agentic operations platform that ingests product and billing data, scores every account deterministically, fires triggers, runs the four core plays, drafts and (at defined autonomy levels) sends customer communication, and logs every outcome so the model improves.

**What the system is not:** an autonomous relationship owner. See §9.

---

## 2. Operating principles — non-negotiable

These are constraints on the implementation, not aspirations. Enforce them in code and in tests.

1. **Scoring is deterministic; judgment is LLM.** Health scores, trigger thresholds, and derived metrics are computed in plain code from SQL. An LLM must never produce a health score, a volume ratio, or a percentage. LLMs classify causes, synthesise briefs, draft prose, and propose actions.
2. **Fail loud on missing data.** If an input to a score is absent, the score is `null` with a named reason — never imputed, never defaulted to a middle value. A confident score built on absent data is the single most dangerous output this system can produce.
3. **Every agent action is logged with its full input context and stated reasoning**, and is reconstructible after the fact. If we cannot audit why an agent contacted a customer, we cannot run the function.
4. **Every play run records an outcome against its exit test.** A play we cannot evaluate is a ritual. This is the raw material for §10.
5. **No volume-pushing.** There is a standing incentive to drive campaign count for its own sake; campaigns that produce no customer result do not repeat. Encode this as a hard guardrail: no agent may generate outreach whose primary call to action is "run more campaigns." Outreach leads with the customer's stated objective. Add an automated check on drafted copy that flags violations before they reach the approval queue.
6. **Human approval by default.** In v1 no customer-facing message sends without a human click, except where §9 explicitly says otherwise.
7. **The customer's business result is the root outcome.** Every account record carries the objective in the customer's own words. An account where that field is empty is a red flag surfaced in the UI, not a blank cell.

---

## 3. Architecture

Five layers. Keep them separable — I expect to replace the agent layer's model provider and prompts frequently, and I do not want that to touch scoring.

```
  [ Ingestion ]   product events, billing, CRM, email/calendar, support
        |
  [ Warehouse ]   canonical Postgres schema, daily refresh, full history
        |
  [ Metrics ]     deterministic derived metrics + health scores (pure functions, tested)
        |
  [ Signals ]     trigger evaluation -> typed Signal records with severity + SLA clock
        |
  [ Agents ]      orchestrator + specialist agents; propose Actions
        |
  [ Actions ]     approval queue -> execution (email, ticket, doc write, task)
        |
  [ Console ]     portfolio view, account view, approval queue, play log, calibration
```

**Critical separation:** the Metrics layer must be importable and runnable with zero LLM calls and zero network access, so it can be unit-tested against fixtures. Golden-file tests on every scoring function.

---

## 4. Data model

Build a canonical schema in Postgres. Ingestion adapters normalise into it; nothing downstream reads a vendor shape directly.

**Core entities (from the instrumentation spec, doc 03 Tier 1 — these are blocking):**

- `accounts` — id, name, contract_start, term, plan, commercial_model (`ad_hoc` | `committed`), committed_volume, commitment_end, tier, quadrant, potential_departments, potential_creators_per_dept, potential_campaigns_per_creator
- `departments` — id, account_id, name, created_at, first_campaign_at
- `users` — id, account_id, department_id, role, created_at, last_active_at, deactivated_at
- `campaigns` — id, account_id, department_id, creator_user_id, created_at, launched_at (nullable), template_type, billable
- `billing_periods` — account_id, period, billable_campaign_count

**Reconciliation requirement:** the campaign count this system reports must equal the count Finance bills. Build a nightly reconciliation job that diffs the two and raises a blocking alert on divergence. Every conversation about volume becomes a debate about the data otherwise. `Assume billable campaign count is also available in the same Postgres database being used for this application.`

**Tier 2 / Tier 3 (build the columns now, populate when available):**
- `campaign_outcomes` — campaign_id, response_rate, completion_rate, reach
- `user_events` — deactivation, invitation sent/accepted, last_active
- `product_errors` — account_id, event, timestamp

**CS-owned entities:**

- `stakeholders` — account_id, name, role, type (`economic_buyer` | `exec_sponsor` | `champion` | `creator` | `blocker`), relationship_strength, last_contact_at, departed_at
- `account_plans` — one per account: stated_objective (customer's words), how_measured, baseline, potential_basis, top_risk, top_opportunity, last_refreshed
- `value_docs` — account_id, result, metric, confirmed_by, confirmed_at, evidence_url
- `health_scores` — account_id, scored_at, per-dimension scores, composite, band, applied_overrides[], null_reasons[]
- `signals` — account_id, type, severity, fired_at, sla_due_at, resolved_at, resolution
- `play_runs` — account_id, play, opened_at, closed_at, exit_test_results (jsonb), outcome, cause_classification
- `actions` — play_run_id, agent, type, payload, reasoning, autonomy_level, status, approved_by, executed_at
- `feedback_items` — account_id, source, verbatim, tag, routed_to, linked_ticket

Everything is append-only with `valid_from`/`valid_to` on mutable dimensions. I need to reconstruct what the system believed about an account two quarters ago (see §10).

---

## 5. Metrics engine — implement exactly

Pure functions, unit-tested, no LLM. Reproduce the formulas below verbatim; the specific numbers are the current model version and must be config-driven so I can retune them without a deploy.

**Derived metrics:**
```
volume_ratio_90d        = campaigns(last 90d) / campaigns(prior 90d)
creator_repeat_rate     = creators with >=2 campaigns in 60d / creators with >=1
departments_live        = departments with >=1 campaign in last 90d
single_threaded_depts   = live departments with exactly 1 active creator
abandonment_rate        = created but not launched / created
time_to_first_campaign  = first launch - contract_start
commitment_pace         = consumed / (committed * elapsed_fraction_of_term)
nrr                     = current-period revenue from prior cohort / prior-period revenue from that cohort
```

**Health score — six weighted dimensions, 0–100 each:**

| Dimension | Weight | Scoring |
|---|---|---|
| Volume trajectory | 30% | ratio ≥1.25→100 · 1.00–1.24→85 · 0.85–0.99→65 · 0.70–0.84→40 · 0.50–0.69→20 · <0.50→0. Accounts <180 days score against onboarding plan target instead. |
| Breadth | 20% | `50 × min(depts_live/depts_target,1) + 50 × min(pct_depts_with_2plus_creators,1)` |
| Value realisation | 20% | confirmed result <90d→100 · <180d→70 · documented but stale or unconfirmed→40 · none→0 |
| Campaign quality | 15% | percentile vs cohort on the chosen quality metric; fall back to a 0/50/100 rubric below 15 accounts in cohort |
| Relationship coverage | 10% | +20 each, capped 100: economic buyer identified · exec sponsor identified · exec sponsor engaged this quarter · ≥3 contacts mapped · reference-willing champion |
| Sentiment & friction | 5% | 100 no escalations & tickets flat/falling · 50 elevated or one resolved escalation · 0 open escalation or sharply rising |

**Bands:** Healthy 75–100 · Watch 50–74 · At risk 30–49 · Critical 0–29.

**Overrides — these cap the composite regardless of the weighted result. Implement as a post-processing step that records which override applied:**

| Condition | Cap |
|---|---|
| Champion departed, no successor | At risk |
| Zero campaigns in 45 days | At risk |
| Zero campaigns in 90 days | Critical |
| No exec sponsor after day 90 | Watch |
| Committed utilisation <40% with <90 days of term left | At risk |
| Single creator across whole account past day 90 | Watch |
| Open escalation unresolved >30 days | At risk |

**Seasonality flag:** if an account has ≥12 months of history, compute the year-over-year comparison alongside the 90-day sequential one and flag divergence. Sequential comparison on a seasonal account is our most likely source of systematic false alarms. `Assume Polst customers have seasonal campaign patterns.`

---

## 6. Signals layer

Evaluate triggers nightly. Each fires a typed `signal` with a severity and an SLA clock, and the clock is the thing the console shows me — lead time between trigger and intervention is a tracked metric, not an afterthought.

**Decay triggers (any one):** volume_ratio_90d < 0.85 · zero campaigns in 30 days for a previously active account · a live department drops to zero creators · a single-creator department's creator inactive 14 days · commitment pace implying <70% consumption at term end · champion departure detected.

**Response SLA:** Tier 1 within 3 days · Tier 2 within 10 days · Tier 3 automated sequence immediately.

**Other triggers:** contract signed (Play 1) · 20 days before renewal or commitment end (Play 3) · Healthy + confirmed result + addressable department not live (Play 4) · first 90 days on any T2+ account, health goes Critical, champion departs, new department launching, renewal within 90 days, reference candidate (each elevates coverage one level, time-boxed — implement the expiry, or accounts stay elevated forever).

---

## 7. The agents

One orchestrator routes signals to specialists. Each specialist is a Claude agent with a tightly scoped toolset, a written objective, an exit test, and a metric. Use tool use for all data access — no agent gets raw database credentials, and every tool call is logged.

**Orchestrator.** Consumes signals, deduplicates (one account with four signals gets one coordinated intervention, not four emails), assigns priority by tier × severity × revenue at risk, opens `play_runs`, and refuses to open a second concurrent customer-facing play on the same account.

**1. Onboarding Agent (Play 1).** Goal is a *customer-confirmed result*, not a launched campaign. Targets: first campaign by day 14, confirmed result by day 45. Runs the day −3 → day 45 sequence: validate the Sales handoff against the checklist and **refuse an incomplete one back to Sales** (build this as a real workflow state, not a warning); prepare the kickoff brief; draft the written success criteria for customer confirmation; track the second-creator requirement per department; prompt the value-confirmation conversation at ~day 45; seed the expansion question. Exit test: result documented and customer-confirmed, ≥2 active creators, second campaign customer-initiated, economic buyer has seen the result. **Do not let the agent close this play at launch** — that failure mode is the reason volume flattens at one campaign a month.

**2. Decay Agent (Play 2) — the highest-value agent in the system.** Sequence matters: **diagnose before contacting.** Decay is almost always local — one department or one creator — and outreach to a buyer about "usage being down" when the cause is one creator on parental leave burns credibility. The agent must localise the decay to department and creator, identify onset date, then classify cause into: person left/changed role · never got value · product friction · seasonal/cyclical · budget or priority shift · competitive displacement. Response branches entirely on cause — including **"seasonal → no intervention, log it and adjust the baseline."** Build that as a first-class outcome, not a null case. Contact creator-level causes at creator level and account-level causes at buyer level. Drafted outreach leads with the customer's outcome ("you were tracking toward 5-day distribution — are you still hitting that?"), never with our usage data. Exit requires a concrete action with a date and a logged cause. Metrics: recovery rate (volume back to ≥90% of baseline within 90 days) and lead time from trigger to intervention.

**3. Renewal Agent (Play 3).** Fires at T-20. Runs the evidence check, the utilisation check, and the stakeholder check *before* any commercial conversation — under-utilisation is the customer's strongest argument for reducing commitment, and it must be solved before the conversation, not during it. Prepares the value review pack in the customer's metric with their baseline and delta. Drafts the next-period proposal as a growth plan anchored on trajectory. Surfaces objections deliberately at T-5. Post-renewal debrief feeds back into decay triggers.

**4. Expansion Agent (Play 4).** Hard qualification gate — all must be true before it opens: confirmed result in last 2 quarters · Healthy ≥60 days · no single-threaded departments · named target department with a named owner · champion willing to introduce · budget path understood. **Enforce this gate in code, not in the prompt.** Expansion sold on relationship rather than evidence produces departments that go dark in two quarters. Route to Sales when a new budget holder is involved. A new department triggers a full Play 1 run, not an extension of the existing one.

**5. Portfolio Analyst.** Non-customer-facing. Weekly At-risk/Critical review pack, bi-weekly Watch review, monthly NRR roll-up and portfolio snapshot for the CEO, quarterly model calibration input. Writes to the console, drafts nothing outbound.

**6. Voice-of-Customer Router.** Tags every logged friction point, decay cause, and feature request; deduplicates across accounts; produces a ranked, evidence-backed list for Product with account and revenue attached. `Assume they are in the same Postgres database as this application and is updated regularly from the source.` No side channels: everything routes through this one path.

**Also build a Second-Creator Agent** as a background job even though it is not yet a written play: detect single-threaded live departments, and drive a seeding sequence before the creator leaves. It is the cheapest prevention in the whole model.

---

## 8. Console (the UI I actually use)

Next.js, server components, no design flourish. Five screens:

1. **Portfolio** — every account with health, band, trajectory arrow, tier, quadrant, revenue at risk, open signals, SLA clocks. Sortable, filterable. Divergence between health and revenue is highlighted, because that is where the surprises live.
2. **Account** — the account plan rendered live: objective in the customer's words, stakeholder map with coverage checkboxes, health history chart with the override that applied, campaign volume by department and creator, open signals, play history. Missing critical fields render as red prompts, not blanks.
3. **Approval queue** — the operating surface. Each item shows the proposed action, the agent's reasoning, the evidence it used, the autonomy level, and an SLA clock. Approve / edit / reject-with-reason. **Rejection reasons are training data — make the field mandatory and structured.**
4. **Play log** — every run, its exit test result, cause classification, and outcome. This is what turns v0.1 into a real playbook after two quarters.
5. **Calibration** — see below.

---

## 9. Autonomy matrix

Autonomy is a function of tier and action risk, stored in config, and every level is overridable per account.

| Action | T3 Scale | T2 Growth | T1 Strategic |
|---|---|---|---|
| Score, detect, alert | Auto | Auto | Auto |
| Internal brief / research | Auto | Auto | Auto |
| Onboarding sequence, in-product nudges | Auto | Auto | Draft |
| Routine check-in, enablement follow-up | Auto | Draft | Draft |
| Decay outreach — creator level | Auto | Draft | Draft |
| Decay outreach — buyer level | Draft | Draft | Human writes |
| Value confirmation request | Draft | Draft | Human |
| Renewal / commercial proposal | Draft | Human | Human |
| Exec-to-exec on budget or displacement | Never | Never | Human |
| Anything touching price or credits | Never | Never | Human |

**v1 ships with everything at Draft or below.** Auto-send unlocks per action type only after 30 approved-without-edit drafts in that category. Build the edit-rate tracking that makes that promotion decision evidential rather than a vibe.

---

## 10. Evaluation and calibration harness

This is not optional tooling; it is the thing that keeps the system honest. The health model's weights are guesses and become real only through measurement.

**Model quality metrics, computed quarterly and displayed on the calibration screen:**
- **Hit rate** — % of decay/churn events the model flagged At-risk/Critical at least one quarter ahead
- **False alarm rate** — % of At-risk/Critical accounts that recovered with no intervention
- **Lead time** — median days between first amber flag and revenue impact

Because scores are stored append-only, implement **retrospective scoring**: for every account that churned, decayed >30%, or expanded >30%, show what the model said two quarters earlier and whether the score moved before the outcome. Every surprise gets a named missing signal.

**Agent quality:** per agent, track draft approval rate, edit distance on approved drafts, rejection reasons by category, play exit-test pass rate, and cause-classification accuracy against human correction.

Build an eval suite of golden scenarios (seasonal dip misread as decay, champion departure, oversold commitment, single-creator department going quiet, expansion gate near-miss) that runs against the agents on every prompt change. Prompt changes without a regression suite are how this system quietly gets worse.

---

## 11. Stack, AWS deployment, and repo

Bias to boring and legible over clever. Seed stage, one engineer-equivalent, must be maintainable by someone who is not you. **This runs on AWS, single region, `us-east-1`.**

### Application stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy, Alembic
- **Frontend:** Next.js + TypeScript + Tailwind, shadcn/ui
- **Agents:** Claude or an open-weight model, behind a mandatory provider interface. See §11a. Prompts as versioned files in `/prompts`, never inline strings. Model choice **per agent** in Parameter Store config, not global.
- **Orchestration:** written by us, in plain Python. **Do not introduce an agent framework** — not LangGraph, CrewAI, AutoGen, LlamaIndex workflows, or Bedrock Agents. The loop we need is small, its state lives in `play_runs`, and the part a framework abstracts away is exactly the part §10 has to regression-test. Narrow libraries for structured output validation, retries, and tracing are fine and encouraged.
- **Ingestion:** adapter pattern per source (product DB, billing, CRM, email, support). Every adapter has a fixture-backed test.
- **Testing:** pytest; golden-file tests on all scoring; eval suite on all agents.

### AWS services

| Concern | Service | Note |
|---|---|---|
| Database | RDS Postgres, private subnets, Multi-AZ off at this stage | Not Aurora. We do not have the scale to justify the cost or the operational surface. |
| API / app runtime | ECS Fargate behind an ALB | Not Lambda. Agent runs are long, stateful, and chatty; Fargate is the simpler fit. App Runner is acceptable if you want fewer moving parts in phase 1. |
| Scheduled jobs | EventBridge Scheduler → one-off ECS tasks | Nightly scoring, trigger evaluation, billing reconciliation. Removes the need for an always-on scheduler process and gives us retry and failure alarms for free. |
| Async work | SQS + a worker service on Fargate | Agent runs and action execution. Dead-letter queue on everything. |
| Outbound email | SES, single configuration set | See §14 — this is the kill-switch surface. |
| Secrets | Secrets Manager for credentials and API keys; SSM Parameter Store for non-secret config | Model choice, weights, and thresholds live in Parameter Store so I can retune without a deploy, per §5. |
| Object storage | S3 for value-doc evidence, exports, eval fixtures | Versioning on, public access blocked at account level. |
| Frontend hosting | Amplify Hosting, or S3 + CloudFront if you prefer explicit | Either is fine; pick one and do not revisit. |
| Logs and metrics | CloudWatch Logs with a defined retention period, CloudWatch alarms on job failure and reconciliation divergence | |
| Infrastructure as code | Terraform | Everything, including IAM. No console-created resources — if it is not in the repo it does not exist. |
| CI/CD | GitHub Actions → ECR → ECS | Migrations run as a separate task before deploy, never on container start. |

### Deliberately not using

Do not reach for these; if you think one is genuinely needed, argue for it before building.

- **Step Functions for play orchestration.** The `play_runs` table is already the source of truth for orchestration state, and the human approval gate is a database record with an SLA clock. Splitting that state across Step Functions and Postgres gives us two places to look when a play stalls. Keep the state machine in the application.
- **A warehouse (Redshift, Athena, Glue).** Postgres handles a 40-account portfolio comfortably. Revisit at a few hundred accounts.
- **Bedrock Agents / Bedrock Knowledge Bases.** We need the orchestration logic in our own code, versioned and testable against the eval suite in §10. A managed agent framework puts the part I most need to audit inside a service I cannot unit-test.

### Environment rule

**`/metrics` must run locally with no AWS, no network, and no credentials.** The deterministic scoring layer is the part I need to reproduce by hand and test in isolation; if it acquires a dependency on an AWS client, that property is gone. Same for the synthetic generator in §13. Three environments: local (docker-compose Postgres, synthetic data), staging (real AWS, synthetic data), production.

```
/infra       Terraform
/ingest      adapters + normalisation
/core        canonical models, migrations
/metrics     deterministic scoring (no network, no LLM, no AWS)
/signals     trigger evaluation
/agents      orchestrator + specialists + provider interface
/prompts     versioned prompt files
/actions     approval queue + execution
/console     Next.js app
/evals       golden scenarios + calibration
/seed        synthetic data generator
```

---

## 11a. Model strategy — provider interface and the open-weight path

**The interface is mandatory regardless of what we run behind it.** One `LLMProvider` abstraction: structured completion, tool use, streaming, token accounting. Implementations for a hosted API and for a self-hosted OpenAI-compatible endpoint (vLLM). Swapping a provider, or a model for one agent, is a Parameter Store change and nothing else. Every call logs provider, model, version, latency, tokens, and cost to the action record. **We cannot make an evidence-based model decision without that telemetry, so build it in phase 4, not later.**

### Why this architecture tolerates smaller models well

Scores are computed in code. The expansion qualification gate is enforced in code. Nothing customer-facing sends without human approval. The LLM does bounded tasks with a deterministic safety net under each. That removes most of the exposure to where smaller and open-weight models are weakest, and it means model choice is a quality-and-cost question rather than a safety question.

### Task classes, ordered by how safely they take a smaller model

| Task class | Agents | Notes |
|---|---|---|
| Classification and tagging | decay-cause classification, VoC tagging, volume-pushing guardrail check | Constrained output, fixed label set. Highest call volume, lowest difficulty. Migrate here first. |
| Extraction and structuring | handoff validation, stakeholder parsing, objective capture | Schema-constrained. Low risk. |
| Internal synthesis | Portfolio Analyst, account briefs, kickoff prep | Read only by us. A mediocre brief costs nothing. |
| Customer-facing drafting | decay outreach, renewal proposal, value confirmation | Quality gap is most visible here, but the approval queue converts a weak draft into an edit rather than an incident. Measure edit distance before and after any switch. |
| Multi-step tool-use orchestration | Orchestrator | Most demanding, least suited to a small model. Migrate last, if at all. |

### Deciding empirically, not by preference

Extend the §10 eval suite so every golden scenario runs against **each candidate model** and reports pass rate, cause-classification accuracy against human labels, draft edit distance, latency, and cost per run. That table is the decision. Do not migrate a task class until it clears the incumbent on the evals; do not refuse to migrate one that does.

### If we self-host on AWS

- vLLM on EKS or EC2 GPU instances, OpenAI-compatible endpoint, behind the same provider interface. SageMaker real-time endpoints are the managed alternative and can scale to zero on a delay, which matters given how bursty our traffic is.
- Ollama locally for development so the eval suite runs on a laptop.
- **Model the cost honestly before recommending this.** A dedicated GPU instance costs the same whether it serves 200 calls a day or 200,000, and our volume is nightly scoring with no LLM plus a small number of agent runs. At current portfolio size, hosted per-token inference is very likely cheaper than a always-on instance. Self-hosting economics improve with sustained utilisation we do not have yet. Present the arithmetic; do not assume open weights means cheaper.

### The fine-tuning asset — design for it now, use it later

The approval queue is a labelling pipeline. Every approved draft, every edit, and every structured rejection reason is training data in Polst's own voice on Polst's own situations. Store drafts and their final approved versions as a paired corpus from day one, with the account context that produced them. In two or three quarters that corpus is the strongest argument for a fine-tuned open-weight model on the drafting tasks, because it encodes something no general model has. **Build the corpus now; do not attempt the fine-tune until it exists.**

---

## 12. Build phases

Each phase ends in something I can use. Do not start the next until I have seen the last.

0. **Ground.** Terraform for VPC, RDS, ECR, one Fargate service, secrets, and a CI pipeline that deploys a hello-world endpoint. Small, but it means every later phase ships to a real environment instead of accumulating on a laptop. Do not spend more than a day here.
1. **Data spine.** Canonical schema, synthetic generator, ingestion adapter interface, billing reconciliation job.
2. **Metrics + health.** Full deterministic scoring with overrides and null handling. Golden tests. Portfolio and account screens read-only. *This alone replaces the current spreadsheet tracker and is worth shipping on its own.*
3. **Signals + approval queue.** Triggers, SLA clocks, action records, human console. Still no LLM drafting — I want to see whether the triggers are right before agents act on them.
4. **Decay Agent.** Highest value, hardest problem, best first test of whether the agent layer earns its place.
5. **Onboarding Agent + Second-Creator Agent.**
6. **Renewal + Expansion Agents** with the hard qualification gate.
7. **Portfolio Analyst, VoC Router, calibration harness.**

---

## 13. Synthetic data mode

The real instrumentation does not exist yet and is the longest-lead-time dependency we have. **Do not let the build block on it.** Build a generator that produces a realistic 40-account portfolio spanning: healthy growth, seasonal dip, slow decay, sudden champion-departure collapse, oversold commitment at 40% utilisation, single-threaded department, new logo in onboarding, expansion-ready. Every scoring rule and every agent must be demonstrable against synthetic data with one config flag. This also gives me a working demo to take to the CEO and to Product, which is how the instrumentation ask gets prioritised.

---

## 14. Security and data handling

Customer contact data and commercial terms live here. Encrypt at rest, role-based access, full audit log on every read of stakeholder data. Redact PII from prompts where it is not needed for the task — an agent classifying a decay cause needs the pattern, not the person's email address. No customer data in evals or fixtures; synthetic only.

**On AWS specifically:**

- RDS in private subnets with no public accessibility. Application access via security group only; my access via a bastion or SSM Session Manager, never a public endpoint.
- KMS customer-managed keys for RDS, S3, and Secrets Manager. Encryption in transit enforced (`rds.force_ssl`).
- IAM roles per service, least privilege, no long-lived access keys anywhere. Task roles scoped so the ingestion worker cannot read the stakeholder tables it does not need.
- CloudTrail on, logs to a separate S3 bucket with a lifecycle policy. Application-level audit table is the primary record for stakeholder-data reads — CloudTrail is the backstop, not the answer.
- **Outbound kill switch:** all sending goes through SES via one internal service. The switch is a Parameter Store flag the console reads and writes, checked immediately before every send, plus SES account-level sending pause as the second layer. Test that the switch actually stops a queued send — an untested kill switch is decoration.
- SES in production access with a verified domain, DKIM and DMARC configured. Bounce and complaint handling wired to SNS and written back to the stakeholder record; a hard bounce on an economic buyer is a relationship signal, not just a delivery failure.
- Budget alarms on both the AWS account and model inference spend. Agent loops are the realistic runaway-cost failure mode here — put a per-account and per-day cap on agent invocations and alarm before the cap, not at it.

---

## 15. Acceptance criteria for v1

- Health scores reproduce by hand against the model above for ten sampled accounts.
- No score is ever produced from imputed data; missing inputs surface as named nulls.
- Every trigger in §6 fires correctly against the synthetic portfolio, including the seasonal case *not* firing an intervention.
- Every customer-facing action passes through the approval queue with visible reasoning.
- The volume-pushing guardrail catches a deliberately non-compliant draft in test.
- Every play run closes against its exit test with a logged outcome and cause.
- Retrospective scoring can answer: what did the model say about this account two quarters ago?

---

## 16. Assumptions are provided below.

1. Which quality metric can Polst actually measure per campaign — completion, response rate, or reach? Dimension 4 depends on it and it is a Product question. If none is available at build time, implement the 0/50/100 rubric path and leave the percentile path behind a flag.
2. Which Tier 1 instrumentation fields exist today and which need new event tracking? Assume all exist.
3. Source of truth for billable campaign count. Assume same Postgres database.
4. Tier thresholds — Make reasonable assumption.
5. Anything in this brief you think is wrong. I would rather argue now than refactor later.
6. `**Model access.** Assume Bedrock accessing Claude API.
