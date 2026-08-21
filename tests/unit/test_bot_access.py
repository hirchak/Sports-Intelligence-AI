from __future__ import annotations

from typing import Any

from sports_intelligence.bot.access import AllowlistMiddleware
from sports_intelligence.bot.context import AppContext
from sports_intelligence.core.config import Settings
from telegram_fakes import FakeTransport, make_callback, make_message


def _settings(allowed: list[int]) -> Settings:
    return Settings(
        _env_file=None,
        app_env="mock",
        telegram_allowed_user_ids=allowed,
        telegram_bot_token="test-token",
    )


def _context(transport: FakeTransport, allowed: list[int]) -> AppContext:
    return AppContext(
        transport=transport,  # type: ignore[arg-type]
        backend=object(),  # type: ignore[arg-type]
        settings=_settings(allowed),
        allowed_user_ids=frozenset(allowed),
    )


async def test_allowed_message_reaches_handler_with_context() -> None:
    transport = FakeTransport()
    context = _context(transport, [1])
    middleware = AllowlistMiddleware(context)
    seen: list[Any] = []

    async def handler(event: Any, data: dict[str, Any]) -> str:
        seen.append(data["context"])
        return "handled"

    event = make_message("hi", user_id=1)
    result = await middleware(handler, event, {"bot": object()})
    assert result == "handled"
    assert seen == [context]
    assert transport.sent == []


async def test_unknown_message_user_is_denied_without_details() -> None:
    transport = FakeTransport()
    middleware = AllowlistMiddleware(_context(transport, [1]))
    called = False

    async def handler(event: Any, data: dict[str, Any]) -> str:
        nonlocal called
        called = True
        return "handled"

    event = make_message("hi", user_id=999)
    result = await middleware(handler, event, {"bot": object()})
    assert result is None
    assert called is False
    assert len(transport.sent) == 1
    assert transport.sent[0]["text"] == "Доступ запрещён."
    assert transport.sent[0]["chat_id"] == 11


async def test_unknown_callback_user_gets_silent_answer() -> None:
    transport = FakeTransport()
    middleware = AllowlistMiddleware(_context(transport, [1]))
    called = False

    async def handler(event: Any, data: dict[str, Any]) -> str:
        nonlocal called
        called = True
        return "handled"

    event = make_callback("fx:test", user_id=999)
    result = await middleware(handler, event, {"bot": object()})
    assert result is None
    assert called is False
    assert transport.sent == []
    assert transport.answered == [{"callback_query_id": "cb-test-1"}]


async def test_event_without_user_is_denied() -> None:
    transport = FakeTransport()
    middleware = AllowlistMiddleware(_context(transport, [1]))
    called = False

    async def handler(event: Any, data: dict[str, Any]) -> str:
        nonlocal called
        called = True
        return "handled"

    event = make_message("hi", user_id=1, from_user=None)
    result = await middleware(handler, event, {"bot": object()})
    assert result is None
    assert called is False
    assert transport.sent[0]["text"] == "Доступ запрещён."


async def test_empty_allowlist_denies_everyone() -> None:
    transport = FakeTransport()
    middleware = AllowlistMiddleware(_context(transport, []))
    called = False

    async def handler(event: Any, data: dict[str, Any]) -> str:
        nonlocal called
        called = True
        return "handled"

    event = make_message("hi", user_id=1)
    result = await middleware(handler, event, {"bot": object()})
    assert result is None
    assert called is False
    assert transport.sent[0]["text"] == "Доступ запрещён."
