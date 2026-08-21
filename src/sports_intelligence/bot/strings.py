from __future__ import annotations

# Telegram UI text (single language: Russian). Only the bot-facing
# surface uses these strings; the rest of the codebase and the docs
# stay in English.

WELCOME = "Добро пожаловать в <b>Sports Intelligence</b> — ваш личный командный пункт."

MAIN_MENU_HINT = "<b>Главное меню</b>\n\nВыберите действие."

HELP_TEXT = (
    "<b>Команды</b>\n"
    "/start — приветствие и главное меню\n"
    "/dashboard — обзор на сегодня\n"
    "/today — сегодняшние матчи\n"
    "/fixtures [ГГГГ-ММ-ДД] — матчи на дату\n"
    "/match &lt;uuid&gt; — детали матча\n"
    "/health — состояние системы\n"
    "/discover [ГГГГ-ММ-ДД] — собрать данные"
)

FIND_PROMPT = (
    "<b>Найти матчи</b>\n\n"
    "Кнопки ниже открывают ближайшие дни. "
    "Для произвольной даты: /fixtures ГГГГ-ММ-ДД."
)

SAFE_BACKEND_ERROR = "Бэкенд временно недоступен. Попробуйте позже."

INVALID_DATE = "Неверный формат даты. Используйте /fixtures ГГГГ-ММ-ДД."
INVALID_DATE_DISCOVER = "Неверный формат даты. Используйте /discover ГГГГ-ММ-ДД."
INVALID_FIXTURE_ID = "Неверный формат ID матча. Используйте /match <fixture-uuid>."
FIXTURE_NOT_FOUND = "Матч не найден."
UNKNOWN_ACTION = "Неизвестное действие."

OK_LABEL = "OK"
UNAVAILABLE_LABEL = "недоступен"
UNKNOWN_LABEL = "—"

BACK_LABEL = "← Назад"
TODAY_LABEL = "Сегодня"
YESTERDAY_LABEL = "Вчера"
TOMORROW_LABEL = "Завтра"
HEALTH_LABEL = "Здоровье"
HELP_LABEL = "Помощь"
FIND_LABEL = "Найти"
DISCOVER_LABEL = "Собрать"

PREV_LABEL = "Назад"
NEXT_LABEL = "Вперёд"
REFRESH_LABEL = "Обновить"

ACCESS_DENIED = "Доступ запрещён."

RU_MONTHS = (
    "янв.",
    "фев.",
    "мар.",
    "апр.",
    "мая",
    "июн.",
    "июл.",
    "авг.",
    "сен.",
    "окт.",
    "ноя.",
    "дек.",
)


def no_fixtures_for(date_iso: str) -> str:
    return f"На {date_iso} матчей нет."


def not_available(command: str) -> str:
    return f"/{command} недоступна в этой вехе (M3)."
