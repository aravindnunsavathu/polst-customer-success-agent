# Polst CS Agent Platform

See `CLAUDE.md` and `BUILD-PROMPT.md` for the full brief, and
`context/cs-pack/` for the functional spec. This file is just the local
dev quickstart.

## Local setup (Phase 0 + Phase 1)

Everything runs against a local Postgres via docker-compose — no AWS
credentials or network access needed. `/seed` and its generator have zero
network/AWS/LLM dependencies by construction, per BUILD-PROMPT.md §11.

```bash
cp .env.example .env          # only needed once
docker compose up -d          # Postgres on localhost:5433 (not 5432 — see docker-compose.yml)

pip install -e ".[dev]"       # or: pip install fastapi uvicorn sqlalchemy alembic "psycopg[binary]" pydantic faker pytest httpx

alembic upgrade head          # apply the canonical schema
python -m seed.cli --reset    # generate the synthetic 40-account portfolio
python -m ingest.jobs.reconcile_billing   # should print "clean" against seed data

pytest                        # full suite — needs the DB above running
```

## What's here after Phase 1

- `core/` — canonical SQLAlchemy schema (17 tables) + Alembic migrations.
  Accounts and stakeholders are versioned (valid_from/valid_to); everything
  else is a plain fact/event table. See `core/models/mixins.py` for the
  versioning pattern and `pg_enum` gotcha it works around.
- `seed/` — the synthetic portfolio generator (BUILD-PROMPT.md §13): 8
  scenarios × 5 accounts = 40, deterministic given (seed, as_of). Pure and
  DB-free until `seed/cli.py`'s write step.
- `ingest/` — the `SourceAdapter` interface, a fixture-backed reference
  adapter (`FixtureAdapter`, reading a JSON export), the shared upsert
  loader, and the nightly billing reconciliation job.
- `api/` — the Phase 0 hello-world FastAPI service (not yet wired to `core`
  — that's Phase 2's read-only Portfolio/Account screens work, plus a
  proper API layer).
- `infra/` — Terraform for Phase 0 (see `infra/README.md`), authored but
  not applied.

## Known scope decisions from Phase 1

- **Renewal trigger anchor.** `accounts.next_review_date` is a synthetic
  quarterly cadence from `contract_start`, used by Play 3 (Phase 3+) for
  ad-hoc/monthly accounts that have no real `commitment_end`. See the
  implementation plan for why.
- **Temporal versioning** (`valid_from`/`valid_to`) is scoped to `accounts`
  and `stakeholders` — the two entities BUILD-PROMPT.md's retrospective
  scoring requirement (§10) actually depends on. Everything else is a
  plain append-only fact table.
- **Ingestion never touches CS judgment fields.** `tier`, `quadrant`,
  `commercial_model`, `committed_volume`, and the `potential_*` columns on
  `accounts` are never set by `ingest/loader.py` — only a human (via the
  Phase 2+ console) or an explicit CS decision sets those. New accounts
  default to the lowest tier until reviewed.
