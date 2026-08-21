from __future__ import annotations

import asyncio
from contextlib import suppress

from sports_intelligence.bot.app import build_application
from sports_intelligence.bot.backend_client import BackendClient
from sports_intelligence.core.config import get_settings
from sports_intelligence.core.logging import get_logger, setup_logging

logger = get_logger(__name__)


async def run() -> None:
    settings = get_settings()
    setup_logging(level=settings.log_level)
    if not settings.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN is not configured; refusing to start")
        raise SystemExit(1)
    if not settings.telegram_allowed_user_ids:
        logger.warning("TELEGRAM_ALLOWED_USER_IDS is empty; every user will be denied")
    async with BackendClient(settings.bot_backend_base_url) as backend:
        bot, dispatcher = build_application(settings, backend)
        logger.info("telegram bot starting (long polling)")
        try:
            await dispatcher.start_polling(bot)
        finally:
            await bot.session.close()


def main() -> None:
    with suppress(KeyboardInterrupt, SystemExit):
        asyncio.run(run())


if __name__ == "__main__":
    main()
