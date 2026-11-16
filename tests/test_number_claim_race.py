import asyncio
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.models.models import User, Giveaway, Entry
from app.services.giveaway_service import claim_number_atomic, get_taken_numbers
from app.bot.keyboards.participant import build_number_grid


@pytest.mark.asyncio
async def test_two_users_race_for_same_number(test_engine):
    """
    Test that when two users concurrently attempt to claim the exact same number,
    exactly one user wins and receives True, while the loser receives False
    and the number grid is updated.
    """
    session_maker = async_sessionmaker(bind=test_engine, expire_on_commit=False, class_=AsyncSession)

    # Setup initial state
    async with session_maker() as session:
        host = User(telegram_id=1000, username="host", first_name="Host")
        user_a = User(telegram_id=2001, username="user_a", first_name="Alice")
        user_b = User(telegram_id=2002, username="user_b", first_name="Bob")
        session.add_all([host, user_a, user_b])
        await session.flush()

        giveaway = Giveaway(
            host_id=host.telegram_id,
            title="Race Test Giveaway",
            status="open",
        )
        session.add(giveaway)
        await session.flush()

        entry_a = Entry(
            giveaway_id=giveaway.id,
            participant_id=user_a.telegram_id,
            full_name="Alice Smith",
            status="approved",
        )
        entry_b = Entry(
            giveaway_id=giveaway.id,
            participant_id=user_b.telegram_id,
            full_name="Bob Jones",
            status="approved",
        )
        session.add_all([entry_a, entry_b])
        await session.commit()
        giveaway_id = giveaway.id
        entry_a_id = entry_a.id
        entry_b_id = entry_b.id

    # Simulate concurrent race for number 42
    target_number = 42

    async def attempt_claim(entry_id: int):
        async with session_maker() as session:
            success = await claim_number_atomic(session, giveaway_id, entry_id, target_number)
            await session.commit()
            return success

    results = await asyncio.gather(
        attempt_claim(entry_a_id),
        attempt_claim(entry_b_id),
    )

    # Exactly one must succeed, one must fail
    assert sum(1 for r in results if r is True) == 1
    assert sum(1 for r in results if r is False) == 1

    # Verify database state
    async with session_maker() as session:
        taken = await get_taken_numbers(session, giveaway_id)
        assert target_number in taken

        # Loser receives updated 10x10 grid with the number marked as taken (✓42)
        grid = build_number_grid(giveaway_id, taken)
        grid_buttons = [btn for row in grid.inline_keyboard for btn in row]
        taken_btn = next((b for b in grid_buttons if b.text == f"✓{target_number}"), None)
        assert taken_btn is not None
        assert taken_btn.callback_data == "noop"
