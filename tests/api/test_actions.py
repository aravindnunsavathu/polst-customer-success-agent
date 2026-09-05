"""The approval queue's approve/reject mechanics, proven against fixture
rows since no agent populates real actions yet (Phase 4+)."""

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from api.main import app
from core.db import get_db
from core.enums import ActionStatus, AutonomyLevel, CommercialModel, Quadrant, Tier
from core.models import Account, AccountIdentity, Action


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_pending_action(db_session) -> Action:
    # No relationship() links AccountIdentity/Account (deliberately, see
    # seed/cli.py) so SQLAlchemy can't infer insert order — flush the
    # identity before the row that references it.
    identity = AccountIdentity(id=uuid.uuid4())
    db_session.add(identity)
    db_session.flush()

    account = Account(
        id=uuid.uuid4(), account_id=identity.id, name="Test Co", contract_start=date(2025, 1, 1),
        term="monthly", plan="standard", commercial_model=CommercialModel.AD_HOC,
        tier=Tier.T2, quadrant=Quadrant.INVEST,
    )
    action = Action(
        id=uuid.uuid4(), play_run_id=None, agent="decay_agent", type="draft_email",
        payload={"subject": "test"}, reasoning="because X", autonomy_level=AutonomyLevel.DRAFT,
        status=ActionStatus.PENDING,
    )
    db_session.add_all([account, action])
    db_session.commit()
    return action


def test_approve_action(client, db_session):
    action = _make_pending_action(db_session)
    response = client.post(f"/actions/{action.id}/approve", json={"approved_by": "vp_cs"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["approved_by"] == "vp_cs"


def test_reject_action_requires_valid_category(client, db_session):
    action = _make_pending_action(db_session)
    response = client.post(
        f"/actions/{action.id}/reject", json={"rejection_reason_category": "not-a-real-category"}
    )
    assert response.status_code == 400


def test_reject_action_with_valid_reason(client, db_session):
    action = _make_pending_action(db_session)
    response = client.post(
        f"/actions/{action.id}/reject",
        json={"rejection_reason_category": "volume_pushing", "rejection_reason_detail": "leads with usage stats"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["rejection_reason_category"] == "volume_pushing"
    assert body["rejection_reason_detail"] == "leads with usage stats"


def test_cannot_decide_an_already_decided_action(client, db_session):
    action = _make_pending_action(db_session)
    client.post(f"/actions/{action.id}/approve", json={"approved_by": "vp_cs"})
    response = client.post(f"/actions/{action.id}/approve", json={"approved_by": "vp_cs"})
    assert response.status_code == 409


def test_list_actions_filters_by_status(client, db_session):
    _make_pending_action(db_session)
    response = client.get("/actions", params={"status": "pending"})
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = client.get("/actions", params={"status": "approved"})
    assert response.status_code == 200
    assert len(response.json()) == 0
