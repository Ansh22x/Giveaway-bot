from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser
from sqlalchemy.dialects.postgresql import insert
from app.database import get_db_session
from app.models.models import User


class UserSyncMiddleware(BaseMiddleware):
    """
    Ensures that every user interacting with the bot is idempotently upserted
    into the `users` table before handlers run.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        tg_user: TgUser = data.get("event_from_user")
        if tg_user:
            try:
                async with get_db_session() as session:
                    # SQLite fallback vs Postgres support
                    stmt = (
                        insert(User)
                        .values(
                            telegram_id=tg_user.id,
                            username=tg_user.username,
                            first_name=tg_user.first_name,
                        )
                        .on_conflict_do_update(
                            index_elements=[User.telegram_id],
                            set_={
                                "username": tg_user.username,
                                "first_name": tg_user.first_name,
                            },
                        )
                    )
                    await session.execute(stmt)
            except Exception:
                pass  # Do not block update if user sync fails

        return await handler(event, data)
