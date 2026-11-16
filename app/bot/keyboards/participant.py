from typing import Set
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_join_keyboard(giveaway_id: int) -> InlineKeyboardMarkup:
    """Inline Join button attached to public giveaway posts."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎁 Join Giveaway",
                    callback_data=f"join:{giveaway_id}",
                )
            ]
        ]
    )


def get_resubmit_keyboard(giveaway_id: int) -> InlineKeyboardMarkup:
    """Inline button to resubmit rejected payment proof."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Resubmit Proof",
                    callback_data=f"join:{giveaway_id}",
                )
            ]
        ]
    )


def build_number_grid(giveaway_id: int, taken_numbers: Set[int]) -> InlineKeyboardMarkup:
    """
    Builds a 10x10 inline keyboard grid for numbers 1 to 100.
    - Taken numbers: '✓42' (callback_data='noop')
    - Available numbers: '42' (callback_data='pick:<giveaway_id>:<n>')
    """
    rows = []
    # 10 rows of 10 columns = 100 buttons total
    for row_idx in range(10):
        current_row = []
        for col_idx in range(10):
            num = (row_idx * 10) + col_idx + 1
            if num in taken_numbers:
                btn_text = f"✓{num}"
                callback_data = "noop"
            else:
                btn_text = str(num)
                callback_data = f"pick:{giveaway_id}:{num}"
            current_row.append(InlineKeyboardButton(text=btn_text, callback_data=callback_data))
        rows.append(current_row)

    # Add navigation/cancel at the bottom
    rows.append([InlineKeyboardButton(text="❌ Cancel Selection", callback_data="cancel_action")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
