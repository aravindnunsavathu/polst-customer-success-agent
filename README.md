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

## What's here after Phase 4

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
- `prompts/` — versioned prompt templates (never inline strings):
  `decay_cause_classification.md`, `decay_outreach_creator.md`.
- `seed/` — the synthetic portfolio generator (§13): 8 scenarios × 5
  accounts = 40, deterministic given (seed, as_of).
- `ingest/` — the `SourceAdapter` interface, a fixture-backed reference
  adapter, the shared upsert loader, and the nightly billing reconciliation
  job.
- `api/` — FastAPI service. Read-only: `GET /accounts`, `GET /accounts/{id}`
  (open signals, play history), `GET /signals` (the portfolio-wide
  worklist, sorted by priority). Two write endpoints for the approval
  queue: `POST /actions/{id}/approve`, `POST /actions/{id}/reject`
  (mandatory structured reason) — now genuinely populated by the Decay
  Agent, not just proven against fixtures.
- `console/` — Next.js 16 (App Router, TypeScript, Tailwind), no design
  flourish per §8: Portfolio, Account detail (+ open signals, play
  history), Signals worklist, Approval Queue.
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
- **Play 4's trigger is the simple 3-condition version** (healthy +
  confirmed result + addressable department not live) — the full 6-point
  qualification gate is Phase 6's job, enforced in code when the
  Expansion Agent actually runs.
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
