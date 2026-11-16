from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from app.config import settings
from app.bot.middlewares.user_sync import UserSyncMiddleware
from app.bot.middlewares.rate_limit import RateLimitMiddleware
from app.bot.middlewares.error_handler import GlobalErrorMiddleware
from app.bot.handlers import common, host, participant, actions

bot = Bot(
    token=settings.BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=None),
)

dp = Dispatcher()

# Register Global Middlewares
dp.update.outer_middleware(RateLimitMiddleware())
dp.update.outer_middleware(UserSyncMiddleware())
dp.message.middleware(GlobalErrorMiddleware())
dp.callback_query.middleware(GlobalErrorMiddleware())

# Register Routers in precedence order
dp.include_router(common.router)
dp.include_router(host.router)
dp.include_router(participant.router)
dp.include_router(actions.router)
