from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from sports_intelligence.bot.context import AppContext
from sports_intelligence.bot.strings import ACCESS_DENIED
from sports_intelligence.core.logging import get_logger

logger = get_logger(__name__)


class AllowlistMiddleware(BaseMiddleware):
    """Central access control.

    Only allowlisted Telegram user IDs reach any handler. Unknown users
    receive a minimal denial (message) or a silent answer (callback) —
    no system details are exposed. The middleware is registered once for
    both messages and callback queries, so no handler duplicates the
    check.
    """

    def __init__(self, context: AppContext) -> None:
        self._context = context

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = getattr(getattr(event, "from_user", None), "id", None)
        if user_id is None or user_id not in self._context.allowed_user_ids:
            logger.warning("telegram access denied", extra={"user_id": user_id})
            await self._deny(event)
            return None
        data["context"] = self._context
        return await handler(event, data)

    async def _deny(self, event: TelegramObject) -> None:
        try:
            if isinstance(event, Message):
                await self._context.transport.send_text(event.chat.id, ACCESS_DENIED)
            elif isinstance(event, CallbackQuery):
                await self._context.transport.answer_callback(event.id)
        except Exception:
            logger.warning("failed to send access denial", exc_info=True)
