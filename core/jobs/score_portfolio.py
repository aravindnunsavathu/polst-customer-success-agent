"""Nightly scoring job (BUILD-PROMPT.md §6): computes and stores a
health_scores row for every current account. This is the one place
allowed to import both `core` (real Postgres) and `metrics` (pure
scoring) — it is the bridge between them, not scoring logic itself.
Entrypoint: `python -m core.jobs.score_portfolio`."""

import sys
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import SessionLocal
from core.enums import HealthBand
from core.jobs.fetch import (
    account_context,
    fetch_campaign_facts,
    fetch_stakeholder_facts,
    fetch_value_doc_facts,
)
from core.models import Account, HealthScore
from metrics.config import HealthModelConfig, default_config
from metrics.health import compute_health_score


def score_account(
    session: Session, account: Account, as_of: date, config: HealthModelConfig
) -> HealthScore:
    result = compute_health_score(
        campaigns=fetch_campaign_facts(session, account.account_id),
        value_docs=fetch_value_doc_facts(session, account.account_id),
        stakeholders=fetch_stakeholder_facts(session, account.account_id),
        escalations=[],  # no escalation/ticket data source exists yet
        account=account_context(account),
        as_of=as_of,
        config=config,
    )

    return HealthScore(
        id=uuid.uuid4(),
        account_id=account.account_id,
        scored_at=datetime.now(timezone.utc),
        volume_trajectory_score=result.dimension_scores["volume_trajectory"].score,
        breadth_score=result.dimension_scores["breadth"].score,
        value_realisation_score=result.dimension_scores["value_realisation"].score,
        campaign_quality_score=result.dimension_scores["campaign_quality"].score,
        relationship_coverage_score=result.dimension_scores["relationship_coverage"].score,
        sentiment_friction_score=result.dimension_scores["sentiment_friction"].score,
        composite_score=result.composite_score,
        final_score=result.final_score,
        band=HealthBand(result.band) if result.band else None,
        applied_overrides=[o.name for o in result.applied_overrides],
        null_reasons=result.null_reasons,
        model_version=result.model_version,
    )


def run(as_of: date | None = None) -> int:
    as_of = as_of or date.today()
    config = default_config()
    session = SessionLocal()
    try:
        accounts = session.execute(select(Account).where(Account.valid_to.is_(None))).scalars().all()
        band_counts: dict[str, int] = {}
        for account in accounts:
            health_score = score_account(session, account, as_of, config)
            session.add(health_score)
            key = health_score.band.value if health_score.band else "null"
            band_counts[key] = band_counts.get(key, 0) + 1
        session.commit()
        print(f"Scored {len(accounts)} accounts: {band_counts}")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(run())
