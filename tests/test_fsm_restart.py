import pytest
from app.models.models import User, Giveaway, Entry, PendingAction
from app.services.pending_service import get_pending_action, set_pending_action
from app.services.giveaway_service import claim_number_atomic, get_taken_numbers
from app.bot.keyboards.participant import build_number_grid


@pytest.mark.asyncio
async def test_restart_mid_number_pick_resumes_from_db(db_session):
    """
    Simulates a server restart while a user was in the middle of picking a number.
    Ensures state is fully persisted in the DB pending_actions table and can resume seamlessly.
    """
    user = User(telegram_id=3001, username="charlie", first_name="Charlie")
    db_session.add(user)
    await db_session.flush()

    giveaway = Giveaway(
        host_id=user.telegram_id,
        title="FSM Survival Giveaway",
        status="open",
    )
    db_session.add(giveaway)
    await db_session.flush()

    entry = Entry(
        giveaway_id=giveaway.id,
        participant_id=user.telegram_id,
        full_name="Charlie Brown",
        status="approved",
    )
    db_session.add(entry)
    await db_session.flush()

    # User is in state PICKING_NUMBER
    await set_pending_action(
        db_session,
        telegram_id=user.telegram_id,
        state="PICKING_NUMBER",
        giveaway_id=giveaway.id,
        entry_id=entry.id,
    )
    await db_session.commit()

    # --- SIMULATE PROCESS RESTART ---
    # In-memory RAM is lost, new request arrives, read pending state from DB:
    resumed_action = await get_pending_action(db_session, user.telegram_id)
    assert resumed_action is not None
    assert resumed_action.state == "PICKING_NUMBER"
    assert resumed_action.giveaway_id == giveaway.id
    assert resumed_action.entry_id == entry.id

    # The user picks number 17 after restart
    success = await claim_number_atomic(
        db_session,
        giveaway_id=resumed_action.giveaway_id,
        entry_id=resumed_action.entry_id,
        number=17,
    )
    assert success is True

    # Check updated entry
    await db_session.refresh(entry)
    assert entry.number == 17
