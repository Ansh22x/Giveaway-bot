from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery
from sqlalchemy import select

from app.database import get_db_session
from app.models.models import Giveaway, Entry
from app.services.giveaway_service import (
    can_participant_join,
    claim_number_atomic,
    get_taken_numbers,
)
from app.services.pending_service import set_pending_action, clear_pending_action
from app.bot.keyboards.participant import build_number_grid
from app.bot.keyboards.common import get_cancel_keyboard

router = Router(name="participant")


@router.callback_query(F.data.startswith("join:"))
async def cb_join_giveaway(callback: CallbackQuery, bot: Bot):
    giveaway_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    async with get_db_session() as session:
        can_join, reason, existing_entry = await can_participant_join(session, giveaway_id, user_id)
        giveaway = await session.get(Giveaway, giveaway_id)

        if not can_join:
            await callback.answer(f"⚠️ {reason}", show_alert=True)
            return

        if existing_entry and existing_entry.status == "rejected":
            # Resubmission flow
            await set_pending_action(
                session,
                telegram_id=user_id,
                state="AWAITING_PAYMENT_PROOF",
                giveaway_id=giveaway_id,
                entry_id=existing_entry.id,
            )
            price_text = f"Price: {giveaway.price_label}\n" if giveaway.price_label else ""
            await callback.answer()
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"🔄 **Resubmitting Payment Proof for {giveaway.title}**\n\n"
                        f"{price_text}\n"
                        "Please upload your updated payment proof (screenshot/receipt photo) or text transaction note:"
                    ),
                    reply_markup=get_cancel_keyboard(),
                    parse_mode="Markdown",
                )
            except Exception:
                await callback.message.answer(
                    "⚠️ Please start the bot in private chat (@YourBot) first so we can DM you!"
                )
            return

        # New participant registration flow
        await set_pending_action(
            session,
            telegram_id=user_id,
            state="AWAITING_NAME",
            giveaway_id=giveaway_id,
        )

    await callback.answer()
    prompt_text = (
        f"🎉 **Joining {giveaway.title}**\n\n"
        "To get started, please reply with your **Full Name** (2–80 characters):"
    )
    try:
        await bot.send_message(
            chat_id=user_id,
            text=prompt_text,
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )
    except Exception:
        await callback.message.answer(
            f"👤 {callback.from_user.first_name}, please send a DM to the bot first to join!",
            reply_markup=get_cancel_keyboard(),
        )


@router.callback_query(F.data.startswith("pick:"))
async def cb_pick_number(callback: CallbackQuery):
    parts = callback.data.split(":")
    giveaway_id = int(parts[1])
    chosen_number = int(parts[2])
    user_id = callback.from_user.id

    async with get_db_session() as session:
        stmt = select(Entry).where(
            Entry.giveaway_id == giveaway_id,
            Entry.participant_id == user_id,
        )
        entry = (await session.execute(stmt)).scalar_one_or_none()
        if not entry:
            await callback.answer("Entry not found.", show_alert=True)
            return

        if entry.status != "approved":
            await callback.answer(f"Your entry status is '{entry.status}'. You cannot pick a number yet.", show_alert=True)
            return

        if entry.number is not None:
            await callback.answer(f"You have already confirmed number #{entry.number}!", show_alert=True)
            return

        # Attempt atomic claim
        claimed = await claim_number_atomic(
            session=session,
            giveaway_id=giveaway_id,
            entry_id=entry.id,
            number=chosen_number,
        )

        giveaway = await session.get(Giveaway, giveaway_id)
        taken_numbers = await get_taken_numbers(session, giveaway_id)

        if claimed:
            await clear_pending_action(session, user_id)
            await callback.answer(f"🎉 Number #{chosen_number} claimed successfully!", show_alert=True)
            if callback.message:
                await callback.message.edit_text(
                    f"🎉 **CONFIRMATION** 🎉\n\n"
                    f"**Giveaway:** {giveaway.title}\n"
                    f"**Participant:** {entry.full_name}\n"
                    f"**Locked Number:** #{chosen_number}\n\n"
                    "Your lucky number is locked in! Best of luck during the draw. 🍀",
                    reply_markup=None,
                    parse_mode="Markdown",
                )
        else:
            # Race condition: someone else claimed the number in the meantime!
            await callback.answer(f"⚠️ Number #{chosen_number} was just taken! Pick another number.", show_alert=True)
            grid_kb = build_number_grid(giveaway_id, taken_numbers)
            if callback.message:
                await callback.message.edit_text(
                    f"⚠️ **Number #{chosen_number} was just taken by another participant!**\n\n"
                    f"Please select an available number from the updated grid below:",
                    reply_markup=grid_kb,
                    parse_mode="Markdown",
                )
