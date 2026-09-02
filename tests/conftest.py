"""Shared fixtures. Tests using db_session need a reachable Postgres test
database — `docker compose up -d db` first (see root README); a fresh
volume creates `polst_cs_test` automatically via docker/init-test-db.sql.

This deliberately does NOT fall back to DATABASE_URL: db_session
truncates every table before each test, and DATABASE_URL points at
whatever you've seeded for local demo/dev use. The two must never be the
same database, or `pytest` silently wipes your seeded portfolio — which
is exactly what happened during Phase 2 development before this fixture
required TEST_DATABASE_URL explicitly."""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from seed.cli import ALL_TABLES

DEFAULT_TEST_DATABASE_URL = "postgresql+psycopg://polst_app:localdev@localhost:5433/polst_cs_test"


@pytest.fixture
def db_session():
    database_url = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    if "test" not in database_url.rsplit("/", 1)[-1]:
        raise RuntimeError(
            f"TEST_DATABASE_URL ({database_url!r}) doesn't look like a test database "
            f"(name has no 'test' in it) — refusing to truncate it. This check exists "
            f"because this fixture wipes every table before each test."
        )
    engine = create_engine(database_url)
    session = sessionmaker(bind=engine)()
    table_names = ", ".join(m.__tablename__ for m in ALL_TABLES)
    session.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
