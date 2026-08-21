from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from sports_intelligence.bot.access import AllowlistMiddleware
from sports_intelligence.bot.backend_client import BackendClient
from sports_intelligence.bot.context import AppContext
from sports_intelligence.bot.handlers import router
from sports_intelligence.bot.transport import AiogramTransport
from sports_intelligence.core.config import Settings


def build_application(settings: Settings, backend: BackendClient) -> tuple[Bot, Dispatcher]:
    """Build the aiogram Bot + Dispatcher with central access control.

    The Telegram layer is a thin UI: handlers only receive an AppContext
    with the transport and the typed backend client; no provider, DB or
    LLM access exists here.
    """
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    context = AppContext(
        transport=AiogramTransport(bot),
        backend=backend,
        settings=settings,
        allowed_user_ids=frozenset(settings.telegram_allowed_user_ids),
    )
    middleware = AllowlistMiddleware(context)
    router.message.middleware(middleware)
    router.callback_query.middleware(middleware)
    dispatcher.include_router(router)
    return bot, dispatcher
