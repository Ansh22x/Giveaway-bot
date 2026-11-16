import logging
import traceback
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from app.bot.keyboards.common import get_retry_keyboard

logger = logging.getLogger("app.bot.errors")


class GlobalErrorMiddleware(BaseMiddleware):
    """
    Catches any unhandled exceptions, logs structured traceback,
    and returns a friendly error with a Retry button.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception as e:
            user = data.get("event_from_user")
            user_id = user.id if user else 0

            logger.error(
                f"Unhandled exception during handler execution: {e}",
                extra={
                    "telegram_id": user_id,
                    "action": "handler_error",
                },
                exc_info=True,
            )

            error_text = (
                "⚠️ Something unexpected went wrong while processing your request.\n"
                "Our team has been notified. Please try again."
            )
            retry_kb = get_retry_keyboard()

            try:
                if isinstance(event, CallbackQuery):
                    await event.answer("An error occurred. Please retry.", show_alert=True)
                    if event.message:
                        await event.message.answer(error_text, reply_markup=retry_kb)
                elif isinstance(event, Message):
                    await event.answer(error_text, reply_markup=retry_kb)
            except Exception:
                pass  # Fallback if reply itself fails

            return None
