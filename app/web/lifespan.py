import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI
from sqlalchemy import delete

from app.config import settings
from app.database import dispose_database, get_db_session
from app.models.models import ProcessedUpdate
from app.bot.instance import bot

logger = logging.getLogger("app.web.lifespan")

# Global set to track in-flight background update processing tasks
active_background_tasks = set()
cleanup_task = None


async def periodic_update_cleanup():
    """Periodically purges processed_updates older than 24 hours."""
    while True:
        try:
            await asyncio.sleep(3600)  # Every hour
            cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
            async with get_db_session() as session:
                stmt = delete(ProcessedUpdate).where(ProcessedUpdate.created_at < cutoff)
                await session.execute(stmt)
            logger.info("Processed updates cleanup executed successfully.")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"Error during periodic update cleanup: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global cleanup_task
    logger.info("Initializing Ultra Giveaway Bot webhook server...")

    # Always set Telegram Webhook on startup to ensure secret_token and URL are 100% in sync
    try:
        await bot.set_webhook(
            url=settings.full_webhook_url,
            secret_token=settings.WEBHOOK_SECRET,
            allowed_updates=["message", "callback_query", "chat_member"],
            drop_pending_updates=False,
        )
        logger.info(f"Webhook set successfully to {settings.full_webhook_url}")
    except Exception as e:
        logger.error(f"Failed to set Telegram webhook on startup: {e}")

    # Start periodic cleanup task
    cleanup_task = asyncio.create_task(periodic_update_cleanup())

    yield

    logger.info("Shutting down... finishing in-flight tasks and disposing resources.")

    # Cancel cleanup task
    if cleanup_task:
        cleanup_task.cancel()

    # Wait for all in-flight background tasks with timeout
    if active_background_tasks:
        logger.info(f"Waiting for {len(active_background_tasks)} active background tasks to finish...")
        done, pending = await asyncio.wait(active_background_tasks, timeout=5.0)
        for t in pending:
            t.cancel()

    # Close Telegram bot session and DB pool
    try:
        await bot.session.close()
    except Exception:
        pass

    try:
        await dispose_database()
    except Exception:
        pass

    logger.info("Shutdown complete.")
