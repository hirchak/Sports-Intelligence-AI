from __future__ import annotations

import uuid
from datetime import date

from sports_intelligence.bot.callback_data import (
    DISCOVER_CALLBACK,
    HEALTH_CALLBACK,
    MENU_FIND,
    MENU_HEALTH,
    MENU_HELP,
    MENU_MAIN,
    MENU_TODAY,
    fixture_callback,
    page_callback,
    parse_fixture_callback,
    parse_page_callback,
    parse_refresh_callback,
    refresh_callback,
)

FIXTURE_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")


def test_fixture_callback_roundtrip() -> None:
    data = fixture_callback(FIXTURE_ID)
    assert data == f"fx:{FIXTURE_ID}"
    assert parse_fixture_callback(data) == FIXTURE_ID


def test_page_callback_roundtrip() -> None:
    data = page_callback(date(2026, 8, 21), 3)
    assert data == "pg:2026-08-21:3"
    assert parse_page_callback(data) == (date(2026, 8, 21), 3)


def test_refresh_callback_roundtrip() -> None:
    data = refresh_callback(date(2026, 8, 21))
    assert data == "rf:2026-08-21"
    assert parse_refresh_callback(data) == date(2026, 8, 21)


def test_malformed_callbacks_return_none() -> None:
    assert parse_fixture_callback("pg:2026-08-21:0") is None
    assert parse_fixture_callback("fx:not-a-uuid") is None
    assert parse_fixture_callback("") is None
    assert parse_page_callback("pg:not-a-date:0") is None
    assert parse_page_callback("pg:2026-08-21") is None
    assert parse_page_callback("pg:2026-08-21:not-an-int") is None
    assert parse_refresh_callback("rf:bad-date") is None


def test_callback_payloads_stay_short_and_secret_free() -> None:
    payloads = [
        fixture_callback(FIXTURE_ID),
        page_callback(date(2026, 8, 21), 999),
        refresh_callback(date(2026, 8, 21)),
        DISCOVER_CALLBACK,
        HEALTH_CALLBACK,
        MENU_MAIN,
        MENU_TODAY,
        MENU_FIND,
        MENU_HEALTH,
        MENU_HELP,
    ]
    for payload in payloads:
        assert len(payload.encode("utf-8")) <= 64
        assert "{" not in payload
        assert "token" not in payload.lower()
        assert "password" not in payload.lower()
