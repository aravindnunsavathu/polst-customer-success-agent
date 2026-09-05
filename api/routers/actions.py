"""The approval queue (BUILD-PROMPT.md §8.3): approve / reject-with-reason
actions. No agent populates `actions` yet (Phase 4+) — still no LLM
drafting per the Phase 3 sequencing rationale — so this queue is
legitimately empty against real data today. The mechanics (mandatory
structured rejection reason especially) are proven by
tests/api/test_actions.py against fixture rows."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.schemas import ActionOut, ApproveRequest, RejectRequest
from core.db import get_db
from core.enums import ActionStatus, RejectionReasonCategory
from core.models import Action

router = APIRouter(prefix="/actions", tags=["actions"])


def _to_out(action: Action) -> ActionOut:
    return ActionOut(
        id=str(action.id),
        play_run_id=str(action.play_run_id) if action.play_run_id else None,
        agent=action.agent,
        type=action.type,
        payload=action.payload or {},
        reasoning=action.reasoning,
        autonomy_level=action.autonomy_level.value,
        status=action.status.value,
        approved_by=action.approved_by,
        rejection_reason_category=(
            action.rejection_reason_category.value if action.rejection_reason_category else None
        ),
        rejection_reason_detail=action.rejection_reason_detail,
        created_at=action.created_at,
    )


@router.get("", response_model=list[ActionOut])
def list_actions(status: str | None = None, db: Session = Depends(get_db)) -> list[ActionOut]:
    query = select(Action)
    if status:
        try:
            query = query.where(Action.status == ActionStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"unknown status {status!r}")
    actions = db.execute(query.order_by(Action.created_at.desc())).scalars().all()
    return [_to_out(a) for a in actions]


def _get_pending_action(db: Session, action_id: str) -> Action:
    try:
        action_uuid = uuid.UUID(action_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="action_id must be a UUID")
    action = db.get(Action, action_uuid)
    if action is None:
        raise HTTPException(status_code=404, detail="action not found")
    if action.status != ActionStatus.PENDING:
        raise HTTPException(status_code=409, detail=f"action is already {action.status.value}")
    return action


@router.post("/{action_id}/approve", response_model=ActionOut)
def approve_action(action_id: str, body: ApproveRequest, db: Session = Depends(get_db)) -> ActionOut:
    action = _get_pending_action(db, action_id)
    action.status = ActionStatus.APPROVED
    action.approved_by = body.approved_by
    db.commit()
    db.refresh(action)
    return _to_out(action)


@router.post("/{action_id}/reject", response_model=ActionOut)
def reject_action(action_id: str, body: RejectRequest, db: Session = Depends(get_db)) -> ActionOut:
    action = _get_pending_action(db, action_id)
    try:
        category = RejectionReasonCategory(body.rejection_reason_category)
    except ValueError:
        valid = ", ".join(c.value for c in RejectionReasonCategory)
        raise HTTPException(status_code=400, detail=f"rejection_reason_category must be one of: {valid}")
    action.status = ActionStatus.REJECTED
    action.rejection_reason_category = category
    action.rejection_reason_detail = body.rejection_reason_detail
    db.commit()
    db.refresh(action)
    return _to_out(action)
