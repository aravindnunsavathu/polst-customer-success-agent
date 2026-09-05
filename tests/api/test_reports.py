"""Read-only /reports endpoints, proven against fixture rows — same
style as test_actions.py."""

import uuid
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from api.main import app
from core.db import get_db
from core.enums import ReportType
from core.models import PortfolioReport


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_report(db_session, report_type=ReportType.AT_RISK_CRITICAL_REVIEW) -> PortfolioReport:
    report = PortfolioReport(
        id=uuid.uuid4(), report_type=report_type, period_start=date(2026, 1, 1), period_end=date(2026, 1, 7),
        generated_at=datetime.now(timezone.utc), data={"count": 3}, narrative="Three accounts flagged.",
    )
    db_session.add(report)
    db_session.commit()
    return report


def test_list_reports(client, db_session):
    _make_report(db_session)
    response = client.get("/reports")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["report_type"] == "at_risk_critical_review"
    assert body[0]["narrative"] == "Three accounts flagged."


def test_list_reports_filters_by_type(client, db_session):
    _make_report(db_session, ReportType.AT_RISK_CRITICAL_REVIEW)
    _make_report(db_session, ReportType.WATCH_REVIEW)

    response = client.get("/reports", params={"type": "watch_review"})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["report_type"] == "watch_review"


def test_list_reports_rejects_unknown_type(client, db_session):
    response = client.get("/reports", params={"type": "not_a_real_type"})
    assert response.status_code == 400


def test_get_report_by_id(client, db_session):
    report = _make_report(db_session)
    response = client.get(f"/reports/{report.id}")
    assert response.status_code == 200
    assert response.json()["id"] == str(report.id)


def test_get_report_404_when_missing(client, db_session):
    response = client.get(f"/reports/{uuid.uuid4()}")
    assert response.status_code == 404


def test_get_report_400_on_bad_uuid(client, db_session):
    response = client.get("/reports/not-a-uuid")
    assert response.status_code == 400
