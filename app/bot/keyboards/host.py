from typing import List
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.models.models import Giveaway, GiveawayAdmin


def get_draft_menu_keyboard(giveaway: Giveaway) -> InlineKeyboardMarkup:
    """Inline menu for managing a draft giveaway."""
    mode_text = "🎲 Random" if giveaway.draw_mode == "random" else "🔢 Picked Number"
    buttons = [
        [
            InlineKeyboardButton(text="✏️ Edit Title", callback_data=f"draft:title:{giveaway.id}"),
            InlineKeyboardButton(text="📝 Edit Description", callback_data=f"draft:desc:{giveaway.id}"),
        ],
        [
            InlineKeyboardButton(text="📜 Edit Rules", callback_data=f"draft:rules:{giveaway.id}"),
            InlineKeyboardButton(text="💰 Set Price Label", callback_data=f"draft:price:{giveaway.id}"),
        ],
        [
            InlineKeyboardButton(text="🖼️ Add/Manage Media", callback_data=f"draft:media:{giveaway.id}"),
            InlineKeyboardButton(text=f"⚙️ Draw Mode: {mode_text}", callback_data=f"draft:mode:{giveaway.id}"),
        ],
        [
            InlineKeyboardButton(text="👥 Manage Admins", callback_data=f"draft:admins:{giveaway.id}"),
            InlineKeyboardButton(text="👁️ Preview", callback_data=f"draft:preview:{giveaway.id}"),
        ],
        [
            InlineKeyboardButton(text="🚀 Publish Giveaway", callback_data=f"draft:publish:{giveaway.id}"),
        ],
        [
            InlineKeyboardButton(text="🗑️ Delete Draft", callback_data=f"draft:delete:{giveaway.id}"),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_media_menu_keyboard(giveaway_id: int, current_count: int) -> InlineKeyboardMarkup:
    """Keyboard for media management."""
    buttons = []
    if current_count < 10:
        buttons.append([InlineKeyboardButton(text="➕ Upload Media (Photo/Video/Doc)", callback_data=f"media:upload:{giveaway_id}")])
    if current_count > 0:
        buttons.append([InlineKeyboardButton(text="🗑️ Clear All Media", callback_data=f"media:clear:{giveaway_id}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Back to Giveaway Menu", callback_data=f"draft:menu:{giveaway_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_approval_keyboard(entry_id: int) -> InlineKeyboardMarkup:
    """Keyboard sent to host & admins to review payment proof."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Approve", callback_data=f"appr:{entry_id}"),
                InlineKeyboardButton(text="❌ Reject", callback_data=f"rej:{entry_id}"),
            ]
        ]
    )


def get_admins_management_keyboard(giveaway_id: int, admins: List[GiveawayAdmin]) -> InlineKeyboardMarkup:
    """Keyboard for listing and managing giveaway admins."""
    buttons = []
    for admin in admins:
        buttons.append([
            InlineKeyboardButton(
                text=f"❌ Remove Admin {admin.telegram_id}",
                callback_data=f"rm_admin:{giveaway_id}:{admin.telegram_id}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="➕ Add Admin", callback_data=f"add_admin:{giveaway_id}")])
    buttons.append([InlineKeyboardButton(text="⬅️ Back to Menu", callback_data=f"draft:menu:{giveaway_id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
