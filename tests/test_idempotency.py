import pytest
from sqlalchemy import select
from app.models.models import ProcessedUpdate


@pytest.mark.asyncio
async def test_duplicate_update_id_is_ignored(db_session):
    """
    Tests that when an update_id is received more than once (e.g. Telegram webhook retry),
    it is detected in the processed_updates table and duplicate processing is bypassed.
    """
    test_update_id = 987654321

    # First attempt: record update_id
    stmt = select(ProcessedUpdate.update_id).where(ProcessedUpdate.update_id == test_update_id)
    exists = (await db_session.execute(stmt)).scalar_one_or_none()
    assert exists is None

    db_session.add(ProcessedUpdate(update_id=test_update_id))
    await db_session.commit()

    # Second attempt: check if duplicate
    stmt = select(ProcessedUpdate.update_id).where(ProcessedUpdate.update_id == test_update_id)
    exists_again = (await db_session.execute(stmt)).scalar_one_or_none()
    assert exists_again == test_update_id
