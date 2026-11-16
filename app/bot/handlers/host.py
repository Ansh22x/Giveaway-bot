import io
from datetime import datetime, timezone
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    BufferedInputFile,
    InputMediaPhoto,
    InputMediaVideo,
    InputMediaDocument,
)
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from app.database import get_db_session
from app.models.models import Giveaway, GiveawayAdmin, GiveawayMedia, Entry, User
from app.services.giveaway_service import (
    is_giveaway_host,
    is_giveaway_admin,
    draw_winner,
    export_giveaway_csv,
    get_taken_numbers,
)
from app.services.pending_service import set_pending_action, clear_pending_action
from app.services.audit_service import log_audit
from app.bot.keyboards.host import (
    get_draft_menu_keyboard,
    get_media_menu_keyboard,
    get_admins_management_keyboard,
    get_admin_approval_keyboard,
)
from app.bot.keyboards.participant import get_join_keyboard, build_number_grid
from app.bot.keyboards.common import get_cancel_keyboard
from app.bot.utils import chunk_text, truncate_caption

router = Router(name="host")


def format_giveaway_post(giveaway: Giveaway, preview: bool = False) -> str:
    prefix = "👀 **[PREVIEW MODE]**\n\n" if preview else ""
    price_info = f"💰 **Price:** {giveaway.price_label}\n" if giveaway.price_label else "💰 **Price:** Free\n"
    rules_info = f"\n📜 **Rules:**\n{giveaway.rules}\n" if giveaway.rules else ""
    desc_info = f"\n{giveaway.description}\n" if giveaway.description else ""

    text = (
        f"{prefix}🎁 **{giveaway.title}**\n\n"
        f"{desc_info}"
        f"{price_info}"
        f"{rules_info}\n"
        f"🔢 Total numbers available: 100\n"
        f"🎯 Draw Mode: {giveaway.draw_mode.capitalize()}\n"
    )
    return text


@router.message(Command("new"))
async def cmd_new(message: Message):
    """Creates a new draft giveaway."""
    async with get_db_session() as session:
        giveaway = Giveaway(
            host_id=message.from_user.id,
            title="✨ New Ultra Giveaway",
            status="draft",
            draw_mode="random",
        )
        session.add(giveaway)
        await session.flush()

        await log_audit(
            session,
            actor_id=message.from_user.id,
            action="create_draft",
            giveaway_id=giveaway.id,
        )

        kb = get_draft_menu_keyboard(giveaway)
        text = (
            f"🛠️ **Giveaway #{giveaway.id} Draft Created!**\n\n"
            f"**Title:** {giveaway.title}\n"
            f"**Draw Mode:** {giveaway.draw_mode}\n\n"
            "Use the buttons below to customize your giveaway before publishing:"
        )
        await message.answer(text, reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data.startswith("draft:menu:"))
async def cb_draft_menu(callback: CallbackQuery):
    giveaway_id = int(callback.data.split(":")[2])
    async with get_db_session() as session:
        giveaway = await session.get(Giveaway, giveaway_id)
        if not giveaway:
            await callback.answer("Giveaway not found.", show_alert=True)
            return

        if not await is_giveaway_admin(session, giveaway.id, callback.from_user.id):
            await callback.answer("Permission denied.", show_alert=True)
            return

        kb = get_draft_menu_keyboard(giveaway)
        text = (
            f"🛠️ **Giveaway #{giveaway.id} Configuration**\n\n"
            f"**Title:** {giveaway.title}\n"
            f"**Description:** {giveaway.description or 'Not set'}\n"
            f"**Rules:** {giveaway.rules or 'Not set'}\n"
            f"**Price Label:** {giveaway.price_label or 'Free'}\n"
            f"**Draw Mode:** {giveaway.draw_mode}\n"
            f"**Status:** {giveaway.status.upper()}"
        )
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data.startswith("draft:title:"))
async def cb_draft_title(callback: CallbackQuery):
    giveaway_id = int(callback.data.split(":")[2])
    async with get_db_session() as session:
        if not await is_giveaway_admin(session, giveaway_id, callback.from_user.id):
            await callback.answer("Permission denied.", show_alert=True)
            return
        await set_pending_action(session, callback.from_user.id, state="EDIT_TITLE", giveaway_id=giveaway_id)

    await callback.answer()
    await callback.message.answer(
        "✏️ Please enter the new **Title** for this giveaway (2–120 characters):",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("draft:desc:"))
async def cb_draft_desc(callback: CallbackQuery):
    giveaway_id = int(callback.data.split(":")[2])
    async with get_db_session() as session:
        if not await is_giveaway_admin(session, giveaway_id, callback.from_user.id):
            await callback.answer("Permission denied.", show_alert=True)
            return
        await set_pending_action(session, callback.from_user.id, state="EDIT_DESC", giveaway_id=giveaway_id)

    await callback.answer()
    await callback.message.answer(
        "📝 Please enter the **Description** for this giveaway:",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("draft:rules:"))
async def cb_draft_rules(callback: CallbackQuery):
    giveaway_id = int(callback.data.split(":")[2])
    async with get_db_session() as session:
        if not await is_giveaway_admin(session, giveaway_id, callback.from_user.id):
            await callback.answer("Permission denied.", show_alert=True)
            return
        await set_pending_action(session, callback.from_user.id, state="EDIT_RULES", giveaway_id=giveaway_id)

    await callback.answer()
    await callback.message.answer(
        "📜 Please enter the **Rules and Terms** for this giveaway:",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("draft:price:"))
async def cb_draft_price(callback: CallbackQuery):
    giveaway_id = int(callback.data.split(":")[2])
    async with get_db_session() as session:
        if not await is_giveaway_admin(session, giveaway_id, callback.from_user.id):
            await callback.answer("Permission denied.", show_alert=True)
            return
        await set_pending_action(session, callback.from_user.id, state="EDIT_PRICE", giveaway_id=giveaway_id)

    await callback.answer()
    await callback.message.answer(
        "💰 Please enter the **Price Label & Payment Instructions** (e.g. '$10 via USDT-TRC20: Txxx or Free'):",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("draft:mode:"))
async def cb_draft_mode(callback: CallbackQuery):
    giveaway_id = int(callback.data.split(":")[2])
    async with get_db_session() as session:
        giveaway = await session.get(Giveaway, giveaway_id)
        if not giveaway or not await is_giveaway_admin(session, giveaway_id, callback.from_user.id):
            await callback.answer("Permission denied.", show_alert=True)
            return

        giveaway.draw_mode = "number" if giveaway.draw_mode == "random" else "random"
        await session.flush()
        kb = get_draft_menu_keyboard(giveaway)
        await callback.message.edit_reply_markup(reply_markup=kb)
        await callback.answer(f"Draw mode changed to {giveaway.draw_mode.capitalize()}!")


@router.callback_query(F.data.startswith("draft:media:"))
async def cb_draft_media(callback: CallbackQuery):
    giveaway_id = int(callback.data.split(":")[2])
    async with get_db_session() as session:
        if not await is_giveaway_admin(session, giveaway_id, callback.from_user.id):
            await callback.answer("Permission denied.", show_alert=True)
            return
        stmt = select(GiveawayMedia).where(GiveawayMedia.giveaway_id == giveaway_id)
        media_items = (await session.execute(stmt)).scalars().all()
        count = len(media_items)

    kb = get_media_menu_keyboard(giveaway_id, count)
    await callback.message.edit_text(
        f"🖼️ **Media Manager for Giveaway #{giveaway_id}**\n\n"
        f"Currently attached media items: **{count}/10**\n\n"
        "You can attach photos, videos, or documents to be showcased in an album when published.",
        reply_markup=kb,
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("media:upload:"))
async def cb_media_upload(callback: CallbackQuery):
    giveaway_id = int(callback.data.split(":")[2])
    async with get_db_session() as session:
        if not await is_giveaway_admin(session, giveaway_id, callback.from_user.id):
            await callback.answer("Permission denied.", show_alert=True)
            return
        await set_pending_action(session, callback.from_user.id, state="ADD_MEDIA", giveaway_id=giveaway_id)

    await callback.answer()
    await callback.message.answer(
        "📤 Please send a **Photo**, **Video**, or **Document**.\n"
        "You can include a caption with your media file.",
        reply_markup=get_cancel_keyboard(),
    )


@router.callback_query(F.data.startswith("media:clear:"))
async def cb_media_clear(callback: CallbackQuery):
    giveaway_id = int(callback.data.split(":")[2])
    async with get_db_session() as session:
        if not await is_giveaway_admin(session, giveaway_id, callback.from_user.id):
            await callback.answer("Permission denied.", show_alert=True)
            return
        stmt = delete(GiveawayMedia).where(GiveawayMedia.giveaway_id == giveaway_id)
        await session.execute(stmt)

    await callback.answer("All media items deleted.", show_alert=True)
    kb = get_media_menu_keyboard(giveaway_id, 0)
    await callback.message.edit_reply_markup(reply_markup=kb)


@router.callback_query(F.data.startswith("draft:admins:"))
async def cb_draft_admins(callback: CallbackQuery):
    giveaway_id = int(callback.data.split(":")[2])
    async with get_db_session() as session:
        if not await is_giveaway_host(session, giveaway_id, callback.from_user.id):
            await callback.answer("Only the Host can manage admins.", show_alert=True)
            return
        stmt = select(GiveawayAdmin).where(GiveawayAdmin.giveaway_id == giveaway_id)
        admins = (await session.execute(stmt)).scalars().all()

    kb = get_admins_management_keyboard(giveaway_id, admins)
    await callback.message.edit_text(
        f"👥 **Manage Admins for Giveaway #{giveaway_id}**\n\n"
        f"Admins can upload media, edit description/rules, and approve/reject participant entries.\n"
        f"Current admins count: **{len(admins)}**",
        reply_markup=kb,
        parse_mode="Markdown",
    )


@router.callback_query(F.data.startswith("add_admin:"))
async def cb_add_admin(callback: CallbackQuery):
    giveaway_id = int(callback.data.split(":")[1])
    async with get_db_session() as session:
        if not await is_giveaway_host(session, giveaway_id, callback.from_user.id):
            await callback.answer("Only the Host can add admins.", show_alert=True)
            return
        await set_pending_action(session, callback.from_user.id, state="ADD_ADMIN", giveaway_id=giveaway_id)

    await callback.answer()
    await callback.message.answer(
        "👥 Please send the **Telegram User ID** or forward a message from the user you wish to add as admin:",
        reply_markup=get_cancel_keyboard(),
    )


@router.callback_query(F.data.startswith("rm_admin:"))
async def cb_rm_admin(callback: CallbackQuery):
    parts = callback.data.split(":")
    giveaway_id, admin_id = int(parts[1]), int(parts[2])
    async with get_db_session() as session:
        if not await is_giveaway_host(session, giveaway_id, callback.from_user.id):
            await callback.answer("Only the Host can remove admins.", show_alert=True)
            return
        stmt = delete(GiveawayAdmin).where(
            GiveawayAdmin.giveaway_id == giveaway_id,
            GiveawayAdmin.telegram_id == admin_id,
        )
        await session.execute(stmt)
        stmt_admins = select(GiveawayAdmin).where(GiveawayAdmin.giveaway_id == giveaway_id)
        admins = (await session.execute(stmt_admins)).scalars().all()

    await callback.answer(f"Removed admin {admin_id}.", show_alert=True)
    kb = get_admins_management_keyboard(giveaway_id, admins)
    await callback.message.edit_reply_markup(reply_markup=kb)


@router.callback_query(F.data.startswith("draft:preview:"))
async def cb_draft_preview(callback: CallbackQuery):
    giveaway_id = int(callback.data.split(":")[2])
    async with get_db_session() as session:
        giveaway = await session.get(Giveaway, giveaway_id)
        if not giveaway:
            await callback.answer("Giveaway not found.", show_alert=True)
            return

    preview_text = format_giveaway_post(giveaway, preview=True)
    join_kb = get_join_keyboard(giveaway_id)
    await callback.answer()
    for chunk in chunk_text(preview_text):
        await callback.message.answer(chunk, reply_markup=join_kb, parse_mode="Markdown")


@router.callback_query(F.data.startswith("draft:publish:"))
async def cb_draft_publish(callback: CallbackQuery, bot: Bot):
    giveaway_id = int(callback.data.split(":")[2])
    async with get_db_session() as session:
        giveaway = await session.get(Giveaway, giveaway_id)
        if not giveaway:
            await callback.answer("Giveaway not found.", show_alert=True)
            return
        if not await is_giveaway_host(session, giveaway_id, callback.from_user.id):
            await callback.answer("Only the Host can publish.", show_alert=True)
            return

        stmt = select(GiveawayMedia).where(GiveawayMedia.giveaway_id == giveaway_id).order_by(GiveawayMedia.sort_order.asc())
        media_list = (await session.execute(stmt)).scalars().all()

        giveaway.status = "open"
        giveaway.opened_at = datetime.now(timezone.utc)
        await session.flush()

        await log_audit(
            session,
            actor_id=callback.from_user.id,
            action="publish_giveaway",
            giveaway_id=giveaway_id,
        )

    post_text = format_giveaway_post(giveaway, preview=False)
    join_kb = get_join_keyboard(giveaway_id)

    # If media exists, send media group / single media
    if len(media_list) > 1:
        album = []
        for idx, m in enumerate(media_list):
            caption = truncate_caption(post_text) if idx == 0 else m.caption
            if m.kind == "photo":
                album.append(InputMediaPhoto(media=m.file_id, caption=caption, parse_mode="Markdown"))
            elif m.kind == "video":
                album.append(InputMediaVideo(media=m.file_id, caption=caption, parse_mode="Markdown"))
            elif m.kind == "document":
                album.append(InputMediaDocument(media=m.file_id, caption=caption, parse_mode="Markdown"))
        await bot.send_media_group(chat_id=callback.message.chat.id, media=album)
        # Send join button as follow-up message
        await callback.message.answer("👇 Click below to participate in this giveaway:", reply_markup=join_kb)
    elif len(media_list) == 1:
        m = media_list[0]
        cap = truncate_caption(post_text)
        if m.kind == "photo":
            await bot.send_photo(chat_id=callback.message.chat.id, photo=m.file_id, caption=cap, reply_markup=join_kb, parse_mode="Markdown")
        elif m.kind == "video":
            await bot.send_video(chat_id=callback.message.chat.id, video=m.file_id, caption=cap, reply_markup=join_kb, parse_mode="Markdown")
        elif m.kind == "document":
            await bot.send_document(chat_id=callback.message.chat.id, document=m.file_id, caption=cap, reply_markup=join_kb, parse_mode="Markdown")
    else:
        for chunk in chunk_text(post_text):
            await callback.message.answer(chunk, reply_markup=join_kb, parse_mode="Markdown")

    await callback.answer("🚀 Giveaway published successfully!", show_alert=True)


@router.callback_query(F.data.startswith("draft:delete:"))
async def cb_draft_delete(callback: CallbackQuery):
    giveaway_id = int(callback.data.split(":")[2])
    async with get_db_session() as session:
        if not await is_giveaway_host(session, giveaway_id, callback.from_user.id):
            await callback.answer("Only the Host can delete this draft.", show_alert=True)
            return
        stmt = delete(Giveaway).where(Giveaway.id == giveaway_id)
        await session.execute(stmt)

    await callback.answer("Giveaway deleted.", show_alert=True)
    await callback.message.edit_text("🗑️ Giveaway draft was deleted.")


# ==============================================================================
# Host Management Commands (/list, /pending, /open, /lock, /draw, /cancel, /export)
# ==============================================================================

@router.message(Command("open"))
async def cmd_open(message: Message):
    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer("Usage: `/open <giveaway_id>`", parse_mode="Markdown")
        return
    giveaway_id = int(parts[1])
    async with get_db_session() as session:
        if not await is_giveaway_host(session, giveaway_id, message.from_user.id):
            await message.answer("Permission denied: only host can open.")
            return
        giveaway = await session.get(Giveaway, giveaway_id)
        if not giveaway:
            await message.answer("Giveaway not found.")
            return
        giveaway.status = "open"
        giveaway.opened_at = datetime.now(timezone.utc)
        await log_audit(session, actor_id=message.from_user.id, action="open_giveaway", giveaway_id=giveaway_id)

    await message.answer(f"✅ Giveaway #{giveaway_id} is now OPEN for participants!")


@router.message(Command("lock"))
async def cmd_lock(message: Message):
    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer("Usage: `/lock <giveaway_id>`", parse_mode="Markdown")
        return
    giveaway_id = int(parts[1])
    async with get_db_session() as session:
        if not await is_giveaway_host(session, giveaway_id, message.from_user.id):
            await message.answer("Permission denied: only host can lock.")
            return
        giveaway = await session.get(Giveaway, giveaway_id)
        if not giveaway:
            await message.answer("Giveaway not found.")
            return
        giveaway.status = "locked"
        await log_audit(session, actor_id=message.from_user.id, action="lock_giveaway", giveaway_id=giveaway_id)

    await message.answer(f"🔒 Giveaway #{giveaway_id} is now LOCKED. No more entries accepted. Ready for `/draw`!")


@router.message(Command("draw"))
async def cmd_draw(message: Message, bot: Bot):
    """
    /draw <id> [--force] [number]
    """
    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer("Usage: `/draw <giveaway_id> [--force] [winning_number_if_number_mode]`", parse_mode="Markdown")
        return

    giveaway_id = int(parts[1])
    force = "--force" in parts

    chosen_num = None
    for p in parts[2:]:
        if p != "--force" and p.isdigit():
            chosen_num = int(p)
            break

    async with get_db_session() as session:
        winner, msg = await draw_winner(
            session=session,
            giveaway_id=giveaway_id,
            host_id=message.from_user.id,
            force=force,
            chosen_number=chosen_num,
        )

        if not winner:
            await message.answer(f"❌ {msg}")
            return

        giveaway = await session.get(Giveaway, giveaway_id)

    winner_mention = f"@{winner.participant.username}" if winner.participant and winner.participant.username else winner.full_name
    announcement = (
        f"🏆 **GIVEAWAY WINNER ANNOUNCED!** 🏆\n\n"
        f"**Giveaway:** {giveaway.title} (#{giveaway.id})\n"
        f"**Winning Number:** #{winner.number}\n"
        f"**Winner:** {winner.full_name} ({winner_mention})\n\n"
        "Congratulations to the winner! 🎉"
    )
    await message.answer(announcement, parse_mode="Markdown")

    # DM the winner directly
    try:
        dm_text = (
            f"🎉 **YOU WON!** 🎉\n\n"
            f"Congratulations {winner.full_name}, your lucky number **#{winner.number}** won the giveaway:\n"
            f"**{giveaway.title}**!\n\n"
            "The host has been notified and will reach out to fulfill your prize."
        )
        await bot.send_message(chat_id=winner.participant_id, text=dm_text, parse_mode="Markdown")
    except Exception:
        pass


@router.message(Command("cancel"))
async def cmd_cancel_giveaway(message: Message):
    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer("Usage: `/cancel <giveaway_id>`", parse_mode="Markdown")
        return
    giveaway_id = int(parts[1])
    async with get_db_session() as session:
        if not await is_giveaway_host(session, giveaway_id, message.from_user.id):
            await message.answer("Permission denied: only host can cancel.")
            return
        giveaway = await session.get(Giveaway, giveaway_id)
        if not giveaway:
            await message.answer("Giveaway not found.")
            return
        giveaway.status = "cancelled"
        await log_audit(session, actor_id=message.from_user.id, action="cancel_giveaway", giveaway_id=giveaway_id)

    await message.answer(f"🚫 Giveaway #{giveaway_id} has been CANCELLED.")


@router.message(Command("export"))
async def cmd_export(message: Message):
    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.answer("Usage: `/export <giveaway_id>`", parse_mode="Markdown")
        return
    giveaway_id = int(parts[1])
    async with get_db_session() as session:
        if not await is_giveaway_admin(session, giveaway_id, message.from_user.id):
            await message.answer("Permission denied.")
            return
        csv_data = await export_giveaway_csv(session, giveaway_id)

    file_bytes = csv_data.encode("utf-8")
    doc = BufferedInputFile(file_bytes, filename=f"giveaway_{giveaway_id}_roster.csv")
    await message.answer_document(doc, caption=f"📊 Participant Roster for Giveaway #{giveaway_id}")


@router.message(Command("list"))
async def cmd_list(message: Message):
    parts = message.text.strip().split()
    giveaway_id = int(parts[1]) if len(parts) > 1 else None

    async with get_db_session() as session:
        if not giveaway_id:
            # Show active giveaways hosted by user
            stmt = select(Giveaway).where(Giveaway.host_id == message.from_user.id).order_by(Giveaway.id.desc()).limit(10)
            giveaways = (await session.execute(stmt)).scalars().all()
            if not giveaways:
                await message.answer("You don't have any giveaways yet. Use `/new` to create one!", parse_mode="Markdown")
                return
            lines = ["📋 **Your Giveaways:**\n"]
            for g in giveaways:
                lines.append(f"• `#{g.id}` - **{g.title}** ({g.status.upper()})")
            lines.append("\nView entries for a specific giveaway with `/list <id>`")
            await message.answer("\n".join(lines), parse_mode="Markdown")
            return

        stmt = (
            select(Entry)
            .where(Entry.giveaway_id == giveaway_id, Entry.status == "approved")
            .options(selectinload(Entry.participant))
            .order_by(Entry.number.asc())
        )
        entries = (await session.execute(stmt)).scalars().all()

    if not entries:
        await message.answer(f"No approved entries found for Giveaway #{giveaway_id}.")
        return

    lines = [f"📋 **Approved Participants for Giveaway #{giveaway_id}** ({len(entries)}/100):\n"]
    for e in entries:
        user_handle = f"@{e.participant.username}" if e.participant and e.participant.username else "NoUsername"
        num_str = f"#{e.number}" if e.number else "No number"
        lines.append(f"• **{num_str}**: {e.full_name} ({user_handle})")

    for chunk in chunk_text("\n".join(lines)):
        await message.answer(chunk, parse_mode="Markdown")


@router.message(Command("pending"))
async def cmd_pending(message: Message):
    parts = message.text.strip().split()
    giveaway_id = int(parts[1]) if len(parts) > 1 else None

    async with get_db_session() as session:
        query = select(Entry).where(Entry.status == "awaiting_approval").options(selectinload(Entry.participant), selectinload(Entry.giveaway))
        if giveaway_id:
            query = query.where(Entry.giveaway_id == giveaway_id)
        entries = (await session.execute(query)).scalars().all()

    if not entries:
        await message.answer("🎉 No entries currently awaiting approval.")
        return

    await message.answer(f"📬 **{len(entries)} entries awaiting approval:**", parse_mode="Markdown")
    for e in entries[:10]:
        uname = f"@{e.participant.username}" if e.participant and e.participant.username else "N/A"
        txt = (
            f"👤 **Participant:** {e.full_name} ({uname})\n"
            f"🎁 **Giveaway:** {e.giveaway.title} (#{e.giveaway_id})\n"
            f"💳 **Payment Note:** {e.payment_note or 'None'}\n"
        )
        kb = get_admin_approval_keyboard(e.id)
        if e.proof_file_id:
            try:
                await message.answer_photo(photo=e.proof_file_id, caption=txt, reply_markup=kb, parse_mode="Markdown")
                continue
            except Exception:
                pass
        await message.answer(txt, reply_markup=kb, parse_mode="Markdown")


# ==============================================================================
# Approve & Reject Callbacks
# ==============================================================================

@router.callback_query(F.data.startswith("appr:"))
async def cb_approve_entry(callback: CallbackQuery, bot: Bot):
    entry_id = int(callback.data.split(":")[1])
    async with get_db_session() as session:
        entry = await session.get(Entry, entry_id)
        if not entry:
            await callback.answer("Entry not found.", show_alert=True)
            return

        if not await is_giveaway_admin(session, entry.giveaway_id, callback.from_user.id):
            await callback.answer("Permission denied: admin only.", show_alert=True)
            return

        if entry.status == "approved":
            await callback.answer("Entry is already approved.", show_alert=True)
            return

        entry.status = "approved"
        entry.approved_by = callback.from_user.id
        entry.approved_at = datetime.now(timezone.utc)
        await session.flush()

        giveaway = await session.get(Giveaway, entry.giveaway_id)
        taken_numbers = await get_taken_numbers(session, entry.giveaway_id)

        # Set participant pending action to pick number
        await set_pending_action(
            session,
            telegram_id=entry.participant_id,
            state="PICKING_NUMBER",
            giveaway_id=entry.giveaway_id,
            entry_id=entry.id,
        )

        await log_audit(
            session,
            actor_id=callback.from_user.id,
            action="approve_entry",
            giveaway_id=entry.giveaway_id,
            meta={"entry_id": entry.id, "participant_id": entry.participant_id},
        )

    await callback.answer("✅ Entry approved!")
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(f"✅ Approved entry #{entry_id} for {entry.full_name}.")

    # DM Participant the 10x10 Number Grid
    try:
        grid_kb = build_number_grid(giveaway.id, taken_numbers)
        dm_text = (
            f"🎉 **Congratulations {entry.full_name}!**\n\n"
            f"Your entry for **{giveaway.title}** has been **APPROVED**! 🥳\n\n"
            "Now pick your lucky number (1–100) from the grid below.\n"
            "Numbers marked with `✓` are already taken. Tap any available number to claim it immediately:"
        )
        await bot.send_message(chat_id=entry.participant_id, text=dm_text, reply_markup=grid_kb, parse_mode="Markdown")
    except Exception as e:
        await callback.message.answer(f"⚠️ Could not DM participant (Telegram error: {e}).")


@router.callback_query(F.data.startswith("rej:"))
async def cb_reject_entry(callback: CallbackQuery):
    entry_id = int(callback.data.split(":")[1])
    async with get_db_session() as session:
        entry = await session.get(Entry, entry_id)
        if not entry:
            await callback.answer("Entry not found.", show_alert=True)
            return

        if not await is_giveaway_admin(session, entry.giveaway_id, callback.from_user.id):
            await callback.answer("Permission denied: admin only.", show_alert=True)
            return

        # Prompt admin for reject reason
        await set_pending_action(
            session,
            telegram_id=callback.from_user.id,
            state="REJECT_REASON",
            giveaway_id=entry.giveaway_id,
            entry_id=entry.id,
        )

    await callback.answer()
    await callback.message.answer(
        f"❌ Please provide a rejection reason for **{entry.full_name}**:",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown",
    )
