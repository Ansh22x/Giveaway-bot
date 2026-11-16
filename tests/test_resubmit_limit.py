import pytest
from app.models.models import User, Giveaway, Entry
from app.services.giveaway_service import can_participant_join


@pytest.mark.asyncio
async def test_rejected_user_can_resubmit_once_not_twice(db_session):
    """
    Validates that a participant whose payment proof was rejected
    is permitted to resubmit exactly once (resubmit_count=0 -> 1),
    and is blocked if attempting to resubmit again (resubmit_count >= 1).
    """
    host = User(telegram_id=6001, username="host", first_name="Host")
    user = User(telegram_id=6002, username="applicant", first_name="Applicant")
    db_session.add_all([host, user])
    await db_session.flush()

    giveaway = Giveaway(
        host_id=host.telegram_id,
        title="Resubmit Test Giveaway",
        status="open",
    )
    db_session.add(giveaway)
    await db_session.flush()

    # Entry is rejected for the first time (resubmit_count = 0)
    entry = Entry(
        giveaway_id=giveaway.id,
        participant_id=user.telegram_id,
        full_name="Applicant One",
        status="rejected",
        reject_reason="Invalid receipt screenshot",
        resubmit_count=0,
    )
    db_session.add(entry)
    await db_session.commit()

    # Check 1: Can resubmit once
    can_join, reason, matched_entry = await can_participant_join(db_session, giveaway.id, user.telegram_id)
    assert can_join is True
    assert "You may resubmit payment proof once." in reason
    assert matched_entry.id == entry.id

    # Simulate admin rejecting the resubmission (resubmit_count becomes 1)
    entry.resubmit_count = 1
    await db_session.commit()

    # Check 2: Cannot resubmit a second time
    can_join_again, reason_again, matched_entry_again = await can_participant_join(db_session, giveaway.id, user.telegram_id)
    assert can_join_again is False
    assert "exhausted your resubmission attempt" in reason_again
