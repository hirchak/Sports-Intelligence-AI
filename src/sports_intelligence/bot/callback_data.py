from __future__ import annotations

from datetime import date
from uuid import UUID

# Short, stable, secret-free callback payloads (well below Telegram's
# 64-byte limit). Details are always resolved server-side.

FIXTURE_PREFIX = "fx:"
PAGE_PREFIX = "pg:"
REFRESH_PREFIX = "rf:"
DISCOVER_CALLBACK = "disc"
HEALTH_CALLBACK = "health"
MENU_PREFIX = "menu:"
MENU_MAIN = "menu:main"
MENU_TODAY = "menu:today"
MENU_FIND = "menu:find"
MENU_HEALTH = "menu:health"
MENU_HELP = "menu:help"


def fixture_callback(fixture_id: UUID) -> str:
    return f"{FIXTURE_PREFIX}{fixture_id}"


def page_callback(fixture_date: date, page: int) -> str:
    return f"{PAGE_PREFIX}{fixture_date.isoformat()}:{page}"


def refresh_callback(fixture_date: date) -> str:
    return f"{REFRESH_PREFIX}{fixture_date.isoformat()}"


def parse_fixture_callback(data: str) -> UUID | None:
    if not data.startswith(FIXTURE_PREFIX):
        return None
    try:
        return UUID(data[len(FIXTURE_PREFIX) :])
    except ValueError:
        return None


def parse_page_callback(data: str) -> tuple[date, int] | None:
    if not data.startswith(PAGE_PREFIX):
        return None
    parts = data.split(":")
    if len(parts) != 3:
        return None
    try:
        return date.fromisoformat(parts[1]), int(parts[2])
    except ValueError:
        return None


def parse_refresh_callback(data: str) -> date | None:
    if not data.startswith(REFRESH_PREFIX):
        return None
    try:
        return date.fromisoformat(data[len(REFRESH_PREFIX) :])
    except ValueError:
        return None
