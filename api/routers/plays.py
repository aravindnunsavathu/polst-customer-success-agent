"""The play log (BUILD-PROMPT.md §8.4): "every run, its exit test
result, cause classification, and outcome." Read-only, cross-account —
unlike GET /accounts/{id}'s play_runs (scoped to one account), this is
the portfolio-wide view "what turns v0.1 into a real playbook after two
quarters" needs."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.schemas import PlayLogActionOut, PlayRunLogOut
from core.db import get_db
from core.enums import PlayType
from core.models import Account, Action, PlayRun

router = APIRouter(prefix="/plays", tags=["plays"])


def _to_out(play_run: PlayRun, account: Account, actions: list[Action]) -> PlayRunLogOut:
    return PlayRunLogOut(
        id=str(play_run.id),
        account_id=str(play_run.account_id),
        account_name=account.name,
        tier=account.tier.value,
        play=play_run.play.value,
        opened_at=play_run.opened_at,
        closed_at=play_run.closed_at,
        outcome=play_run.outcome,
        cause_classification=play_run.cause_classification,
        exit_test_results=play_run.exit_test_results or {},
        actions=[
            PlayLogActionOut(
                id=str(a.id), agent=a.agent, type=a.type, autonomy_level=a.autonomy_level.value,
                status=a.status.value, reasoning=a.reasoning, created_at=a.created_at,
            )
            for a in actions
        ],
    )


@router.get("", response_model=list[PlayRunLogOut])
def list_play_runs(
    play: str | None = None, status: str | None = None, db: Session = Depends(get_db)
) -> list[PlayRunLogOut]:
    """`status`: "open" | "closed", optional. `play`: a PlayType value, optional."""
    query = select(PlayRun, Account).join(Account, Account.account_id == PlayRun.account_id).where(
        Account.valid_to.is_(None)
    )
    if play:
        try:
            query = query.where(PlayRun.play == PlayType(play))
        except ValueError:
            valid = ", ".join(p.value for p in PlayType)
            raise HTTPException(status_code=400, detail=f"play must be one of: {valid}")
    if status == "open":
        query = query.where(PlayRun.closed_at.is_(None))
    elif status == "closed":
        query = query.where(PlayRun.closed_at.is_not(None))
    elif status is not None:
        raise HTTPException(status_code=400, detail="status must be 'open' or 'closed'")

    rows = db.execute(query.order_by(PlayRun.opened_at.desc())).all()
    play_run_ids = [pr.id for pr, _ in rows]
    actions_by_play_run: dict = {}
    if play_run_ids:
        action_rows = db.execute(
            select(Action).where(Action.play_run_id.in_(play_run_ids)).order_by(Action.created_at)
        ).scalars().all()
        for a in action_rows:
            actions_by_play_run.setdefault(a.play_run_id, []).append(a)

    return [_to_out(pr, account, actions_by_play_run.get(pr.id, [])) for pr, account in rows]
