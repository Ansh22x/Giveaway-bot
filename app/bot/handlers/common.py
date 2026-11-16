from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from app.database import get_db_session
from app.services.pending_service import clear_pending_action

router = Router(name="common")


@router.message(CommandStart())
async def cmd_start(message: Message):
    text = (
        "🎉 **Welcome to Ultra Giveaway Bot!**\n\n"
        "The production-grade Telegram raffle and giveaway platform.\n\n"
        "**Host Commands:**\n"
        "• `/new` - Create a new giveaway raffle\n"
        "• `/list` - View approved entries (paginated)\n"
        "• `/pending` - Review awaiting approval queue\n"
        "• `/open <id>` - Open giveaway for participation\n"
        "• `/lock <id>` - Lock giveaway before draw\n"
        "• `/draw <id> [--force] [number]` - Draw winner\n"
        "• `/cancel <id>` - Cancel giveaway\n"
        "• `/export <id>` - Export participant roster as CSV\n\n"
        "Need help or want to create your first raffle? Type `/new` to get started!"
    )
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "📖 **Ultra Giveaway Help Guide**\n\n"
        "**For Hosts & Admins:**\n"
        "1. Start with `/new` to draft your raffle.\n"
        "2. Add your title, description, rules, media, and price.\n"
        "3. Hit **Publish** when ready. Share the post into your channels or groups!\n"
        "4. Review and approve incoming participant payments via inline buttons.\n"
        "5. When all 100 slots are taken, use `/lock <id>` and then `/draw <id>`.\n\n"
        "**For Participants:**\n"
        "1. Click **🎁 Join Giveaway** on an active raffle.\n"
        "2. Submit your full name and payment proof.\n"
        "3. Once approved, you will receive an interactive 10x10 grid to choose your lucky number (1–100)!"
    )
    await message.answer(text, parse_mode="Markdown")


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer("This slot is already taken!", show_alert=False)


@router.callback_query(F.data == "cancel_action")
async def cb_cancel_action(callback: CallbackQuery):
    async with get_db_session() as session:
        await clear_pending_action(session, callback.from_user.id)
    await callback.answer("Action cancelled.", show_alert=False)
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("❌ Current operation cancelled.")


@router.callback_query(F.data == "retry_last")
async def cb_retry_last(callback: CallbackQuery):
    await callback.answer("Please send the command or tap the button again.")
