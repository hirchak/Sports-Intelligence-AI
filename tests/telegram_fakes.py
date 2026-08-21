from __future__ import annotations

from typing import Any

from aiogram.types import CallbackQuery, Chat, InlineKeyboardMarkup, Message, User


class FakeTransport:
    """In-memory TelegramTransport stand-in for deterministic handler tests."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.edited: list[dict[str, Any]] = []
        self.answered: list[dict[str, Any]] = []

    async def send_text(
        self,
        chat_id: int,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        self.sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})

    async def edit_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        self.edited.append(
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "reply_markup": reply_markup,
            }
        )

    async def answer_callback(self, callback_query_id: str) -> None:
        self.answered.append({"callback_query_id": callback_query_id})


_MISSING = object()


def make_message(
    text: str,
    user_id: int = 1,
    chat_id: int = 11,
    from_user: User | None | object = _MISSING,
) -> Message:
    return Message.model_construct(
        message_id=1,
        chat=Chat.model_construct(id=chat_id, type="private"),
        from_user=(
            from_user
            if from_user is not _MISSING
            else User.model_construct(id=user_id, is_bot=False, first_name="Tester")
        ),
        text=text,
    )


def make_callback(data: str, user_id: int = 1, chat_id: int = 11) -> CallbackQuery:
    return CallbackQuery.model_construct(
        id="cb-test-1",
        from_user=User.model_construct(id=user_id, is_bot=False, first_name="Tester"),
        message=make_message("placeholder", user_id=user_id, chat_id=chat_id),
        chat_instance="ci-test-1",
        data=data,
    )
