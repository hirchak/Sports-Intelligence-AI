from __future__ import annotations

import uuid
from datetime import date

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from sports_intelligence.bot.backend_client import BackendClientError, FixtureView
from sports_intelligence.bot.callback_data import (
    DISCOVER_CALLBACK,
    FIXTURE_PREFIX,
    HEALTH_CALLBACK,
    MENU_FIND,
    MENU_HEALTH,
    MENU_HELP,
    MENU_MAIN,
    MENU_TODAY,
    PAGE_PREFIX,
    REFRESH_PREFIX,
    parse_fixture_callback,
    parse_page_callback,
    parse_refresh_callback,
)
from sports_intelligence.bot.context import AppContext
from sports_intelligence.bot.formatting import (
    build_fixture_page,
    render_dashboard,
    render_discover,
    render_fixture_detail,
    render_health,
)
from sports_intelligence.bot.menu import (
    back_to_main_keyboard,
    dashboard_keyboard,
    find_menu_keyboard,
    main_menu_keyboard,
)
from sports_intelligence.bot.strings import (
    FIXTURE_NOT_FOUND,
    HELP_TEXT,
    INVALID_DATE,
    INVALID_DATE_DISCOVER,
    INVALID_FIXTURE_ID,
    MAIN_MENU_HINT,
    SAFE_BACKEND_ERROR,
    UNKNOWN_ACTION,
    WELCOME,
    not_available,
)
from sports_intelligence.core.logging import get_logger
from sports_intelligence.core.time import local_today, utc_now

logger = get_logger(__name__)

router = Router()

NOT_AVAILABLE_COMMANDS = ("predictions", "stats", "evaluate", "improvements")


@router.message(CommandStart())
async def start_command(message: Message, context: AppContext) -> None:
    await context.transport.send_text(
        message.chat.id,
        f"{WELCOME}\n\n{MAIN_MENU_HINT}",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("help"))
async def help_command(message: Message, context: AppContext) -> None:
    await context.transport.send_text(
        message.chat.id, HELP_TEXT, reply_markup=back_to_main_keyboard()
    )


@router.message(Command("dashboard"))
async def dashboard_command(message: Message, context: AppContext) -> None:
    today = local_today(utc_now(), context.settings.app_timezone)
    fixtures = await _fetch_fixtures(context, today)
    if fixtures is None:
        await context.transport.send_text(
            message.chat.id, SAFE_BACKEND_ERROR, reply_markup=back_to_main_keyboard()
        )
        return
    health = await context.backend.health()
    await context.transport.send_text(
        message.chat.id,
        render_dashboard(fixtures, health, context.settings.app_timezone),
        reply_markup=dashboard_keyboard(today),
    )


@router.message(Command("today"))
async def today_command(message: Message, context: AppContext) -> None:
    today = local_today(utc_now(), context.settings.app_timezone)
    await _send_fixture_page(message.chat.id, context, today, 0)


@router.message(Command("fixtures"))
async def fixtures_command(message: Message, command: CommandObject, context: AppContext) -> None:
    raw = (command.args or "").strip()
    if not raw:
        fixture_date = local_today(utc_now(), context.settings.app_timezone)
    else:
        try:
            fixture_date = date.fromisoformat(raw)
        except ValueError:
            await context.transport.send_text(
                message.chat.id, INVALID_DATE, reply_markup=back_to_main_keyboard()
            )
            return
    await _send_fixture_page(message.chat.id, context, fixture_date, 0)


@router.message(Command("match"))
async def match_command(message: Message, command: CommandObject, context: AppContext) -> None:
    raw = (command.args or "").strip()
    try:
        fixture_id = uuid.UUID(raw)
    except ValueError:
        await context.transport.send_text(
            message.chat.id, INVALID_FIXTURE_ID, reply_markup=back_to_main_keyboard()
        )
        return
    await _send_fixture_detail(message.chat.id, context, fixture_id)


@router.message(Command("discover"))
async def discover_command(message: Message, command: CommandObject, context: AppContext) -> None:
    raw = (command.args or "").strip()
    if not raw:
        fixture_date = local_today(utc_now(), context.settings.app_timezone)
    else:
        try:
            fixture_date = date.fromisoformat(raw)
        except ValueError:
            await context.transport.send_text(
                message.chat.id, INVALID_DATE_DISCOVER, reply_markup=back_to_main_keyboard()
            )
            return
    await context.transport.send_text(
        message.chat.id,
        await _discover_text(context, fixture_date),
        reply_markup=back_to_main_keyboard(),
    )


@router.message(Command("health"))
async def health_command(message: Message, context: AppContext) -> None:
    status = await context.backend.health()
    await context.transport.send_text(
        message.chat.id, render_health(status), reply_markup=back_to_main_keyboard()
    )


async def _not_available(message: Message, command: CommandObject, context: AppContext) -> None:
    name = command.command or "command"
    await context.transport.send_text(
        message.chat.id, not_available(name), reply_markup=back_to_main_keyboard()
    )


for _name in NOT_AVAILABLE_COMMANDS:
    router.message(Command(_name))(_not_available)


@router.callback_query(F.data == MENU_MAIN)
async def main_menu_callback(callback: CallbackQuery, context: AppContext) -> None:
    await context.transport.answer_callback(callback.id)
    await _answer_from_callback(
        callback, context, MAIN_MENU_HINT, reply_markup=main_menu_keyboard()
    )


@router.callback_query(F.data == MENU_TODAY)
async def today_menu_callback(callback: CallbackQuery, context: AppContext) -> None:
    await context.transport.answer_callback(callback.id)
    today = local_today(utc_now(), context.settings.app_timezone)
    await _render_page_from_callback(callback, context, today, 0)


@router.callback_query(F.data == MENU_FIND)
async def find_menu_callback(callback: CallbackQuery, context: AppContext) -> None:
    await context.transport.answer_callback(callback.id)
    today = local_today(utc_now(), context.settings.app_timezone)
    await _answer_from_callback(
        callback,
        context,
        "<b>Найти матчи</b>\n\n"
        "Кнопки ниже открывают ближайшие дни. "
        "Для произвольной даты: /fixtures ГГГГ-ММ-ДД.",
        reply_markup=find_menu_keyboard(today),
    )


@router.callback_query(F.data == MENU_HEALTH)
async def health_menu_callback(callback: CallbackQuery, context: AppContext) -> None:
    await context.transport.answer_callback(callback.id)
    status = await context.backend.health()
    await _answer_from_callback(
        callback, context, render_health(status), reply_markup=back_to_main_keyboard()
    )


@router.callback_query(F.data == MENU_HELP)
async def help_menu_callback(callback: CallbackQuery, context: AppContext) -> None:
    await context.transport.answer_callback(callback.id)
    await _answer_from_callback(callback, context, HELP_TEXT, reply_markup=back_to_main_keyboard())


@router.callback_query(F.data == HEALTH_CALLBACK)
async def health_callback(callback: CallbackQuery, context: AppContext) -> None:
    await context.transport.answer_callback(callback.id)
    status = await context.backend.health()
    await _answer_from_callback(
        callback, context, render_health(status), reply_markup=back_to_main_keyboard()
    )


@router.callback_query(F.data == DISCOVER_CALLBACK)
async def discover_callback(callback: CallbackQuery, context: AppContext) -> None:
    await context.transport.answer_callback(callback.id)
    fixture_date = local_today(utc_now(), context.settings.app_timezone)
    await _answer_from_callback(
        callback,
        context,
        await _discover_text(context, fixture_date),
        reply_markup=back_to_main_keyboard(),
    )


@router.callback_query(F.data.startswith(FIXTURE_PREFIX))
async def fixture_callback_handler(callback: CallbackQuery, context: AppContext) -> None:
    fixture_id = parse_fixture_callback(callback.data or "")
    if fixture_id is None:
        await _answer_from_callback(
            callback, context, UNKNOWN_ACTION, reply_markup=back_to_main_keyboard()
        )
        return
    await context.transport.answer_callback(callback.id)
    try:
        fixture = await context.backend.get_fixture(str(fixture_id))
    except BackendClientError:
        logger.warning("backend fixture detail call failed", exc_info=True)
        await _answer_from_callback(
            callback, context, SAFE_BACKEND_ERROR, reply_markup=back_to_main_keyboard()
        )
        return
    if fixture is None:
        await _answer_from_callback(
            callback, context, FIXTURE_NOT_FOUND, reply_markup=back_to_main_keyboard()
        )
        return
    await _answer_from_callback(
        callback,
        context,
        render_fixture_detail(fixture, context.settings.app_timezone),
        reply_markup=back_to_main_keyboard(),
    )


@router.callback_query(F.data.startswith(PAGE_PREFIX))
async def page_callback_handler(callback: CallbackQuery, context: AppContext) -> None:
    parsed = parse_page_callback(callback.data or "")
    if parsed is None:
        await _answer_from_callback(
            callback, context, UNKNOWN_ACTION, reply_markup=back_to_main_keyboard()
        )
        return
    fixture_date, page = parsed
    await _render_page_from_callback(callback, context, fixture_date, page)


@router.callback_query(F.data.startswith(REFRESH_PREFIX))
async def refresh_callback_handler(callback: CallbackQuery, context: AppContext) -> None:
    fixture_date = parse_refresh_callback(callback.data or "")
    if fixture_date is None:
        await _answer_from_callback(
            callback, context, UNKNOWN_ACTION, reply_markup=back_to_main_keyboard()
        )
        return
    await _render_page_from_callback(callback, context, fixture_date, 0)


@router.callback_query()
async def unknown_callback(callback: CallbackQuery, context: AppContext) -> None:
    await context.transport.answer_callback(callback.id)


async def _fetch_fixtures(context: AppContext, fixture_date: date) -> list[FixtureView] | None:
    try:
        return await context.backend.list_fixtures(fixture_date)
    except BackendClientError:
        logger.warning("backend fixtures call failed", exc_info=True)
        return None


async def _send_fixture_page(
    chat_id: int, context: AppContext, fixture_date: date, page: int
) -> None:
    fixtures = await _fetch_fixtures(context, fixture_date)
    if fixtures is None:
        await context.transport.send_text(
            chat_id, SAFE_BACKEND_ERROR, reply_markup=back_to_main_keyboard()
        )
        return
    text, keyboard = build_fixture_page(fixtures, page, fixture_date, context.settings.app_timezone)
    if keyboard is None:
        # No fixtures — render a short screen with Back.
        await context.transport.send_text(chat_id, text, reply_markup=back_to_main_keyboard())
        return
    await context.transport.send_text(chat_id, text, reply_markup=keyboard)


async def _render_page_from_callback(
    callback: CallbackQuery, context: AppContext, fixture_date: date, page: int
) -> None:
    await context.transport.answer_callback(callback.id)
    fixtures = await _fetch_fixtures(context, fixture_date)
    if fixtures is None:
        await _answer_from_callback(
            callback, context, SAFE_BACKEND_ERROR, reply_markup=back_to_main_keyboard()
        )
        return
    text, keyboard = build_fixture_page(fixtures, page, fixture_date, context.settings.app_timezone)
    if keyboard is None:
        await _answer_from_callback(callback, context, text, reply_markup=back_to_main_keyboard())
        return
    await _answer_from_callback(callback, context, text, reply_markup=keyboard)


async def _send_fixture_detail(chat_id: int, context: AppContext, fixture_id: uuid.UUID) -> None:
    try:
        fixture = await context.backend.get_fixture(str(fixture_id))
    except BackendClientError:
        logger.warning("backend fixture detail call failed", exc_info=True)
        await context.transport.send_text(
            chat_id, SAFE_BACKEND_ERROR, reply_markup=back_to_main_keyboard()
        )
        return
    if fixture is None:
        await context.transport.send_text(
            chat_id, FIXTURE_NOT_FOUND, reply_markup=back_to_main_keyboard()
        )
        return
    await context.transport.send_text(
        chat_id,
        render_fixture_detail(fixture, context.settings.app_timezone),
        reply_markup=back_to_main_keyboard(),
    )


async def _discover_text(context: AppContext, fixture_date: date) -> str:
    try:
        result = await context.backend.discover(fixture_date)
    except BackendClientError:
        logger.warning("backend discovery call failed", exc_info=True)
        return SAFE_BACKEND_ERROR
    logger.info(
        "telegram discovery job enqueued",
        extra={"job_id": str(result.job_id), "fixture_date": fixture_date.isoformat()},
    )
    return render_discover(result)


async def _answer_from_callback(
    callback: CallbackQuery,
    context: AppContext,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    if callback.message is None:
        return
    try:
        await context.transport.edit_text(
            callback.message.chat.id, callback.message.message_id, text, reply_markup
        )
    except Exception:
        logger.warning("failed to edit telegram message; sending a new one", exc_info=True)
        await context.transport.send_text(callback.message.chat.id, text, reply_markup)
