# Polst CS Agent Platform

See `CLAUDE.md` and `BUILD-PROMPT.md` for the full brief, and
`context/cs-pack/` for the functional spec. This file is just the local
dev quickstart.

## Local setup (Phase 0 through Phase 4)

Everything runs against local Postgres via docker-compose — no AWS
credentials or network access needed. `/metrics`, `/signals`, and
`/agents` (outside their `jobs/` bridge modules, and outside
`agents/llm/bedrock.py`) and `/seed` have zero network/AWS/LLM/DB
dependencies by construction, per BUILD-PROMPT.md §11.

```bash
cp .env.example .env          # only needed once
docker compose up -d          # Postgres on localhost:5433 (not 5432 — see docker-compose.yml)
                               # creates both polst_cs (dev) and polst_cs_test (tests) on a fresh volume

pip install -e ".[dev]"       # or: pip install fastapi uvicorn sqlalchemy alembic "psycopg[binary]" pydantic faker pyyaml pytest httpx

alembic upgrade head          # apply the canonical schema to the dev DB
python -m seed.cli --reset    # generate the synthetic 40-account portfolio
python -m ingest.jobs.reconcile_billing   # should print "clean" against seed data
python -m core.jobs.score_portfolio       # scores every account, writes health_scores
python -m signals.jobs.evaluate_triggers  # evaluates §6 triggers, opens signals/play_runs/coverage_elevations
python -m agents.jobs.run_decay_agent     # diagnoses + classifies open decay play_runs, drafts outreach
python -m agents.jobs.run_onboarding_agent    # advances open onboarding play_runs one stage each
python -m agents.jobs.run_second_creator_agent # scans for single-threaded departments, drafts seeding actions
python -m agents.jobs.run_renewal_agent       # advances open renewal play_runs (T-20 -> T+7) one stage each
python -m agents.jobs.run_expansion_agent     # re-validates the Play 4 gate in code, drafts the champion case
python -m agents.jobs.run_portfolio_analyst   # self-paced weekly/bi-weekly/monthly/quarterly reviews
python -m agents.jobs.run_voc_router          # tags untagged feedback, dedupes across accounts, ranks for Product

# Tests need the schema on the TEST database too (separate from dev — see below):
DATABASE_URL=$TEST_DATABASE_URL alembic upgrade head
pytest                        # full suite

# Console + API, in two terminals:
uvicorn api.main:app --reload --port 8000
cd console && npm install && cp .env.local.example .env.local && npm run dev   # http://localhost:3000
```

### Why two databases

`tests/conftest.py`'s `db_session` fixture truncates every table before
each test. It reads `TEST_DATABASE_URL`, never `DATABASE_URL` — pointing
both at the same database means running `pytest` silently wipes whatever
you've seeded for local demo use (this happened once during Phase 2
development). `docker/init-test-db.sql` creates `polst_cs_test`
automatically on a fresh `docker compose up`; the fixture also refuses to
run against any URL whose database name doesn't contain "test".

### No real LLM credentials in this environment

Same situation as `/infra`'s Terraform: `agents/llm/bedrock.py` is
authored against the Bedrock Converse-style API but has never been
exercised against a live endpoint. Every agent runs today against
`HeuristicLLMProvider` (`agents/llm/fake.py`) — plain Python rules, no
network, configured as the default in `agents/llm/config/model_config.yaml`.
It's good enough to demonstrate the full diagnose → classify → draft
pipeline end-to-end against the seeded portfolio, but it is not a real
classifier. Point `model_config.yaml` at `provider: bedrock` once real
AWS/Bedrock access exists, and review `bedrock.py` against the actual
response shape before trusting it.

## What's here after Phase 7

- `core/` — canonical SQLAlchemy schema (19 tables) + Alembic migrations.
  Accounts and stakeholders are versioned (valid_from/valid_to); everything
  else is a plain fact/event table. `core/jobs/` holds the nightly jobs
  allowed to import both `core` and `metrics`/`signals`/`agents` —
  `fetch.py`'s Postgres-to-pure-facts converters are shared across all of them.
- `metrics/` — the deterministic health-scoring engine (BUILD-PROMPT.md
  §5 / doc 02 §3-5): derived metrics, six dimensions, seven overrides, the
  composite orchestrator, and `metrics/config/health_model_v1.yaml` (every
  weight and threshold, git-tracked and config-driven). Zero network/AWS/
  DB dependency — `tests/metrics/test_golden_scores.py` has ten
  hand-verified scores per §15's acceptance criterion.
- `signals/` — trigger evaluation (§6): six decay triggers (with seasonal
  suppression backed by `metrics.dimensions.seasonality_flag`), three play
  triggers, six time-boxed coverage-elevation triggers, and the
  non-agent orchestrator (dedup, one-play-per-account, priority ranking).
  `signals/jobs/evaluate_triggers.py` is the nightly bridge to Postgres.
  Also zero network/AWS/DB dependency outside `jobs/`.
- `agents/` — the provider-agnostic `LLMProvider` interface (§11a),
  the §9 autonomy matrix resolver (with the v1 Draft-cap and
  30-approved-without-edit promotion path actually computed from `Action`
  history), the volume-pushing guardrail, and the **Decay Agent**
  (§7 Play 2): deterministic diagnosis (localize to department/creator,
  estimate onset date) feeds an LLM cause classification, which branches
  into a creator-level draft, an internal Product-routing action (also
  logs a `FeedbackItem` — no side channels, per doc 01), a stricter
  exec-to-exec action for budget/competitive causes, or — for `seasonal`
  — a first-class no-intervention outcome that closes the play_run
  immediately. `agents/jobs/run_decay_agent.py` also closes out
  play_runs whose 90-day recovery window has elapsed (recovered vs.
  unrecovered), the play's named metric.
  Also the **Onboarding Agent** (§7 Play 1): a multi-week state machine,
  not a single-shot decision — `agents/onboarding/agent.py` advances at
  most one stage per invocation, persisting progress in
  `play_runs.exit_test_results` across nightly runs (same pattern the
  Decay Agent uses for its 90-day recovery window). Stage 1 validates the
  Sales handoff (`agents/onboarding/handoff.py`, pure/deterministic —
  a data-completeness check, not a judgment call) and **returns an
  incomplete handoff to Sales as a real workflow state** (`play_run`
  closes with `outcome="handoff_rejected"`), not a warning. Stage 2
  drafts the internal kickoff brief and the customer-facing written
  success criteria. Stage 3, at ~day 40, drafts a value-confirmation
  request to the economic buyer if no result is confirmed yet. Stage 4
  evaluates all four doc-06 exit-test conditions live every run and
  **never closes at launch alone** — it closes `completed_successfully`
  only once all four are true, or `stalled` past a stall window (see
  Known scope decisions). Also the **Second-Creator Agent**: a
  background job (`agents/second_creator/agent.py`, not a written play)
  that scans every account's live departments each night for exactly one
  active creator and drafts a seeding message before that creator
  leaves — "the cheapest prevention in the whole model."
  `agents/jobs/run_onboarding_agent.py` and
  `agents/jobs/run_second_creator_agent.py` are the nightly Postgres
  bridges.
  Also the **Renewal Agent** (§7 Play 3): a T-20 → T+7 state machine on
  the same play_run-state pattern. T-20 runs the evidence, utilization,
  and stakeholder checks *before* any commercial conversation
  (`agents/renewal/diagnosis.py`) and — when utilization is low from the
  start of the term rather than from a recent decline — logs a
  `FeedbackItem` tagged `oversold_commitment` and routed to **Sales**
  ("that's a Sales-handoff finding, not a CS failure," doc 06), the
  Renewal Agent's analogue of the Decay Agent's product-friction routing.
  T-15 drafts the value review, T-10 the growth-plan proposal, T-5 the
  deliberate objection check, and T+7 always closes the play with a
  debrief, classifying the outcome from the account's own versioned
  history (see Known scope decisions). And the **Expansion Agent**
  (§7 Play 4): the play_run the signals layer opens on the simple
  3-condition trigger gets **re-validated here against the full 6-point
  qualification gate in code** (`agents/expansion/gate.py`) — an
  unqualified account closes immediately, undrafted. A new budget holder
  hands to Sales; the same holder means CS runs it, starting with a
  drafted internal case for the champion to present. Once the named
  target department actually goes live, the agent tracks doc 06's
  four-point exit test and, on success, opens a fresh **Onboarding**
  play_run for the new department — "a new department triggers a full
  Play 1 run, not an extension of the existing one." Both agents' jobs:
  `agents/jobs/run_renewal_agent.py`, `agents/jobs/run_expansion_agent.py`.
  Also the **Portfolio Analyst** (§7): non-customer-facing, "writes to
  the console, drafts nothing outbound." Four cadenced reviews, each a
  deterministic aggregation step (band/revenue rollups, cohort-based NRR
  via `metrics.derived.nrr`) paired with an LLM narrative synthesis —
  weekly At-risk/Critical, bi-weekly Watch, monthly NRR + portfolio
  snapshot for the CEO, and quarterly calibration input. Self-paced:
  `agents/jobs/run_portfolio_analyst.py` only generates a report once its
  own cadence has elapsed since the last one of that type, not on every
  invocation. And the **Voice-of-Customer Router** (§7): classifies any
  `FeedbackItem` that doesn't already carry a tag (the Decay and Renewal
  Agents tag their own at creation), dedupes across accounts by tag, and
  ranks by accounts-affected × revenue — "no side channels, everything
  routes through this one path." `agents/jobs/run_voc_router.py`.
  Both write into the shared `portfolio_reports` table via
  `agents/portfolio_analyst/agent.py` / `agents/voc_router/router.py`.
- `evals/` — the calibration harness (§10): pure, deterministic functions
  (same discipline as `/metrics` — no network/DB/LLM) computing hit rate,
  false alarm rate, median lead time, and per-event retrospective
  look-back ("what did the model say two quarters before this account
  churned/decayed/expanded"), fed by the Portfolio Analyst's quarterly
  calibration_input report.
- `prompts/` — versioned prompt templates (never inline strings):
  `decay_cause_classification.md`, `decay_outreach_creator.md`,
  `onboarding_kickoff_brief.md`, `onboarding_success_criteria.md`,
  `onboarding_value_confirmation.md`, `second_creator_seeding.md`,
  `renewal_value_review.md`, `renewal_growth_proposal.md`,
  `renewal_objection_check.md`, `expansion_champion_case.md`,
  `portfolio_at_risk_critical_review.md`, `portfolio_watch_review.md`,
  `portfolio_monthly_ceo_snapshot.md`, `portfolio_calibration_input.md`,
  `voc_tag_classification.md`, `voc_ranked_list_summary.md`.
- `seed/` — the synthetic portfolio generator (§13): 8 scenarios × 5
  accounts = 40, deterministic given (seed, as_of).
- `ingest/` — the `SourceAdapter` interface, a fixture-backed reference
  adapter, the shared upsert loader, and the nightly billing reconciliation
  job.
- `api/` — FastAPI service. Read-only: `GET /accounts`, `GET /accounts/{id}`
  (open signals, play history), `GET /signals` (the portfolio-wide
  worklist, sorted by priority), `GET /reports` (optional `?type=`) and
  `GET /reports/{id}` (the Portfolio Analyst's four reviews + the VoC
  Router's ranked list), `GET /plays` (optional `?play=`/`?status=`, the
  cross-account play log with each play_run's actions and exit-test
  results nested in). Two write endpoints for the approval
  queue: `POST /actions/{id}/approve`, `POST /actions/{id}/reject`
  (mandatory structured reason) — now genuinely populated by the Decay
  Agent, not just proven against fixtures.
- `console/` — Next.js 16 (App Router, TypeScript, Tailwind), no design
  flourish per §8: Portfolio, Account detail (+ open signals, play
  history), Signals worklist, Approval Queue, **Play Log** (every play
  run across the portfolio, filterable by play type and open/closed,
  each row's actions and exit-test JSON behind a `<details>` expander —
  no client JS needed for that), and **Calibration** (hit rate, false
  alarm rate, median lead time as stat cards, the latest narrative, and
  a Surprises table — decay/churn events the model didn't flag a quarter
  ahead — plus a compact history table if more than one quarterly report
  exists). Both are the §8 screens Phase 7 originally shipped API-only;
  see Known scope decisions for why they're plain server components with
  zero new client-side state.
- `infra/` — Terraform for Phase 0 (see `infra/README.md`), authored but
  not applied.

## Known scope decisions

- **Renewal trigger anchor.** `accounts.next_review_date` is a synthetic
  quarterly cadence from `contract_start`, used by Play 3 for ad-hoc/
  monthly accounts that have no real `commitment_end`.
- **Temporal versioning** (`valid_from`/`valid_to`) is scoped to `accounts`
  and `stakeholders` — the two entities the retrospective-scoring
  requirement (§10) actually depends on.
- **Ingestion never touches CS judgment fields** (`tier`, `quadrant`,
  `commercial_model`, `committed_volume`, `potential_*`) — only a human or
  an explicit CS decision sets those. New accounts default to the lowest
  tier until reviewed.
- **Composite score renormalizes over available dimensions** rather than
  going null the instant one dimension can't be computed (your call,
  Phase 2). `campaign_quality` and `sentiment_friction` have no confirmed
  data source yet (§16.1; no escalation/ticket table exists at all), so
  in practice every score today excludes `sentiment_friction` at minimum —
  visible in `health_scores.null_reasons`, never silently imputed.
- **Campaign quality's 0/50/100 rubric uses creator repeat rate** as the
  proxy metric (doc 02 §4's own suggested fallback), since no campaign
  outcome metric is confirmed. The percentile path is real code, gated
  behind `campaign_quality.use_percentile` in the config, off by default.
- **Sentiment & friction is structurally always null** — no
  escalation/support-ticket table exists anywhere in the schema or the
  doc 03 instrumentation ask. The scoring function and its override are
  both real, correct code, just never triggered by data yet.
- **Seasonality eligibility is data-coverage-based, not a flat month
  count.** `seasonality_flag` only trusts a YoY comparison when real
  campaign history actually reaches back far enough to populate the
  entire prior-year window, and requires a minimum sample size on both
  sides. A cruder "12 calendar months since the earliest campaign" check
  let a handful of campaigns at the edge of a mostly-empty window produce
  a nonsense ratio (7-24x) that silently suppressed genuine decay signals
  — caught by testing against the seeded portfolio, not by the unit tests
  alone, which is why `tests/signals/test_triggers.py` has an explicit
  regression test for it.
- **"Refuses a second concurrent play" is account-wide**, not
  per-play-type: at most one open `play_run` per account regardless of
  play, the stricter reading of "one coordinated intervention."
- **Two of the six coverage-elevation durations are approximated.**
  "Until first value" (new department launching) and "duration of
  project" (reference candidate) don't map to anything tracked at the
  right grain — no per-department value confirmation, no reference/
  case-study project entity — so `signals/coverage.py` uses a fixed,
  documented duration (60 and 90 days respectively) instead.
- **Play 4's *trigger* (which play_run opens) stays the simple
  3-condition version** (healthy + confirmed result + addressable
  department not live) — it only decides whether to open the play_run.
  The full 6-point qualification gate (Phase 6) is re-checked in code by
  the Expansion Agent itself before anything drafts, per §7's "enforce
  this gate in code, not in the prompt."
- **Diagnosis is deterministic Python, not an LLM step.** Localizing
  decay to a department/creator and estimating an onset date is factual
  computation from data already in Postgres — only cause classification
  and outreach drafting go through an LLM, matching §11a's task-class
  table and the deterministic/judgment split in CLAUDE.md.
- **The v1 autonomy cap only applies to customer-facing action types.**
  §9 says "auto-*send*" unlocks after 30 approved-without-edit drafts —
  `score_detect_alert` and `internal_brief` are Auto for every tier in
  the matrix and stay Auto in v1, since nothing customer-facing is at
  stake. `agents/config/autonomy_matrix.yaml` marks each row
  `customer_facing: true/false` explicitly rather than leaving that
  distinction implicit.
- **Cause → contact-level mapping follows doc 06's table, not a generic
  "buyer outreach."** `person_left`/`never_got_value` → creator-level
  draft; `product_friction` → internal routing (no customer contact,
  plus a `FeedbackItem` so it flows through the one VoC intake doc 01
  insists on); `budget_priority_shift`/`competitive_displacement` → the
  stricter `exec_to_exec_budget_or_displacement` autonomy row (Never/
  Never/Human), not the generic "decay outreach — buyer level" row.
  That generic row exists in the matrix for completeness but nothing in
  the Decay Agent's cause branching invokes it yet.
- **A keyword-based guardrail, not an LLM-judged one.** `agents/guardrails.py`
  checks drafted copy against a literal volume-pushing phrase list —
  matches CLAUDE.md's "gates enforced in code, not in prompts," but can't
  catch every rephrasing. A flagged draft is forced to at least `Draft`
  autonomy regardless of promotion status; it's never silently dropped.
- **`STALL_DAYS = 120` is our own addition, not in the brief.** Doc 06
  gives Play 1 a day -3 → day 45 sequence and an exit test, but no
  cutoff for an onboarding that never meets it. Without one, a genuinely
  abandoned onboarding's `play_run` stays open forever, which violates
  §2.4 ("every play run records an outcome"). 120 days is a generous
  multiple of the day-45 value-confirmation checkpoint, not a value from
  the spec.
- **`buyer_has_seen_result` is a proxy, not a direct signal.** No event
  in the schema records "the economic buyer saw the result." A
  `value_doc` with `confirmed_by` set is the closest available stand-in
  — doc 06's process routes confirmation through the economic buyer, so
  a confirmed doc implies they saw it. A real "shared with buyer" event
  would be a strictly better signal if doc 03's instrumentation ever adds
  one.
- **The exit test is recomputed live every run, not cached in state.**
  `_exit_test_conditions()` reads current campaigns/value-docs each
  invocation rather than trusting a stale flag — campaigns and value docs
  can change between runs for reasons the state machine itself didn't
  cause (e.g. a value doc confirmed independently of the day-40 request).
- **`HeuristicLLMProvider._draft()` branches on which evidence keys are
  present**, not on a prompt name — it originally assumed every drafting
  prompt was "checking in on the customer's stated objective" (true for
  Decay and Onboarding), which produced a nonsensical draft for
  Second-Creator seeding (no objective to check in on, and the prompt's
  actual ask — "invite a colleague" — never appeared). Fixed by keying
  off the absence of `stated_objective` in the evidence block combined
  with the presence of `department_id`, since that's the shape only
  second-creator evidence has. Caught by `tests/agents/test_second_creator.py`,
  not by the earlier ad-hoc smoke test, which is why it's a named
  regression test now rather than a silent fix.
- **Three of Play 4's six gate conditions have no usage-data source at
  all** — a named target department with a named owner, whether the
  champion will make the introduction, and whether the budget path
  involves a new holder. These are CS judgment, not something derivable
  from product data, so a migration added
  `account_plans.expansion_target_department/_owner/_champion_introduction/_new_budget_holder`,
  filled by a human, same status as `tier`/`quadrant`/`commercial_model`.
  `expansion_new_budget_holder` is nullable rather than defaulting to
  `False` — "unknown" and "confirmed same holder" must not read the
  same way, or the gate would silently pass accounts nobody actually
  checked.
- **`DepartmentFact` gained a `name` field** (default `None`) purely so
  the Expansion Agent can match the account plan's free-text
  `expansion_target_department` against a live department — nothing else
  in `/signals` or `/metrics` needed a department's name before.
- **The Renewal Agent's "recommitment secured" signal is real, not a
  proxy** — doc 06's exit test asks for "recommitment ≥ prior volume" at
  T+7, far too soon to see a usage-volume comparison mean anything.
  Instead it compares the account's *own versioned history*: `accounts`
  is append-only (`valid_from`/`valid_to`), so a genuine recommitment
  shows up as a new version with `commitment_end`/`next_review_date`
  pushed forward and `committed_volume` held or grown. If the term
  wasn't extended and no campaigns ran since the reference date, the
  outcome is `lost`; otherwise (still consuming, but no recorded
  extension) it's honestly logged as `undetermined` rather than guessed.
- **"Growth plan agreed" is tracked as "presented," not "agreed."**
  Nothing in the schema records the buyer's agreement to a proposal —
  same class of gap as Onboarding's `buyer_has_seen_result` proxy.
  `growth_plan_presented` is true once both the growth-proposal and
  objection-check stages have run; a human still has to confirm actual
  agreement.
- **The T-5 objection check and the T-10 growth proposal share the
  `renewal_commercial_proposal` autonomy row** but are logged as distinct
  `Action.type`s (`renewal_growth_proposal` / `renewal_objection_check`)
  for play-log clarity — same precedent as the Second-Creator Agent
  resolving against `routine_check_in` while storing its own action
  type. Doc 06 treats both as part of one commercial conversation with
  the same risk profile; §9 has no separate row for a T-5 follow-up.
- **Doc 06's "paper it" step (T-5, signing the actual contract) isn't
  modeled as a stage.** It's an offline step with no data this system
  computes or drafts — the objections stage is the last agent-driven
  checkpoint before it.
- **Expansion's per-department exit-test conditions are proxies where
  the schema has no per-department granularity.** There's no
  per-department account plan, so `departmental_success_criteria_documented`
  uses "a value doc confirmed since the department launched" as the
  nearest available evidence rather than a direct "documented" signal.
- **Two new stall windows, our own addition, not in the brief**
  (`NO_LAUNCH_STALL_DAYS = 180`, `DID_NOT_STICK_STALL_DAYS = 270` in
  `agents/expansion/agent.py`) — same §2.4 rationale as Onboarding's
  `STALL_DAYS`: every play run needs a logged outcome, including "the
  target department never launched" and "it launched but didn't stick,"
  doc 06's own named worst case ("a department added and lost is worse
  than neutral").
- **`ValueDocFact` gained a `confirmed_by` field** (`metrics/types.py`,
  default `None` so no existing call site broke) — the onboarding exit
  test's `buyer_has_seen_result` proxy needs it, but the pure fact
  dataclass never carried it and `core/jobs/fetch.py`'s
  `fetch_value_doc_facts` was silently dropping the column, so the
  condition could never be true against real data. Found while writing
  `tests/agents/test_onboarding_agent.py`'s exit-test-passes case, not
  by manual smoke testing.
- **Fixed `health_scores.scored_at` to derive its date from `as_of`,
  not wall-clock `datetime.now()`.** The job already accepted `as_of`
  for computing the score itself, but stamped every row with real "now"
  regardless — a backfill run scoring a historical date would have every
  row lie about which date it represents, making "what did the model say
  two quarters ago" (§10's own Phase 7 demo criterion) unanswerable by
  querying `scored_at`. The time-of-day component still comes from real
  wall-clock so repeated same-day runs order predictably; only the date
  is forced to `as_of`. Found while building the calibration harness,
  before writing any of its tests — a backfill against the freshly-seeded
  portfolio produced 12 identical `scored_at` values until this was
  fixed.
- **The Portfolio Analyst's 5 outputs share one `portfolio_reports`
  table** (`report_type` discriminator: 4 Portfolio Analyst cadences +
  the VoC Router's ranked list) rather than five near-identical tables —
  all five are the same shape: deterministic `data`, optional LLM
  `narrative`, a period, read-only.
- **NRR is cohort-based, matching doc 01's own definition exactly**
  ("revenue from prior-period cohort in current period ÷ revenue from
  that cohort in prior period") — the monthly snapshot's NRR figure only
  sums accounts present in *both* periods; new logos are reported
  separately (`new_logos_count`) and never inflate the NRR number, per
  the prompt's explicit hard rule against praising raw revenue growth as
  retention.
- **Revenue is the same `departments_live × $8,000/mo` proxy already
  used by the API's priority scoring** (BUILD-PROMPT.md has no real
  billing integration yet) — pulled out of `api/routers/accounts.py`
  into `metrics.derived.REVENUE_PER_DEPARTMENT_PROXY` so the Portfolio
  Analyst, the VoC Router, and both API routers share one constant
  instead of three copies of the same magic number.
- **Calibration events reuse the exact `volume_ratio_90d` formula**
  the health model's volume-trajectory dimension and the decay trigger
  already use — "churned/decayed >30%/expanded >30%" is that same ratio
  crossing a wider threshold (≤0.70 / ==0.0 / ≥1.30) than the 0.85 decay
  trigger, not a separately-defined metric requiring its own formula.
- **False alarm rate needs play_run data, not just health-score
  history** — "recovered with no intervention" is checked by looking for
  any `play_run` opened during a risk episode's window, which is a DB
  query (`agents/jobs/run_portfolio_analyst.py`), not something the pure
  `evals/calibration.py` functions can determine on their own from
  banding history alone.
- **Naming the missing signal behind a calibration surprise stays a
  human step**, per doc 02 §7 ("for every surprise, name the signal that
  would have caught it"). `evals/calibration.py` surfaces *which* events
  were surprises (not flagged a quarter ahead); the calibration prompt is
  explicitly instructed not to invent what the missing signal was.
- **Phase 7 shipped Play log and Calibration API-only; both got their
  console screens in a follow-up pass.** The three-phase gap (Phases
  4-6 also shipped zero new console pages) meant `GET /reports` already
  existed and adding the screens really was the "pure frontend exercise"
  the earlier note predicted — the only new backend piece needed was
  `GET /plays`, since the account-scoped play history nested in
  `GET /accounts/{id}` had no cross-account equivalent.
- **Both new pages are plain server components, no `"use client"`.**
  Filters (`/plays?play=&status=`) are `<Link>`s that change the URL,
  read back via `searchParams`; per-row detail (a play_run's actions,
  its exit-test JSON) is a native `<details>` disclosure, not client
  state — consistent with the read-only Signals/Portfolio pages, and
  cheaper than QueueList's client-side approve/reject flow, which
  actually needs to mutate state without a full page reload.
- **Calibration's surprises table needed account names, not just IDs**
  — `evals/calibration.py` stays pure and only ever produces an
  `account_id` string, so `agents/jobs/run_portfolio_analyst.py`'s
  `_calibration_summary` now also attaches `account_name` when it builds
  the report's `data.surprises` list, the same "resolve names at the
  DB-aware edge, keep the pure layer free of ORM lookups" split used
  everywhere else in this codebase.
- **The golden scenario eval suite runs against real seed-generated data
  through a real test-DB round trip** (`tests/evals/test_golden_scenarios.py`),
  not hand-rolled fixtures — it inserts one of the actual
  `seed/scenarios.py` generators' output via `write_portfolio` and
  exercises the real `core/jobs/fetch.py` conversion path, since the
  point of a regression suite that runs "on every prompt change" (§10)
  is catching a break in the integration path, not just the pure logic
  underneath it. The expansion-gate near-miss test is the one exception
  that hand-supplies a synthetic health-score history alongside the real
  scenario data — a fresh scenario insert has no scoring history yet,
  and the test needs to isolate exactly one failing condition rather
  than also failing on missing history.
