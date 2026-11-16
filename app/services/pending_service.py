from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import PendingAction


async def get_pending_action(session: AsyncSession, telegram_id: int) -> Optional[PendingAction]:
    """Retrieve the currently active pending action for a user."""
    stmt = select(PendingAction).where(PendingAction.telegram_id == telegram_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def set_pending_action(
    session: AsyncSession,
    telegram_id: int,
    state: str,
    giveaway_id: Optional[int] = None,
    entry_id: Optional[int] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> PendingAction:
    """Sets or replaces the user's pending action (DB-backed FSM)."""
    action = await get_pending_action(session, telegram_id)
    if action:
        action.state = state
        action.giveaway_id = giveaway_id
        action.entry_id = entry_id
        action.payload = payload or {}
        action.updated_at = datetime.now(timezone.utc)
    else:
        action = PendingAction(
            telegram_id=telegram_id,
            state=state,
            giveaway_id=giveaway_id,
            entry_id=entry_id,
            payload=payload or {},
        )
        session.add(action)
    await session.flush()
    return action


async def clear_pending_action(session: AsyncSession, telegram_id: int) -> None:
    """Clears any pending action for the user."""
    stmt = delete(PendingAction).where(PendingAction.telegram_id == telegram_id)
    await session.execute(stmt)
    await session.flush()
