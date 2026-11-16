import asyncio
import logging
from typing import Optional
from fastapi import FastAPI, Request, Header, HTTPException, status
from fastapi.responses import JSONResponse, PlainTextResponse
from aiogram.types import Update
from sqlalchemy import select

from app.config import settings
from app.logging_config import setup_logging
from app.database import ping_database, get_db_session
from app.models.models import ProcessedUpdate
from app.bot.instance import bot, dp
from app.web.lifespan import lifespan, active_background_tasks

# Configure structured logging
setup_logging(settings.LOG_LEVEL)
logger = logging.getLogger("app.web.app")

app = FastAPI(
    title="Ultra Giveaway Bot API",
    version="1.0.0",
    lifespan=lifespan,
)


async def process_update_safe(update_data: dict) -> None:
    """
    Background worker that handles update processing:
    1. Idempotency check using processed_updates table.
    2. Feeds update to aiogram dispatcher.
    """
    update_id = update_data.get("update_id")
    try:
        if update_id is not None:
            async with get_db_session() as session:
                stmt = select(ProcessedUpdate.update_id).where(ProcessedUpdate.update_id == update_id)
                existing = (await session.execute(stmt)).scalar_one_or_none()
                if existing:
                    logger.info(f"Duplicate update_id {update_id} skipped.")
                    return

                session.add(ProcessedUpdate(update_id=update_id))
                await session.flush()

        aiogram_update = Update.model_validate(update_data, context={"bot": bot})
        await dp.feed_update(bot=bot, update=aiogram_update)
    except Exception as e:
        logger.error(f"Error processing background update {update_id}: {e}", exc_info=True)


@app.get("/healthz")
async def healthz():
    """Liveness & readiness probe: checks DB connectivity without auth."""
    db_ok = await ping_database()
    if not db_ok:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "degraded", "database": "disconnected"},
        )
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "ok", "database": "connected"},
    )


@app.post(settings.WEBHOOK_PATH)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(None),
):
    """
    Telegram webhook receiver.
    Verifies secret_token, schedules background task, and returns 200 OK within 100ms.
    """
    if settings.WEBHOOK_SECRET and x_telegram_bot_api_secret_token:
        received = x_telegram_bot_api_secret_token.strip()
        expected = settings.WEBHOOK_SECRET.strip()
        if received != expected:
            logger.warning(
                f"Rejected webhook call: secret token mismatch. Expected {expected[:4]}..., received {received[:4]}..."
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Invalid webhook secret token",
            )

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    # Offload heavy update processing to background task to guarantee < 100ms response
    task = asyncio.create_task(process_update_safe(data))
    active_background_tasks.add(task)
    task.add_done_callback(active_background_tasks.discard)

    return PlainTextResponse(content="OK", status_code=status.HTTP_200_OK)
