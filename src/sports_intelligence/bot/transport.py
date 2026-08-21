from __future__ import annotations

from typing import Protocol

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup


class TelegramTransport(Protocol):
    """Minimal outbound transport used by handlers.

    Handlers only ever call these three methods, so updates can be
    tested deterministically with an in-memory fake and no Telegram
    token or network.
    """

    async def send_text(
        self,
        chat_id: int,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None: ...

    async def edit_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None: ...

    async def answer_callback(self, callback_query_id: str) -> None: ...


class AiogramTransport:
    """Real transport backed by an aiogram Bot instance."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send_text(
        self,
        chat_id: int,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        await self._bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)

    async def edit_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        await self._bot.edit_message_text(
            text=text, chat_id=chat_id, message_id=message_id, reply_markup=reply_markup
        )

    async def answer_callback(self, callback_query_id: str) -> None:
        await self._bot.answer_callback_query(callback_query_id=callback_query_id)
