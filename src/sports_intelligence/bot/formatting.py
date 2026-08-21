from __future__ import annotations

import math
from datetime import date, datetime
from html import escape
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sports_intelligence.bot.backend_client import DiscoverResult, FixtureView, HealthStatus
from sports_intelligence.bot.callback_data import (
    fixture_callback,
    page_callback,
    refresh_callback,
)
from sports_intelligence.bot.strings import (
    BACK_LABEL,
    NEXT_LABEL,
    OK_LABEL,
    PREV_LABEL,
    REFRESH_LABEL,
    RU_MONTHS,
    UNAVAILABLE_LABEL,
    UNKNOWN_LABEL,
    no_fixtures_for,
)
from sports_intelligence.core.time import local_today, utc_now

PAGE_SIZE = 8
MISSING_TEAM = "—"
MAX_BUTTON_TEXT = 40


def display_name(value: str | None) -> str:
    if not value:
        return MISSING_TEAM
    return escape(value)


def plain_name(value: str | None) -> str:
    if not value:
        return MISSING_TEAM
    if len(value) > MAX_BUTTON_TEXT:
        return value[: MAX_BUTTON_TEXT - 1] + "…"
    return value


def kickoff_time_local(kickoff_at: datetime, timezone_name: str) -> str:
    zone = ZoneInfo(timezone_name)
    return kickoff_at.astimezone(zone).strftime("%H:%M")


def kickoff_label_local(kickoff_at: datetime, timezone_name: str) -> str:
    zone = ZoneInfo(timezone_name)
    local = kickoff_at.astimezone(zone)
    return f"{local.day:02d} {RU_MONTHS[local.month - 1]} {local:%H:%M} {timezone_name}"


def group_by_league(fixtures: list[FixtureView]) -> list[tuple[str, list[FixtureView]]]:
    groups: dict[str, list[FixtureView]] = {}
    for fixture in fixtures:
        groups.setdefault(fixture.league_slug, []).append(fixture)
    return list(groups.items())


def paginate(fixtures: list[FixtureView], page: int) -> tuple[list[FixtureView], int, int]:
    total_pages = math.ceil(len(fixtures) / PAGE_SIZE) if fixtures else 1
    clamped = max(0, min(page, total_pages - 1))
    start = clamped * PAGE_SIZE
    return fixtures[start : start + PAGE_SIZE], clamped, total_pages


def build_fixture_page(
    fixtures: list[FixtureView],
    page: int,
    fixture_date: date,
    timezone_name: str,
) -> tuple[str, InlineKeyboardMarkup | None]:
    ordered = sorted(fixtures, key=lambda fixture: fixture.kickoff_at)
    if not ordered:
        return no_fixtures_for(fixture_date.isoformat()), None
    page_fixtures, clamped_page, total_pages = paginate(ordered, page)
    groups = group_by_league(page_fixtures)
    lines = [f"<b>{escape(fixture_date.isoformat())}</b>"]
    for slug, league_fixtures in groups:
        lines.append("")
        lines.append(f"<b>{escape(slug)}</b>")
        for fixture in league_fixtures:
            time = kickoff_time_local(fixture.kickoff_at, timezone_name)
            lines.append(
                f"{time} {display_name(fixture.home_team)} — {display_name(fixture.away_team)}"
            )
    if total_pages > 1:
        lines.append("")
        lines.append(f"Стр. {clamped_page + 1}/{total_pages}")
    return "\n".join(lines), fixtures_keyboard(
        page_fixtures, clamped_page, total_pages, fixture_date, timezone_name
    )


def fixtures_keyboard(
    page_fixtures: list[FixtureView],
    page: int,
    total_pages: int,
    fixture_date: date,
    timezone_name: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for fixture in page_fixtures:
        label = (
            f"{kickoff_time_local(fixture.kickoff_at, timezone_name)} "
            f"{plain_name(fixture.home_team)} — {plain_name(fixture.away_team)}"
        )
        builder.button(text=label, callback_data=fixture_callback(fixture.id))
    builder.adjust(1)
    navigation: list[InlineKeyboardButton] = []
    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                text=PREV_LABEL, callback_data=page_callback(fixture_date, page - 1)
            )
        )
    if page + 1 < total_pages:
        navigation.append(
            InlineKeyboardButton(
                text=NEXT_LABEL, callback_data=page_callback(fixture_date, page + 1)
            )
        )
    navigation.append(
        InlineKeyboardButton(text=REFRESH_LABEL, callback_data=refresh_callback(fixture_date))
    )
    builder.row(*navigation)
    builder.row(InlineKeyboardButton(text=BACK_LABEL, callback_data="menu:main"))
    return builder.as_markup()


def render_fixture_detail(fixture: FixtureView, timezone_name: str) -> str:
    lines = [
        f"<b>{display_name(fixture.home_team)} — {display_name(fixture.away_team)}</b>",
        f"Лига: {escape(fixture.league_slug)}",
        f"Начало: {kickoff_label_local(fixture.kickoff_at, timezone_name)}",
    ]
    if fixture.venue:
        lines.append(f"Место: {escape(fixture.venue)}")
    if fixture.round:
        lines.append(f"Тур: {escape(fixture.round)}")
    lines.append(f"Статус: {escape(fixture.status)}")
    return "\n".join(lines)


def render_dashboard(fixtures: list[FixtureView], health: HealthStatus, timezone_name: str) -> str:
    today = local_today(utc_now(), timezone_name)
    leagues = _distinct_leagues(fixtures)
    leagues_text = ", ".join(escape(slug) for slug in leagues[:5])
    if len(leagues) > 5:
        leagues_text += "…"
    if not leagues_text:
        leagues_text = MISSING_TEAM
    backend_text = "исправен" if health.api else "недоступен"
    return "\n".join(
        [
            "<b>Sports Intelligence</b>",
            "",
            f"Дата: {today.isoformat()}",
            f"Сегодня: {len(fixtures)} матчей",
            f"Лиги: {leagues_text}",
            f"Бэкенд: {backend_text}",
        ]
    )


def render_health(health: HealthStatus) -> str:
    return "\n".join(
        [
            f"API: {_ok_label(health.api)}",
            f"Database: {_ok_label(health.database)}",
            f"Redis: {_ok_label(health.redis)}",
        ]
    )


def render_discover(result: DiscoverResult) -> str:
    queued_text = "да (дубликатов не создано)" if result.already_queued else "нет"
    return "\n".join(
        [
            "<b>Задача сбора</b>",
            f"Job: <code>{result.job_id}</code>",
            f"Статус: {escape(result.status)}",
            f"Уже в очереди: {queued_text}",
        ]
    )


def _distinct_leagues(fixtures: list[FixtureView]) -> list[str]:
    leagues: list[str] = []
    for fixture in fixtures:
        if fixture.league_slug not in leagues:
            leagues.append(fixture.league_slug)
    return leagues


def _ok_label(value: bool | None) -> str:
    if value is None:
        return UNKNOWN_LABEL
    return OK_LABEL if value else UNAVAILABLE_LABEL
