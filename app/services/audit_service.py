from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import AuditLog


async def log_audit(
    session: AsyncSession,
    actor_id: int,
    action: str,
    giveaway_id: Optional[int] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> AuditLog:
    """Records an immutable audit event."""
    audit_entry = AuditLog(
        actor_id=actor_id,
        action=action,
        giveaway_id=giveaway_id,
        meta=meta or {},
    )
    session.add(audit_entry)
    await session.flush()
    return audit_entry
