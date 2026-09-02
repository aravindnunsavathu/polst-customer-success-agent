"""Shared fixtures. Tests using db_session need a reachable Postgres —
`docker compose up -d db` first (see root README)."""

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from core.db import DATABASE_URL as DEFAULT_DATABASE_URL
from seed.cli import ALL_TABLES


@pytest.fixture
def db_session():
    database_url = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)
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
