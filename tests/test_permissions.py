import pytest
from app.models.models import User, Giveaway, Entry, GiveawayAdmin
from app.services.giveaway_service import is_giveaway_admin, is_giveaway_host, draw_winner


@pytest.mark.asyncio
async def test_non_admin_cannot_approve_and_non_host_cannot_draw(db_session):
    """
    Enforces server-side DB permission checks:
    - Non-admin cannot approve entries
    - Non-host cannot draw winners
    """
    host = User(telegram_id=5001, username="true_host", first_name="Host")
    admin = User(telegram_id=5002, username="giveaway_admin", first_name="Admin")
    random_user = User(telegram_id=5003, username="random_user", first_name="Rando")
    db_session.add_all([host, admin, random_user])
    await db_session.flush()

    giveaway = Giveaway(
        host_id=host.telegram_id,
        title="Permission Check Giveaway",
        status="locked",
    )
    db_session.add(giveaway)
    await db_session.flush()

    # Assign admin
    giveaway_admin_link = GiveawayAdmin(
        giveaway_id=giveaway.id,
        telegram_id=admin.telegram_id,
        added_by=host.telegram_id,
    )
    db_session.add(giveaway_admin_link)

    # Participant entry
    participant = User(telegram_id=5004, username="part", first_name="Participant")
    db_session.add(participant)
    await db_session.flush()

    entry = Entry(
        giveaway_id=giveaway.id,
        participant_id=participant.telegram_id,
        full_name="Valid Player",
        status="approved",
        number=7,
    )
    db_session.add(entry)
    await db_session.commit()

    # Test 1: Random user is NOT an admin
    assert await is_giveaway_admin(db_session, giveaway.id, random_user.telegram_id) is False

    # Test 2: Admin IS an admin, but is NOT the host
    assert await is_giveaway_admin(db_session, giveaway.id, admin.telegram_id) is True
    assert await is_giveaway_host(db_session, giveaway.id, admin.telegram_id) is False

    # Test 3: Admin cannot draw (host only)
    winner, msg = await draw_winner(
        session=db_session,
        giveaway_id=giveaway.id,
        host_id=admin.telegram_id,
    )
    assert winner is None
    assert "Permission denied: only the host can draw a winner." in msg

    # Test 4: Host CAN draw
    winner, msg = await draw_winner(
        session=db_session,
        giveaway_id=giveaway.id,
        host_id=host.telegram_id,
    )
    assert winner is not None
    assert winner.id == entry.id
    assert giveaway.status == "drawn"
