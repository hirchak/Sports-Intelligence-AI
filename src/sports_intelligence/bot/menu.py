from __future__ import annotations

from datetime import date, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sports_intelligence.bot.callback_data import (
    DISCOVER_CALLBACK,
    HEALTH_CALLBACK,
    MENU_FIND,
    MENU_HEALTH,
    MENU_HELP,
    MENU_MAIN,
    MENU_TODAY,
    page_callback,
)
from sports_intelligence.bot.strings import (
    BACK_LABEL,
    DISCOVER_LABEL,
    FIND_LABEL,
    HEALTH_LABEL,
    HELP_LABEL,
    TODAY_LABEL,
    TOMORROW_LABEL,
    YESTERDAY_LABEL,
)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Top-level menu shown after /start and on every Back."""
    builder = InlineKeyboardBuilder()
    builder.button(text=TODAY_LABEL, callback_data=MENU_TODAY)
    builder.button(text=FIND_LABEL, callback_data=MENU_FIND)
    builder.button(text=HEALTH_LABEL, callback_data=MENU_HEALTH)
    builder.button(text=HELP_LABEL, callback_data=MENU_HELP)
    builder.adjust(1)
    return builder.as_markup()


def find_menu_keyboard(today: date) -> InlineKeyboardMarkup:
    """Quick-pick relative dates: yesterday / today / tomorrow, plus Back."""
    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    builder = InlineKeyboardBuilder()
    builder.button(text=YESTERDAY_LABEL, callback_data=page_callback(yesterday, 0))
    builder.button(text=TODAY_LABEL, callback_data=page_callback(today, 0))
    builder.button(text=TOMORROW_LABEL, callback_data=page_callback(tomorrow, 0))
    builder.adjust(3)
    builder.row(InlineKeyboardButton(text=BACK_LABEL, callback_data=MENU_MAIN))
    return builder.as_markup()


def dashboard_keyboard(fixture_date: date) -> InlineKeyboardMarkup:
    """Dashboard buttons: jump to fixtures, enqueue discover, see health, Back."""
    builder = InlineKeyboardBuilder()
    builder.button(text=TODAY_LABEL, callback_data=page_callback(fixture_date, 0))
    builder.button(text=DISCOVER_LABEL, callback_data=DISCOVER_CALLBACK)
    builder.button(text=HEALTH_LABEL, callback_data=HEALTH_CALLBACK)
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text=BACK_LABEL, callback_data=MENU_MAIN))
    return builder.as_markup()


def back_to_main_keyboard() -> InlineKeyboardMarkup:
    """Single-row Back keyboard used by single-screen responses."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=BACK_LABEL, callback_data=MENU_MAIN)]]
    )


def with_back(keyboard: InlineKeyboardMarkup) -> InlineKeyboardMarkup:
    """Append a Back row to any existing keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            *keyboard.inline_keyboard,
            [InlineKeyboardButton(text=BACK_LABEL, callback_data=MENU_MAIN)],
        ]
    )
