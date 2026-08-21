from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from aiogram.filters import CommandObject

from sports_intelligence.bot import handlers
from sports_intelligence.bot.backend_client import (
    BackendResponseError,
    BackendUnavailableError,
    DiscoverResult,
    FixtureView,
    HealthStatus,
)
from sports_intelligence.bot.callback_data import (
    MENU_FIND,
    MENU_HEALTH,
    MENU_HELP,
    MENU_MAIN,
    MENU_TODAY,
)
from sports_intelligence.bot.context import AppContext
from sports_intelligence.bot.menu import (
    back_to_main_keyboard,
    dashboard_keyboard,
    find_menu_keyboard,
    main_menu_keyboard,
)
from sports_intelligence.core.config import Settings
from telegram_fakes import FakeTransport, make_callback, make_message

FIXED_NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)
TZ = "Europe/Warsaw"

FIXTURE_A = FixtureView(
    id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
    league_slug="premier-league",
    home_team="Arsenal",
    away_team="Coventry",
    kickoff_at=datetime(2026, 8, 21, 18, 30, tzinfo=UTC),
    venue="Emirates",
    round=None,
    status="NS",
)
FIXTURE_B = FixtureView(
    id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
    league_slug="premier-league",
    home_team=None,
    away_team="Nullfield United",
    kickoff_at=datetime(2026, 8, 21, 19, 30, tzinfo=UTC),
    venue=None,
    round=None,
    status="NS",
)
FIXTURE_C = FixtureView(
    id=uuid.UUID("00000000-0000-0000-0000-000000000003"),
    league_slug="la-liga",
    home_team="Real Madrid",
    away_team="Sevilla",
    kickoff_at=datetime(2026, 8, 21, 20, 0, tzinfo=UTC),
    venue="Bernabeu",
    round="Round 2",
    status="1H",
)


class FakeBackend:
    def __init__(self) -> None:
        self.fixtures: list[FixtureView] = []
        self.fixture: FixtureView | None = None
        self.health_status = HealthStatus(api=True, database=True, redis=True)
        self.discover_result = DiscoverResult(
            job_id=uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
            status="PENDING",
            already_queued=False,
        )
        self.error: Exception | None = None
        self.discover_calls: list[date] = []
        self.fixture_lookups: list[str] = []

    async def list_fixtures(self, fixture_date: date | None = None) -> list[FixtureView]:
        if self.error is not None:
            raise self.error
        return self.fixtures

    async def get_fixture(self, fixture_id: str) -> FixtureView | None:
        self.fixture_lookups.append(fixture_id)
        if self.error is not None:
            raise self.error
        return self.fixture

    async def health(self) -> HealthStatus:
        return self.health_status

    async def discover(self, fixture_date: date) -> DiscoverResult:
        self.discover_calls.append(fixture_date)
        if self.error is not None:
            raise self.error
        return self.discover_result


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend()


@pytest.fixture
def transport() -> FakeTransport:
    return FakeTransport()


@pytest.fixture
def context(backend: FakeBackend, transport: FakeTransport) -> AppContext:
    settings = Settings(
        _env_file=None,
        app_env="mock",
        app_timezone=TZ,
        telegram_bot_token="test-token",
        telegram_allowed_user_ids=[1],
    )
    return AppContext(
        transport=transport,  # type: ignore[arg-type]
        backend=backend,  # type: ignore[arg-type]
        settings=settings,
        allowed_user_ids=frozenset({1}),
    )


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(handlers, "utc_now", lambda: FIXED_NOW)


def _button_texts(keyboard) -> list[str]:
    return [button.text for row in keyboard.inline_keyboard for button in row]


def _back_present(keyboard) -> bool:
    return any(
        button.callback_data == MENU_MAIN for row in keyboard.inline_keyboard for button in row
    )


async def test_start_welcomes_user_with_main_menu(
    context: AppContext, transport: FakeTransport
) -> None:
    message = make_message("/start")
    await handlers.start_command(message, context)
    assert len(transport.sent) == 1
    sent = transport.sent[0]
    assert "Sports Intelligence" in sent["text"]
    assert "Главное меню" in sent["text"]
    texts = _button_texts(sent["reply_markup"])
    assert "Сегодня" in texts
    assert "Найти" in texts
    assert "Здоровье" in texts
    assert "Помощь" in texts


async def test_help_lists_commands_with_back(context: AppContext, transport: FakeTransport) -> None:
    message = make_message("/help")
    await handlers.help_command(message, context)
    sent = transport.sent[0]
    assert "/today" in sent["text"]
    assert "/discover" in sent["text"]
    assert "/match" in sent["text"]
    assert _back_present(sent["reply_markup"])


async def test_today_with_zero_fixtures(context: AppContext, transport: FakeTransport) -> None:
    message = make_message("/today")
    await handlers.today_command(message, context)
    sent = transport.sent[0]
    assert sent["text"] == "На 2026-08-21 матчей нет."
    assert _back_present(sent["reply_markup"])


async def test_today_groups_fixtures_by_league(
    context: AppContext, backend: FakeBackend, transport: FakeTransport
) -> None:
    backend.fixtures = [FIXTURE_C, FIXTURE_A, FIXTURE_B]
    message = make_message("/today")
    await handlers.today_command(message, context)
    text = transport.sent[0]["text"]
    assert "premier-league" in text
    assert "la-liga" in text
    assert "20:30 Arsenal — Coventry" in text
    assert "21:30 — — Nullfield United" in text
    assert "22:00 Real Madrid — Sevilla" in text
    assert _back_present(transport.sent[0]["reply_markup"])


async def test_fixtures_command_with_explicit_date(
    context: AppContext, backend: FakeBackend, transport: FakeTransport
) -> None:
    backend.fixtures = [FIXTURE_A]
    message = make_message("/fixtures")
    command = CommandObject(command="fixtures", args="2026-08-25")
    await handlers.fixtures_command(message, command, context)
    assert "2026-08-25" in transport.sent[0]["text"]


async def test_fixtures_command_rejects_invalid_date(
    context: AppContext, transport: FakeTransport
) -> None:
    message = make_message("/fixtures")
    command = CommandObject(command="fixtures", args="not-a-date")
    await handlers.fixtures_command(message, command, context)
    assert transport.sent[0]["text"] == "Неверный формат даты. Используйте /fixtures ГГГГ-ММ-ДД."


async def test_match_with_valid_uuid(
    context: AppContext, backend: FakeBackend, transport: FakeTransport
) -> None:
    backend.fixture = FIXTURE_C
    message = make_message("/match")
    command = CommandObject(command="match", args=str(FIXTURE_C.id))
    await handlers.match_command(message, command, context)
    text = transport.sent[0]["text"]
    assert "Real Madrid — Sevilla" in text
    assert "Начало: 21 авг. 22:00 Europe/Warsaw" in text
    assert backend.fixture_lookups == [str(FIXTURE_C.id)]
    assert _back_present(transport.sent[0]["reply_markup"])


async def test_match_with_invalid_uuid(
    context: AppContext, backend: FakeBackend, transport: FakeTransport
) -> None:
    message = make_message("/match")
    command = CommandObject(command="match", args="not-a-uuid")
    await handlers.match_command(message, command, context)
    assert (
        transport.sent[0]["text"] == "Неверный формат ID матча. Используйте /match <fixture-uuid>."
    )
    assert backend.fixture_lookups == []


async def test_match_missing_fixture(
    context: AppContext, backend: FakeBackend, transport: FakeTransport
) -> None:
    backend.fixture = None
    message = make_message("/match")
    command = CommandObject(command="match", args=str(FIXTURE_A.id))
    await handlers.match_command(message, command, context)
    assert transport.sent[0]["text"] == "Матч не найден."


async def test_backend_unavailable_produces_safe_message(
    context: AppContext, backend: FakeBackend, transport: FakeTransport
) -> None:
    backend.error = BackendUnavailableError("backend is unreachable")
    message = make_message("/today")
    await handlers.today_command(message, context)
    assert transport.sent[0]["text"] == "Бэкенд временно недоступен. Попробуйте позже."

    backend.error = BackendResponseError(500)
    message = make_message("/match")
    command = CommandObject(command="match", args=str(FIXTURE_A.id))
    await handlers.match_command(message, command, context)
    assert transport.sent[1]["text"] == "Бэкенд временно недоступен. Попробуйте позже."


async def test_no_secrets_or_internal_details_in_messages(
    context: AppContext, backend: FakeBackend, transport: FakeTransport
) -> None:
    backend.error = BackendUnavailableError(
        "backend is unreachable postgres://secret:pass@db/sports_intel"
    )
    message = make_message("/discover")
    await handlers.discover_command(message, CommandObject(command="discover", args=""), context)
    text = transport.sent[0]["text"]
    assert text == "Бэкенд временно недоступен. Попробуйте позже."
    assert "secret" not in text
    assert "test-token" not in text
    assert "sports_intel" not in text


async def test_discover_shows_job_and_idempotency(
    context: AppContext, backend: FakeBackend, transport: FakeTransport
) -> None:
    message = make_message("/discover")
    await handlers.discover_command(message, CommandObject(command="discover", args=""), context)
    text = transport.sent[0]["text"]
    assert "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in text
    assert "Статус: PENDING" in text
    assert "Уже в очереди: нет" in text
    assert backend.discover_calls == [date(2026, 8, 21)]
    assert _back_present(transport.sent[0]["reply_markup"])


async def test_duplicate_discover_keeps_backend_idempotency(
    context: AppContext, backend: FakeBackend, transport: FakeTransport
) -> None:
    backend.discover_result = backend.discover_result.model_copy(update={"already_queued": True})
    message = make_message("/discover")
    await handlers.discover_command(message, CommandObject(command="discover", args=""), context)
    assert "Уже в очереди: да (дубликатов не создано)" in transport.sent[0]["text"]


async def test_discover_rejects_invalid_date(
    context: AppContext, backend: FakeBackend, transport: FakeTransport
) -> None:
    message = make_message("/discover")
    command = CommandObject(command="discover", args="garbage")
    await handlers.discover_command(message, command, context)
    assert transport.sent[0]["text"] == "Неверный формат даты. Используйте /discover ГГГГ-ММ-ДД."
    assert backend.discover_calls == []


async def test_health_shows_concise_status(
    context: AppContext, backend: FakeBackend, transport: FakeTransport
) -> None:
    message = make_message("/health")
    await handlers.health_command(message, context)
    assert transport.sent[0]["text"] == "API: OK\nDatabase: OK\nRedis: OK"
    assert _back_present(transport.sent[0]["reply_markup"])

    backend.health_status = HealthStatus(api=False)
    message = make_message("/health")
    await handlers.health_command(message, context)
    assert transport.sent[1]["text"] == "API: недоступен\nDatabase: —\nRedis: —"


async def test_dashboard_renders_existing_capabilities_only(
    context: AppContext,
    backend: FakeBackend,
    transport: FakeTransport,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sports_intelligence.bot import formatting

    monkeypatch.setattr(formatting, "utc_now", lambda: FIXED_NOW)
    backend.fixtures = [FIXTURE_A, FIXTURE_B, FIXTURE_C]
    message = make_message("/dashboard")
    await handlers.dashboard_command(message, context)
    text = transport.sent[0]["text"]
    assert "Сегодня: 3 матчей" in text
    assert "Бэкенд: исправен" in text
    assert "2026-08-21" in text
    assert "квота" not in text.lower()
    assert transport.sent[0]["reply_markup"] is not None
    assert _back_present(transport.sent[0]["reply_markup"])


async def test_not_available_commands_are_explicit(
    context: AppContext, transport: FakeTransport
) -> None:
    message = make_message("/predictions")
    await handlers._not_available(message, CommandObject(command="predictions", args=""), context)
    assert transport.sent[0]["text"] == "/predictions недоступна в этой вехе (M3)."
    assert _back_present(transport.sent[0]["reply_markup"])


async def test_main_menu_callback_renders_main_menu(
    context: AppContext, transport: FakeTransport
) -> None:
    callback = make_callback(MENU_MAIN)
    await handlers.main_menu_callback(callback, context)
    assert transport.answered == [{"callback_query_id": "cb-test-1"}]
    text = transport.edited[0]["text"]
    assert "Главное меню" in text
    assert _back_present(transport.edited[0]["reply_markup"]) is False
    button_data = [
        button.callback_data
        for row in transport.edited[0]["reply_markup"].inline_keyboard
        for button in row
    ]
    assert MENU_TODAY in button_data
    assert MENU_FIND in button_data
    assert MENU_HEALTH in button_data
    assert MENU_HELP in button_data


async def test_today_menu_callback_renders_fixtures(
    context: AppContext, backend: FakeBackend, transport: FakeTransport
) -> None:
    backend.fixtures = [FIXTURE_A, FIXTURE_B]
    callback = make_callback(MENU_TODAY)
    await handlers.today_menu_callback(callback, context)
    text = transport.edited[0]["text"]
    assert "premier-league" in text
    assert "20:30 Arsenal — Coventry" in text
    assert _back_present(transport.edited[0]["reply_markup"])


async def test_find_menu_callback_renders_relative_dates(
    context: AppContext, transport: FakeTransport
) -> None:
    callback = make_callback(MENU_FIND)
    await handlers.find_menu_callback(callback, context)
    text = transport.edited[0]["text"]
    assert "Найти матчи" in text
    assert "/fixtures ГГГГ-ММ-ДД" in text
    data = [
        button.callback_data
        for row in transport.edited[0]["reply_markup"].inline_keyboard
        for button in row
    ]
    assert "pg:2026-08-20:0" in data
    assert "pg:2026-08-21:0" in data
    assert "pg:2026-08-22:0" in data
    assert _back_present(transport.edited[0]["reply_markup"])


async def test_health_menu_callback_renders_health(
    context: AppContext, transport: FakeTransport
) -> None:
    callback = make_callback(MENU_HEALTH)
    await handlers.health_menu_callback(callback, context)
    assert transport.edited[0]["text"] == "API: OK\nDatabase: OK\nRedis: OK"
    assert _back_present(transport.edited[0]["reply_markup"])


async def test_help_menu_callback_renders_help(
    context: AppContext, transport: FakeTransport
) -> None:
    callback = make_callback(MENU_HELP)
    await handlers.help_menu_callback(callback, context)
    text = transport.edited[0]["text"]
    assert "/today" in text
    assert "/discover" in text
    assert _back_present(transport.edited[0]["reply_markup"])


async def test_fixture_callback_shows_detail(
    context: AppContext, backend: FakeBackend, transport: FakeTransport
) -> None:
    backend.fixture = FIXTURE_A
    callback = make_callback(f"fx:{FIXTURE_A.id}")
    await handlers.fixture_callback_handler(callback, context)
    assert backend.fixture_lookups == [str(FIXTURE_A.id)]
    assert "Arsenal — Coventry" in transport.edited[0]["text"]
    assert _back_present(transport.edited[0]["reply_markup"])


async def test_fixture_callback_missing_fixture(
    context: AppContext, backend: FakeBackend, transport: FakeTransport
) -> None:
    backend.fixture = None
    callback = make_callback(f"fx:{FIXTURE_A.id}")
    await handlers.fixture_callback_handler(callback, context)
    assert transport.edited[0]["text"] == "Матч не найден."
    assert _back_present(transport.edited[0]["reply_markup"])


async def test_malformed_fixture_callback_is_harmless(
    context: AppContext, transport: FakeTransport
) -> None:
    callback = make_callback("fx:not-a-uuid")
    await handlers.fixture_callback_handler(callback, context)
    assert transport.edited[0]["text"] == "Неизвестное действие."
    assert _back_present(transport.edited[0]["reply_markup"])


async def test_tampered_page_callback_is_harmless(
    context: AppContext, transport: FakeTransport
) -> None:
    callback = make_callback("pg:not-a-date:99")
    await handlers.page_callback_handler(callback, context)
    assert transport.edited[0]["text"] == "Неизвестное действие."
    assert _back_present(transport.edited[0]["reply_markup"])


async def test_unknown_callback_gets_silent_answer(
    context: AppContext, transport: FakeTransport
) -> None:
    callback = make_callback("random-garbage")
    await handlers.unknown_callback(callback, context)
    assert transport.answered == [{"callback_query_id": "cb-test-1"}]
    assert transport.edited == []
    assert transport.sent == []


async def test_page_callback_navigates_and_refresh_returns_to_first_page(
    context: AppContext, backend: FakeBackend, transport: FakeTransport
) -> None:
    from sports_intelligence.bot.formatting import PAGE_SIZE

    backend.fixtures = [
        FixtureView(
            id=uuid.uuid4(),
            league_slug="premier-league",
            home_team=f"Team {i}",
            away_team="Opponent",
            kickoff_at=datetime(2026, 8, 21, 17, 0, tzinfo=UTC),
            venue=None,
            round=None,
            status="NS",
        )
        for i in range(PAGE_SIZE + 2)
    ]
    callback = make_callback("pg:2026-08-21:1")
    await handlers.page_callback_handler(callback, context)
    assert "Стр. 2/2" in transport.edited[0]["text"]
    assert _back_present(transport.edited[0]["reply_markup"])

    refresh = make_callback("rf:2026-08-21")
    await handlers.refresh_callback_handler(refresh, context)
    assert "Стр. 1/2" in transport.edited[1]["text"]
    assert _back_present(transport.edited[1]["reply_markup"])


async def test_discover_callback_enqueues_for_local_today(
    context: AppContext, backend: FakeBackend, transport: FakeTransport
) -> None:
    callback = make_callback("disc")
    await handlers.discover_callback(callback, context)
    assert backend.discover_calls == [date(2026, 8, 21)]
    assert "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee" in transport.edited[0]["text"]
    assert _back_present(transport.edited[0]["reply_markup"])


async def test_health_callback_renders_status(
    context: AppContext, transport: FakeTransport
) -> None:
    callback = make_callback("health")
    await handlers.health_callback(callback, context)
    assert transport.edited[0]["text"] == "API: OK\nDatabase: OK\nRedis: OK"
    assert _back_present(transport.edited[0]["reply_markup"])


# Direct menu builder tests (pure functions).


def test_main_menu_keyboard_has_four_buttons() -> None:
    keyboard = main_menu_keyboard()
    texts = _button_texts(keyboard)
    assert texts == ["Сегодня", "Найти", "Здоровье", "Помощь"]


def test_find_menu_keyboard_has_quick_dates_and_back() -> None:
    keyboard = find_menu_keyboard(date(2026, 8, 21))
    data = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert "pg:2026-08-20:0" in data
    assert "pg:2026-08-21:0" in data
    assert "pg:2026-08-22:0" in data
    assert _back_present(keyboard)


def test_dashboard_keyboard_has_actions_and_back() -> None:
    keyboard = dashboard_keyboard(date(2026, 8, 21))
    data = [button.callback_data for row in keyboard.inline_keyboard for button in row]
    assert "pg:2026-08-21:0" in data
    assert "disc" in data
    assert "health" in data
    assert _back_present(keyboard)


def test_back_to_main_keyboard_is_singleton() -> None:
    keyboard = back_to_main_keyboard()
    assert len(keyboard.inline_keyboard) == 1
    row = keyboard.inline_keyboard[0]
    assert len(row) == 1
    assert row[0].callback_data == MENU_MAIN
    assert row[0].text == "← Назад"
