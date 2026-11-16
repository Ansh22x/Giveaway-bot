from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_cancel_keyboard(callback_data: str = "cancel_action") -> InlineKeyboardMarkup:
    """Returns an inline keyboard with a Cancel button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel", callback_data=callback_data)]
        ]
    )


def get_retry_keyboard(callback_data: str = "retry_last") -> InlineKeyboardMarkup:
    """Returns an inline keyboard with Retry and Cancel buttons."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Retry", callback_data=callback_data),
                InlineKeyboardButton(text="❌ Cancel", callback_data="cancel_action"),
            ]
        ]
    )
