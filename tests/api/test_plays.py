"""The cross-account play log, proven against fixture rows — same style
as test_actions.py / test_reports.py."""

import uuid
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient

from api.main import app
from core.db import get_db
from core.enums import ActionStatus, AutonomyLevel, CommercialModel, PlayType, Quadrant, Tier
from core.models import Account, AccountIdentity, Action, PlayRun


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_play_run(db_session, play=PlayType.DECAY, closed=False, name="Test Co") -> PlayRun:
    identity = AccountIdentity(id=uuid.uuid4())
    db_session.add(identity)
    db_session.flush()

    account = Account(
        id=uuid.uuid4(), account_id=identity.id, name=name, contract_start=date(2025, 1, 1),
        term="monthly", plan="standard", commercial_model=CommercialModel.AD_HOC,
        tier=Tier.T2, quadrant=Quadrant.INVEST,
    )
    play_run = PlayRun(
        id=uuid.uuid4(), account_id=identity.id, play=play,
        opened_at=datetime.now(timezone.utc), closed_at=datetime.now(timezone.utc) if closed else None,
        exit_test_results={"cause_classified": True}, outcome="action_created" if not closed else "recovered",
        cause_classification="person_left",
    )
    db_session.add_all([account, play_run])
    db_session.flush()

    action = Action(
        id=uuid.uuid4(), play_run_id=play_run.id, agent="decay_agent", type="decay_outreach_creator",
        payload={"draft": "hi"}, reasoning="because X", autonomy_level=AutonomyLevel.DRAFT,
        status=ActionStatus.PENDING,
    )
    db_session.add(action)
    db_session.commit()
    return play_run


def test_list_play_runs_includes_account_and_actions(client, db_session):
    _make_play_run(db_session)
    response = client.get("/plays")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["account_name"] == "Test Co"
    assert body[0]["cause_classification"] == "person_left"
    assert len(body[0]["actions"]) == 1
    assert body[0]["actions"][0]["type"] == "decay_outreach_creator"


def test_filter_by_play_type(client, db_session):
    _make_play_run(db_session, play=PlayType.DECAY, name="Decay Co")
    _make_play_run(db_session, play=PlayType.RENEWAL, name="Renewal Co")

    response = client.get("/plays", params={"play": "renewal"})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["account_name"] == "Renewal Co"


def test_filter_by_open_status(client, db_session):
    _make_play_run(db_session, closed=False, name="Open Co")
    _make_play_run(db_session, closed=True, name="Closed Co")

    response = client.get("/plays", params={"status": "open"})
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["account_name"] == "Open Co"


def test_invalid_play_type_400(client, db_session):
    response = client.get("/plays", params={"play": "not_a_play"})
    assert response.status_code == 400


def test_invalid_status_400(client, db_session):
    response = client.get("/plays", params={"status": "not_a_status"})
    assert response.status_code == 400
