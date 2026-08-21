from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sports_intelligence.bot.backend_client import DiscoverResult, FixtureView, HealthStatus
from sports_intelligence.bot.formatting import (
    PAGE_SIZE,
    build_fixture_page,
    display_name,
    group_by_league,
    kickoff_time_local,
    paginate,
    plain_name,
    render_dashboard,
    render_discover,
    render_fixture_detail,
    render_health,
)

TIMEZONE = "Europe/Warsaw"


def _fixture(
    fixture_id: str,
    league: str,
    kickoff: str,
    home: str | None = "Команда A",
    away: str | None = "Команда B",
    venue: str | None = None,
    round_name: str | None = None,
) -> FixtureView:
    return FixtureView(
        id=uuid.UUID(fixture_id),
        league_slug=league,
        home_team=home,
        away_team=away,
        kickoff_at=datetime.fromisoformat(kickoff),
        venue=venue,
        round=round_name,
        status="NS",
    )


def test_display_name_nullable_and_escaped() -> None:
    assert display_name(None) == "—"
    assert display_name("") == "—"
    assert display_name("Команда <X> & Y") == "Команда &lt;X&gt; &amp; Y"


def test_plain_name_truncates_long_labels() -> None:
    assert plain_name(None) == "—"
    long_name = "A" * 60
    shortened = plain_name(long_name)
    assert len(shortened) <= 40
    assert shortened.endswith("…")


def test_kickoff_time_uses_local_timezone() -> None:
    kickoff = datetime(2026, 8, 21, 18, 30, tzinfo=UTC)
    assert kickoff_time_local(kickoff, "Europe/Warsaw") == "20:30"
    assert kickoff_time_local(kickoff, "Europe/London") == "19:30"


def test_kickoff_label_uses_russian_month_abbreviation() -> None:
    kickoff = datetime(2026, 8, 21, 18, 30, tzinfo=UTC)
    label = format_module_kickoff_label(kickoff)
    assert "авг." in label
    assert "20:30" in label
    assert "Europe/Warsaw" in label


def format_module_kickoff_label(kickoff: datetime) -> str:
    from sports_intelligence.bot.formatting import kickoff_label_local

    return kickoff_label_local(kickoff, TIMEZONE)


def test_group_by_league_preserves_first_kickoff_order() -> None:
    fixtures = [
        _fixture("00000000-0000-0000-0000-000000000001", "la-liga", "2026-08-21T20:00:00Z"),
        _fixture("00000000-0000-0000-0000-000000000002", "premier-league", "2026-08-21T17:00:00Z"),
        _fixture("00000000-0000-0000-0000-000000000003", "la-liga", "2026-08-21T19:00:00Z"),
    ]
    groups = group_by_league(fixtures)
    assert [slug for slug, _ in groups] == ["la-liga", "premier-league"]


def test_paginate_clamps_page_and_counts_pages() -> None:
    fixtures = [
        _fixture(f"00000000-0000-0000-0000-{i:012d}", "l", "2026-08-21T17:00:00Z")
        for i in range(PAGE_SIZE * 2 + 3)
    ]
    page_fixtures, page, total = paginate(fixtures, 0)
    assert len(page_fixtures) == PAGE_SIZE
    assert (page, total) == (0, 3)

    last_fixtures, page, total = paginate(fixtures, 99)
    assert len(last_fixtures) == 3
    assert page == 2


def test_build_fixture_page_groups_and_escapes() -> None:
    fixtures = [
        _fixture("00000000-0000-0000-0000-000000000001", "premier-league", "2026-08-21T18:30:00Z"),
        _fixture(
            "00000000-0000-0000-0000-000000000002",
            "premier-league",
            "2026-08-21T21:00:00Z",
            home=None,
        ),
        _fixture(
            "00000000-0000-0000-0000-000000000003",
            "la-liga",
            "2026-08-21T19:00:00Z",
            home="Team <X>",
        ),
    ]
    text, keyboard = build_fixture_page(fixtures, 0, date(2026, 8, 21), TIMEZONE)
    assert "premier-league" in text
    assert "la-liga" in text
    assert "20:30 Команда A — Команда B" in text
    assert "23:00 — — Команда B" in text
    assert "Team &lt;X&gt;" in text
    assert "Page " not in text
    assert "Стр." not in text
    assert keyboard is not None
    button_data = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert "fx:00000000-0000-0000-0000-000000000001" in button_data
    assert "rf:2026-08-21" in button_data
    assert "menu:main" in button_data
    assert not any(data.startswith("pg:") for data in button_data)


def test_build_fixture_page_empty_returns_safe_text() -> None:
    text, keyboard = build_fixture_page([], 0, date(2026, 8, 21), TIMEZONE)
    assert text == "На 2026-08-21 матчей нет."
    assert keyboard is None


def test_build_fixture_page_pagination_buttons() -> None:
    fixtures = [
        _fixture(f"00000000-0000-0000-0000-{i:012d}", "l", "2026-08-21T17:00:00Z")
        for i in range(PAGE_SIZE + 1)
    ]
    _, keyboard = build_fixture_page(fixtures, 0, date(2026, 8, 21), TIMEZONE)
    assert keyboard is not None
    data = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert "pg:2026-08-21:1" in data
    assert "pg:2026-08-21:0" not in data


def test_render_fixture_detail_shows_available_fields_only() -> None:
    fixture = _fixture(
        "00000000-0000-0000-0000-000000000001",
        "premier-league",
        "2026-08-21T18:30:00Z",
        venue="Эмирейтс",
        round_name="Тур 1",
    )
    text = render_fixture_detail(fixture, TIMEZONE)
    assert "Команда A — Команда B" in text
    assert "Место: Эмирейтс" in text
    assert "Тур: Тур 1" in text
    assert "Начало: 21 авг. 20:30 Europe/Warsaw" in text
    assert "Статус: NS" in text
    assert "Venue:" not in text
    assert "Start:" not in text

    bare = _fixture(
        "00000000-0000-0000-0000-000000000002",
        "la-liga",
        "2026-08-21T19:00:00Z",
        home=None,
        away=None,
    )
    text = render_fixture_detail(bare, TIMEZONE)
    assert "Место:" not in text
    assert "Тур:" not in text
    assert "— — —" in text


def test_render_dashboard_without_invented_metrics() -> None:
    fixtures = [
        _fixture(f"00000000-0000-0000-0000-{i:012d}", f"league-{i}", "2026-08-21T17:00:00Z")
        for i in range(7)
    ]
    text = render_dashboard(fixtures, HealthStatus(api=True, database=True, redis=True), TIMEZONE)
    assert "Sports Intelligence" in text
    assert "Сегодня: 7 матчей" in text
    assert "Бэкенд: исправен" in text
    assert "league-4" in text
    assert "league-6" not in text
    assert "quota" not in text.lower()
    assert "квота" not in text.lower()

    empty = render_dashboard([], HealthStatus(api=False), TIMEZONE)
    assert "Сегодня: 0 матчей" in empty
    assert "Бэкенд: недоступен" in empty
    assert "Лиги: —" in empty


def test_render_health_concise_without_secrets() -> None:
    text = render_health(HealthStatus(api=True, database=True, redis=True))
    assert text == "API: OK\nDatabase: OK\nRedis: OK"

    degraded = render_health(HealthStatus(api=False))
    assert degraded == "API: недоступен\nDatabase: —\nRedis: —"


def test_render_discover_shows_idempotency_flag() -> None:
    result = DiscoverResult(
        job_id=uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
        status="PENDING",
        already_queued=False,
    )
    text = render_discover(result)
    assert "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in text
    assert "Статус: PENDING" in text
    assert "Уже в очереди: нет" in text

    duplicate = render_discover(result.model_copy(update={"already_queued": True}))
    assert "Уже в очереди: да (дубликатов не создано)" in duplicate
