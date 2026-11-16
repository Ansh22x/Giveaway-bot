from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from app.services.rate_limiter import rate_limiter


class RateLimitMiddleware(BaseMiddleware):
    """
    Enforces 20 updates per user per minute and 60 updates per chat per minute.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        chat = data.get("event_chat")

        user_id = user.id if user else 0
        chat_id = chat.id if chat else user_id

        if user_id or chat_id:
            limited, message = rate_limiter.is_rate_limited(user_id, chat_id)
            if limited:
                if isinstance(event, CallbackQuery):
                    await event.answer(message, show_alert=True)
                elif isinstance(event, Message):
                    await event.answer(f"⏳ {message}")
                return None

        return await handler(event, data)
