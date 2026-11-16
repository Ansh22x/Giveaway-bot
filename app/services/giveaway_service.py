import csv
import io
import random
from datetime import datetime, timezone
from typing import Optional, Set, List, Tuple
from sqlalchemy import select, update, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import Giveaway, GiveawayAdmin, Entry, User, AuditLog
from app.services.audit_service import log_audit


async def is_giveaway_host(session: AsyncSession, giveaway_id: int, telegram_id: int) -> bool:
    stmt = select(Giveaway.id).where(
        Giveaway.id == giveaway_id,
        Giveaway.host_id == telegram_id,
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none() is not None


async def is_giveaway_admin(session: AsyncSession, giveaway_id: int, telegram_id: int) -> bool:
    # Host is also an admin
    if await is_giveaway_host(session, giveaway_id, telegram_id):
        return True
    stmt = select(GiveawayAdmin.telegram_id).where(
        GiveawayAdmin.giveaway_id == giveaway_id,
        GiveawayAdmin.telegram_id == telegram_id,
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none() is not None


async def get_giveaway_notify_recipients(session: AsyncSession, giveaway_id: int) -> List[int]:
    """Returns list of telegram_ids for the host and all admins for this giveaway."""
    stmt_host = select(Giveaway.host_id).where(Giveaway.id == giveaway_id)
    host_id = (await session.execute(stmt_host)).scalar_one_or_none()

    stmt_admins = select(GiveawayAdmin.telegram_id).where(GiveawayAdmin.giveaway_id == giveaway_id)
    admin_ids = (await session.execute(stmt_admins)).scalars().all()

    recipients = set()
    if host_id:
        recipients.add(host_id)
    recipients.update(admin_ids)
    return list(recipients)


async def get_taken_numbers(session: AsyncSession, giveaway_id: int) -> Set[int]:
    """Returns set of numbers (1-100) already claimed in this giveaway."""
    stmt = select(Entry.number).where(
        Entry.giveaway_id == giveaway_id,
        Entry.number.isnot(None),
    )
    result = await session.execute(stmt)
    return set(result.scalars().all())


async def claim_number_atomic(
    session: AsyncSession,
    giveaway_id: int,
    entry_id: int,
    number: int,
) -> bool:
    """
    Atomic claim of a number 1-100:
    UPDATE entries SET number=$n WHERE id=$entry AND giveaway_id=$g AND number IS NULL
      AND NOT EXISTS (SELECT 1 FROM entries WHERE giveaway_id=$g AND number=$n)
    Returns True if successfully claimed, False on race/collision.
    """
    if number < 1 or number > 100:
        return False

    # Check if number is already taken
    collision_check = select(Entry.id).where(
        Entry.giveaway_id == giveaway_id,
        Entry.number == number,
    ).limit(1)

    stmt = (
        update(Entry)
        .where(
            Entry.id == entry_id,
            Entry.giveaway_id == giveaway_id,
            Entry.number.is_(None),
            ~collision_check.exists(),
        )
        .values(number=number)
    )

    result = await session.execute(stmt)
    await session.flush()
    return result.rowcount > 0


async def count_approved_entries(session: AsyncSession, giveaway_id: int) -> int:
    """Counts entries with status 'approved'."""
    stmt = select(func.count(Entry.id)).where(
        Entry.giveaway_id == giveaway_id,
        Entry.status == "approved",
    )
    result = await session.execute(stmt)
    return result.scalar_one() or 0


async def can_participant_join(
    session: AsyncSession,
    giveaway_id: int,
    participant_id: int,
) -> Tuple[bool, str, Optional[Entry]]:
    """
    Validates if a participant can join or resubmit:
    - Checks giveaway status == 'open'
    - Checks cap of 100 participants
    - Checks existing entry status and resubmit_count
    """
    giveaway = await session.get(Giveaway, giveaway_id)
    if not giveaway:
        return False, "Giveaway not found.", None
    if giveaway.status != "open":
        return False, f"Giveaway is not open (current status: {giveaway.status}).", None

    stmt = select(Entry).where(
        Entry.giveaway_id == giveaway_id,
        Entry.participant_id == participant_id,
    )
    existing_entry = (await session.execute(stmt)).scalar_one_or_none()

    if existing_entry:
        if existing_entry.status == "rejected":
            if existing_entry.resubmit_count < 1:
                return True, "You may resubmit payment proof once.", existing_entry
            else:
                return False, "Your submission was previously rejected and you have exhausted your resubmission attempt.", existing_entry
        elif existing_entry.status in ("pending_payment", "awaiting_approval", "approved"):
            return False, f"You already have an active entry (status: {existing_entry.status}).", existing_entry

    # Check 100 limit
    total_approved = await count_approved_entries(session, giveaway_id)
    if total_approved >= 100:
        return False, "Giveaway is full (100/100 slots approved). You cannot join at this time.", None

    return True, "OK", None


async def draw_winner(
    session: AsyncSession,
    giveaway_id: int,
    host_id: int,
    force: bool = False,
    chosen_number: Optional[int] = None,
) -> Tuple[Optional[Entry], str]:
    """
    Draw winner for a giveaway:
    - Host only check
    - Requires status == 'locked'
    - Mode 'random' or 'number'
    - Idempotent without force
    """
    giveaway = await session.get(Giveaway, giveaway_id)
    if not giveaway:
        return None, "Giveaway not found."

    if giveaway.host_id != host_id:
        return None, "Permission denied: only the host can draw a winner."

    if giveaway.status == "drawn" and not force:
        # Idempotent: return existing winner
        if giveaway.winner_entry_id:
            winner = await session.get(Entry, giveaway.winner_entry_id)
            return winner, "Giveaway was already drawn. Use --force to re-draw."
        return None, "Giveaway was already drawn."

    if giveaway.status != "locked" and giveaway.status != "drawn":
        return None, f"Cannot draw: giveaway must be in 'locked' status (current status: {giveaway.status})."

    # Fetch approved entries that have a number assigned
    stmt = (
        select(Entry)
        .where(
            Entry.giveaway_id == giveaway_id,
            Entry.status == "approved",
            Entry.number.isnot(None),
        )
        .options(selectinload(Entry.participant))
    )
    entries = (await session.execute(stmt)).scalars().all()

    if not entries:
        return None, "Cannot draw: no approved entries with picked numbers found."

    winner_entry: Optional[Entry] = None

    if giveaway.draw_mode == "random":
        winner_entry = random.choice(entries)
    elif giveaway.draw_mode == "number":
        if chosen_number is None or chosen_number < 1 or chosen_number > 100:
            return None, "Draw mode is 'number'. Please specify a valid winning number between 1 and 100."
        for e in entries:
            if e.number == chosen_number:
                winner_entry = e
                break
        if not winner_entry:
            return None, f"No approved participant holds number #{chosen_number}."
    else:
        winner_entry = random.choice(entries)

    giveaway.winner_entry_id = winner_entry.id
    giveaway.status = "drawn"
    giveaway.closed_at = datetime.now(timezone.utc)

    await log_audit(
        session,
        actor_id=host_id,
        action="draw_winner",
        giveaway_id=giveaway_id,
        meta={
            "winner_entry_id": winner_entry.id,
            "winner_participant_id": winner_entry.participant_id,
            "winner_number": winner_entry.number,
            "draw_mode": giveaway.draw_mode,
            "force": force,
        },
    )

    return winner_entry, "Winner drawn successfully!"


async def export_giveaway_csv(session: AsyncSession, giveaway_id: int) -> str:
    """Exports giveaway entries as CSV string."""
    stmt = (
        select(Entry)
        .where(Entry.giveaway_id == giveaway_id)
        .options(selectinload(Entry.participant))
        .order_by(Entry.id.asc())
    )
    entries = (await session.execute(stmt)).scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "entry_id",
        "full_name",
        "username",
        "telegram_id",
        "contact",
        "number",
        "status",
        "approved_at",
        "created_at",
    ])

    for e in entries:
        username = e.participant.username if e.participant and e.participant.username else ""
        approved_at = e.approved_at.isoformat() if e.approved_at else ""
        created_at = e.created_at.isoformat() if e.created_at else ""
        writer.writerow([
            e.id,
            e.full_name,
            f"@{username}" if username else "",
            e.participant_id,
            e.contact or "",
            e.number or "",
            e.status,
            approved_at,
            created_at,
        ])

    return output.getvalue()
