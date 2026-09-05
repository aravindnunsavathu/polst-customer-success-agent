# Polst CS Agent Platform

See `CLAUDE.md` and `BUILD-PROMPT.md` for the full brief, and
`context/cs-pack/` for the functional spec. This file is just the local
dev quickstart.

## Local setup (Phase 0 + Phase 1 + Phase 2 + Phase 3)

Everything runs against local Postgres via docker-compose — no AWS
credentials or network access needed. `/metrics` and `/signals` (outside
their `jobs/` bridge modules) and `/seed` have zero network/AWS/LLM/DB
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

## What's here after Phase 3

- `core/` — canonical SQLAlchemy schema (19 tables) + Alembic migrations.
  Accounts and stakeholders are versioned (valid_from/valid_to); everything
  else is a plain fact/event table. `core/jobs/` holds the nightly jobs
  allowed to import both `core` and `metrics`/`signals` — `fetch.py`'s
  Postgres-to-pure-facts converters are shared by both.
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
- `seed/` — the synthetic portfolio generator (§13): 8 scenarios × 5
  accounts = 40, deterministic given (seed, as_of).
- `ingest/` — the `SourceAdapter` interface, a fixture-backed reference
  adapter, the shared upsert loader, and the nightly billing reconciliation
  job.
- `api/` — FastAPI service. Read-only: `GET /accounts`, `GET /accounts/{id}`
  (now including open signals and play history), `GET /signals` (the
  portfolio-wide worklist, sorted by priority). Two write endpoints for
  the approval queue: `POST /actions/{id}/approve`, `POST /actions/{id}/reject`
  (mandatory structured reason) — no agent populates `actions` yet
  (Phase 4+), so the queue is legitimately empty against real data; the
  mechanics are proven in `tests/api/test_actions.py`.
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
