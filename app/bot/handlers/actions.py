import logging
from aiogram import Router, F, Bot
from aiogram.types import Message
from sqlalchemy import select

from app.database import get_db_session
from app.models.models import Giveaway, GiveawayMedia, GiveawayAdmin, Entry, User
from app.services.pending_service import get_pending_action, clear_pending_action, set_pending_action
from app.services.giveaway_service import get_giveaway_notify_recipients
from app.bot.keyboards.host import get_draft_menu_keyboard, get_media_menu_keyboard, get_admin_approval_keyboard
from app.bot.keyboards.participant import get_resubmit_keyboard
from app.bot.keyboards.common import get_cancel_keyboard

logger = logging.getLogger("app.bot.actions")
router = Router(name="actions")


@router.message(F.text | F.photo | F.video | F.document)
async def handle_pending_input(message: Message, bot: Bot):
    user_id = message.from_user.id

    async with get_db_session() as session:
        action = await get_pending_action(session, user_id)
        if not action:
            return  # Not in a pending FSM state, let other handlers process or ignore

        state = action.state
        giveaway_id = action.giveaway_id
        entry_id = action.entry_id

        # ----------------------------------------------------------------------
        # 1. EDIT_TITLE
        # ----------------------------------------------------------------------
        if state == "EDIT_TITLE":
            new_title = (message.text or "").strip()
            if len(new_title) < 2 or len(new_title) > 120:
                await message.answer("⚠️ Title must be between 2 and 120 characters. Please try again:", reply_markup=get_cancel_keyboard())
                return
            giveaway = await session.get(Giveaway, giveaway_id)
            if giveaway:
                giveaway.title = new_title
                await session.flush()
                await clear_pending_action(session, user_id)
                await message.answer("✅ Title updated!", reply_markup=get_draft_menu_keyboard(giveaway))
            return

        # ----------------------------------------------------------------------
        # 2. EDIT_DESC
        # ----------------------------------------------------------------------
        if state == "EDIT_DESC":
            desc = (message.text or "").strip()
            giveaway = await session.get(Giveaway, giveaway_id)
            if giveaway:
                giveaway.description = desc
                await session.flush()
                await clear_pending_action(session, user_id)
                await message.answer("✅ Description updated!", reply_markup=get_draft_menu_keyboard(giveaway))
            return

        # ----------------------------------------------------------------------
        # 3. EDIT_RULES
        # ----------------------------------------------------------------------
        if state == "EDIT_RULES":
            rules = (message.text or "").strip()
            giveaway = await session.get(Giveaway, giveaway_id)
            if giveaway:
                giveaway.rules = rules
                await session.flush()
                await clear_pending_action(session, user_id)
                await message.answer("✅ Rules updated!", reply_markup=get_draft_menu_keyboard(giveaway))
            return

        # ----------------------------------------------------------------------
        # 4. EDIT_PRICE
        # ----------------------------------------------------------------------
        if state == "EDIT_PRICE":
            price = (message.text or "").strip()
            giveaway = await session.get(Giveaway, giveaway_id)
            if giveaway:
                giveaway.price_label = price
                await session.flush()
                await clear_pending_action(session, user_id)
                await message.answer("✅ Price & Payment instructions updated!", reply_markup=get_draft_menu_keyboard(giveaway))
            return

        # ----------------------------------------------------------------------
        # 5. ADD_MEDIA
        # ----------------------------------------------------------------------
        if state == "ADD_MEDIA":
            file_id = None
            kind = None
            caption = message.caption or None

            if message.photo:
                file_id = message.photo[-1].file_id
                kind = "photo"
            elif message.video:
                file_id = message.video.file_id
                kind = "video"
            elif message.document:
                file_id = message.document.file_id
                kind = "document"

            if not file_id or not kind:
                await message.answer("⚠️ Please send a valid photo, video, or document file:", reply_markup=get_cancel_keyboard())
                return

            stmt = select(GiveawayMedia).where(GiveawayMedia.giveaway_id == giveaway_id)
            media_list = (await session.execute(stmt)).scalars().all()
            if len(media_list) >= 10:
                await clear_pending_action(session, user_id)
                await message.answer("⚠️ Maximum 10 media items reached.", reply_markup=get_media_menu_keyboard(giveaway_id, 10))
                return

            new_media = GiveawayMedia(
                giveaway_id=giveaway_id,
                kind=kind,
                file_id=file_id,
                caption=caption,
                sort_order=len(media_list) + 1,
            )
            session.add(new_media)
            await session.flush()
            await clear_pending_action(session, user_id)
            await message.answer(f"✅ Media item added! ({len(media_list) + 1}/10)", reply_markup=get_media_menu_keyboard(giveaway_id, len(media_list) + 1))
            return

        # ----------------------------------------------------------------------
        # 6. ADD_ADMIN
        # ----------------------------------------------------------------------
        if state == "ADD_ADMIN":
            target_id = None
            if message.forward_from:
                target_id = message.forward_from.id
            elif message.text and message.text.strip().isdigit():
                target_id = int(message.text.strip())

            if not target_id:
                await message.answer("⚠️ Please enter a numeric Telegram User ID or forward a message from the user:", reply_markup=get_cancel_keyboard())
                return

            giveaway = await session.get(Giveaway, giveaway_id)
            if giveaway and giveaway.host_id == target_id:
                await message.answer("ℹ️ You are already the Host of this giveaway.")
                await clear_pending_action(session, user_id)
                return

            existing = await session.get(GiveawayAdmin, (giveaway_id, target_id))
            if not existing:
                new_admin = GiveawayAdmin(
                    giveaway_id=giveaway_id,
                    telegram_id=target_id,
                    added_by=user_id,
                )
                session.add(new_admin)
                await session.flush()

            await clear_pending_action(session, user_id)
            await message.answer(f"✅ User `{target_id}` added as admin for giveaway #{giveaway_id}!", parse_mode="Markdown")
            return

        # ----------------------------------------------------------------------
        # 7. AWAITING_NAME (Participant)
        # ----------------------------------------------------------------------
        if state == "AWAITING_NAME":
            name = (message.text or "").strip()
            if len(name) < 2 or len(name) > 80:
                await message.answer("⚠️ Name must be between 2 and 80 characters. Please enter your full name:", reply_markup=get_cancel_keyboard())
                return

            giveaway = await session.get(Giveaway, giveaway_id)
            if not giveaway:
                await clear_pending_action(session, user_id)
                await message.answer("Giveaway no longer exists.")
                return

            stmt = select(Entry).where(
                Entry.giveaway_id == giveaway_id,
                Entry.participant_id == user_id,
            )
            existing_entry = (await session.execute(stmt)).scalar_one_or_none()

            if not existing_entry:
                new_entry = Entry(
                    giveaway_id=giveaway_id,
                    participant_id=user_id,
                    full_name=name,
                    status="pending_payment",
                )
                session.add(new_entry)
                await session.flush()
                entry_id = new_entry.id
            else:
                existing_entry.full_name = name
                await session.flush()
                entry_id = existing_entry.id

            await set_pending_action(
                session,
                telegram_id=user_id,
                state="AWAITING_PAYMENT_PROOF",
                giveaway_id=giveaway_id,
                entry_id=entry_id,
            )

            price_info = f"💰 **Price:** {giveaway.price_label}\n" if giveaway.price_label else "💰 **Price:** Free\n"
            proof_prompt = (
                f"👤 Name recorded: **{name}**\n\n"
                f"{price_info}\n"
                "💳 **Payment Instructions:**\n"
                f"{giveaway.rules or 'Please send the required payment as specified by the host.'}\n\n"
                "📸 Now please send your **Proof of Payment** (photo/screenshot or transaction reference text):"
            )
            await message.answer(proof_prompt, reply_markup=get_cancel_keyboard(), parse_mode="Markdown")
            return

        # ----------------------------------------------------------------------
        # 8. AWAITING_PAYMENT_PROOF (Participant)
        # ----------------------------------------------------------------------
        if state == "AWAITING_PAYMENT_PROOF":
            entry = await session.get(Entry, entry_id)
            if not entry:
                await clear_pending_action(session, user_id)
                await message.answer("Entry not found.")
                return

            proof_file_id = None
            payment_note = None

            if message.photo:
                proof_file_id = message.photo[-1].file_id
                payment_note = message.caption
            elif message.document:
                proof_file_id = message.document.file_id
                payment_note = message.caption
            elif message.text:
                payment_note = message.text.strip()
            else:
                await message.answer("⚠️ Please provide a photo/screenshot, document, or transaction text note:", reply_markup=get_cancel_keyboard())
                return

            entry.proof_file_id = proof_file_id
            entry.payment_note = payment_note
            entry.status = "awaiting_approval"
            await session.flush()

            await clear_pending_action(session, user_id)
            await message.answer(
                "✅ **Payment proof received!**\n"
                "The host and admins have been notified. Once approved, you will receive a number grid to claim your number!",
                parse_mode="Markdown",
            )

            # Notify host and admins
            giveaway = await session.get(Giveaway, giveaway_id)
            recipients = await get_giveaway_notify_recipients(session, giveaway_id)
            user_handle = f"@{message.from_user.username}" if message.from_user.username else f"ID: {user_id}"

            notif_text = (
                f"📬 **New Entry Awaiting Approval!**\n\n"
                f"**Giveaway:** {giveaway.title} (#{giveaway.id})\n"
                f"**Participant:** {entry.full_name} ({user_handle})\n"
                f"**Note:** {payment_note or 'None'}"
            )
            approval_kb = get_admin_approval_keyboard(entry.id)

            for admin_tg_id in recipients:
                try:
                    if proof_file_id:
                        await bot.send_photo(
                            chat_id=admin_tg_id,
                            photo=proof_file_id,
                            caption=notif_text,
                            reply_markup=approval_kb,
                            parse_mode="Markdown",
                        )
                    else:
                        await bot.send_message(
                            chat_id=admin_tg_id,
                            text=notif_text,
                            reply_markup=approval_kb,
                            parse_mode="Markdown",
                        )
                except Exception as e:
                    logger.warning(f"Could not notify admin {admin_tg_id}: {e}")
            return

        # ----------------------------------------------------------------------
        # 9. REJECT_REASON (Admin)
        # ----------------------------------------------------------------------
        if state == "REJECT_REASON":
            reason = (message.text or "").strip()
            if not reason:
                await message.answer("Please enter a short reason for rejecting this entry:", reply_markup=get_cancel_keyboard())
                return

            entry = await session.get(Entry, entry_id)
            if not entry:
                await clear_pending_action(session, user_id)
                await message.answer("Entry not found.")
                return

            entry.status = "rejected"
            entry.reject_reason = reason
            entry.resubmit_count += 1
            await session.flush()

            giveaway = await session.get(Giveaway, entry.giveaway_id)
            await clear_pending_action(session, user_id)
            await message.answer(f"❌ Entry #{entry_id} for {entry.full_name} was REJECTED.")

            # Notify participant
            try:
                resubmit_allowed = entry.resubmit_count <= 1
                if resubmit_allowed:
                    dm_text = (
                        f"❌ **Your entry for {giveaway.title} was rejected.**\n\n"
                        f"**Reason:** {reason}\n\n"
                        "You have **1 resubmission attempt** remaining. Tap below to upload updated payment proof:"
                    )
                    kb = get_resubmit_keyboard(giveaway.id)
                    await bot.send_message(chat_id=entry.participant_id, text=dm_text, reply_markup=kb, parse_mode="Markdown")
                else:
                    dm_text = (
                        f"❌ **Your entry for {giveaway.title} was rejected.**\n\n"
                        f"**Reason:** {reason}\n\n"
                        "You have exhausted your resubmission attempts for this giveaway."
                    )
                    await bot.send_message(chat_id=entry.participant_id, text=dm_text, parse_mode="Markdown")
            except Exception as e:
                logger.warning(f"Failed to DM rejected participant {entry.participant_id}: {e}")
            return
