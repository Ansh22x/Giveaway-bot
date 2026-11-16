import pytest
from app.models.models import User, Giveaway, Entry
from app.services.giveaway_service import can_participant_join


@pytest.mark.asyncio
async def test_101st_participant_capped_at_100_slots(db_session):
    """
    Validates that once 100 approved participants are registered,
    the 101st participant cannot join and receives the giveaway full message.
    """
    host = User(telegram_id=7000, username="host", first_name="Host")
    db_session.add(host)
    await db_session.flush()

    giveaway = Giveaway(
        host_id=host.telegram_id,
        title="Cap Test Giveaway",
        status="open",
    )
    db_session.add(giveaway)
    await db_session.flush()

    # Seed 100 approved entries
    entries = []
    users = []
    for i in range(1, 101):
        u = User(telegram_id=8000 + i, username=f"user_{i}", first_name=f"Player {i}")
        users.append(u)
        e = Entry(
            giveaway_id=giveaway.id,
            participant_id=8000 + i,
            full_name=f"Player {i}",
            status="approved",
            number=i,
        )
        entries.append(e)

    db_session.add_all(users)
    await db_session.flush()
    db_session.add_all(entries)
    await db_session.commit()

    # 101st user attempts to join
    user_101 = User(telegram_id=9999, username="user_101", first_name="Player 101")
    db_session.add(user_101)
    await db_session.commit()

    can_join, reason, _ = await can_participant_join(db_session, giveaway.id, user_101.telegram_id)
    assert can_join is False
    assert "Giveaway is full (100/100 slots approved)" in reason
