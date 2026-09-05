"""Bridges real Postgres into the VoC Router. Entrypoint:
`python -m agents.jobs.run_voc_router`."""

import json
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from agents.llm.config import provider_for
from agents.prompts import load_prompt
from agents.voc_router.router import FeedbackItemFact, dedupe_and_rank
from core.db import SessionLocal
from core.enums import ReportType
from core.jobs.fetch import fetch_campaign_facts
from core.models import Account, FeedbackItem, PortfolioReport
from metrics.derived import REVENUE_PER_DEPARTMENT_PROXY, departments_live


def run(as_of: date | None = None) -> int:
    as_of = as_of or date.today()
    session = SessionLocal()
    try:
        accounts = session.execute(select(Account).where(Account.valid_to.is_(None))).scalars().all()
        revenue_by_account = {
            str(a.account_id): departments_live(fetch_campaign_facts(session, a.account_id), as_of) * REVENUE_PER_DEPARTMENT_PROXY
            for a in accounts
        }

        rows = session.execute(select(FeedbackItem)).scalars().all()
        items = [
            FeedbackItemFact(id=str(r.id), account_id=str(r.account_id), verbatim=r.verbatim, tag=r.tag)
            for r in rows
        ]
        if not items:
            print("No feedback items to route.")
            return 0

        classifier = provider_for("voc_tagging")
        themes, newly_tagged = dedupe_and_rank(items, revenue_by_account, classifier)

        rows_by_id = {str(r.id): r for r in rows}
        for item_id, tag in newly_tagged.items():
            rows_by_id[item_id].tag = tag

        data = {
            "themes": [
                {"tag": t.tag, "accounts_affected": t.accounts_affected,
                 "total_revenue_at_risk": t.total_revenue_at_risk, "account_ids": t.account_ids,
                 "sample_verbatims": t.sample_verbatims}
                for t in themes
            ],
        }
        drafter = provider_for("portfolio_analyst_synthesis")
        response = drafter.complete(
            system="You write the ranked Voice-of-Customer summary for Product.",
            prompt=load_prompt("voc_ranked_list_summary", evidence_json=json.dumps(data, indent=2)),
        )

        session.add(PortfolioReport(
            id=uuid.uuid4(), report_type=ReportType.VOC_RANKED_LIST,
            period_start=as_of - timedelta(days=29), period_end=as_of,
            generated_at=datetime.now(timezone.utc),
            data={**data, "newly_tagged_count": len(newly_tagged)}, narrative=response.text,
        ))
        session.commit()
        print(f"Routed {len(items)} feedback items into {len(themes)} themes, tagged {len(newly_tagged)} new items.")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    sys.exit(run())
