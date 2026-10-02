from __future__ import annotations

import html
from typing import Any
from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from sports_intelligence.bot.backend_client import BackendClientError
from sports_intelligence.bot.context import AppContext
from sports_intelligence.bot.menu import back_to_main_keyboard
from sports_intelligence.bot.strings import SAFE_BACKEND_ERROR

router = Router(name="m9_experiments")


def bounded_escape(value: str, limit: int = 700) -> str:
    """Keep the Telegram markup bounded without cutting an HTML entity."""
    parts: list[str] = []
    size = 0
    for char in value:
        escaped = html.escape(char)
        if size + len(escaped) > limit:
            break
        parts.append(escaped)
        size += len(escaped)
    return "".join(parts)


def list_keyboard(rows: list[dict[str, Any]], kind: str, offset: int) -> InlineKeyboardMarkup:
    keys = [
        [
            InlineKeyboardButton(
                text=str(r.get("title") or r.get("name"))[:55], callback_data=f"m9:{kind}:{r['id']}"
            )
        ]
        for r in rows
    ]
    if offset:
        keys.append(
            [
                InlineKeyboardButton(
                    text="Назад", callback_data=f"m9:list-{kind}:{max(0, offset - 8)}"
                )
            ]
        )
    if len(rows) == 8:
        keys.append(
            [InlineKeyboardButton(text="Далее", callback_data=f"m9:list-{kind}:{offset + 8}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=keys + back_to_main_keyboard().inline_keyboard)


async def list_screen(
    context: AppContext, kind: str, offset: int = 0
) -> tuple[str, InlineKeyboardMarkup]:
    rows = await (
        context.backend.improvement_list(offset)
        if kind == "proposal"
        else context.backend.experiment_list(offset)
    )
    lines = ["Предложения улучшений" if kind == "proposal" else "Эксперименты"]
    for row in rows:
        lines.append(
            f"{html.escape(row['status'])}: {html.escape(row.get('title') or row['name'])}"
        )
        if kind == "proposal":
            lines.append(f"Выборка: {row['sample_size']}; риск: {html.escape(row['risk_level'])}")
    if not rows:
        lines.append("Записей пока нет.")
    return "\n".join(lines), list_keyboard(rows, kind, offset)


@router.message(Command("improvements", "experiments"))
async def improvements_command(message: Message, context: AppContext) -> None:
    try:
        kind = "experiment" if (message.text or "").startswith("/experiments") else "proposal"
        text, keyboard = await list_screen(context, kind)
    except BackendClientError:
        text, keyboard = SAFE_BACKEND_ERROR, back_to_main_keyboard()
    await context.transport.send_text(message.chat.id, text, reply_markup=keyboard)


@router.callback_query(
    F.data.startswith("m9:") | (F.data == "menu:experiments") | (F.data == "menu:improvements")
)
async def experiment_callback(callback: CallbackQuery, context: AppContext) -> None:
    await context.transport.answer_callback(callback.id)
    if callback.message is None:
        return
    keyboard = back_to_main_keyboard()
    try:
        value = callback.data or ""
        if value.startswith("menu:"):
            kind = "experiment" if value == "menu:experiments" else "proposal"
            text, keyboard = await list_screen(context, kind)
        else:
            _, action, identity = value.split(":")
            if action.startswith("list-"):
                offset = int(identity)
                if (
                    offset < 0
                    or offset > 100000
                    or action not in ("list-proposal", "list-experiment")
                ):
                    raise ValueError("invalid list callback")
                text, keyboard = await list_screen(context, action.removeprefix("list-"), offset)
            else:
                identity = str(UUID(identity))
                if action in ("approve", "reject"):
                    row = await context.backend.improvement_action(
                        identity,
                        "approve-experiment" if action == "approve" else "reject",
                        f"telegram:{callback.from_user.id}",
                    )
                    text = (
                        f"{html.escape(row['status'])}\n{html.escape(row['title'])}\n"
                        "Production не изменён. Эксперимент требует отдельного запуска."
                    )
                elif action == "proposal":
                    row = await context.backend.improvement_view(identity)
                    text = (
                        f"{html.escape(row['title'])}\n"
                        f"{html.escape(row['status'])}; n={row['sample_size']}\n"
                        f"{bounded_escape(row['problem'])}\n"
                        f"Гипотеза: {bounded_escape(row['hypothesis'])}\n"
                        f"План: {bounded_escape(row['test_plan'])}\n"
                        "Одобрение: тест candidate prompt на прежней выборке. "
                        "Production не изменяется."
                    )
                    if row["status"] == "PROPOSED":
                        keyboard = InlineKeyboardMarkup(
                            inline_keyboard=[
                                [
                                    InlineKeyboardButton(
                                        text="Одобрить эксперимент",
                                        callback_data=f"m9:approve:{identity}",
                                    )
                                ],
                                [
                                    InlineKeyboardButton(
                                        text="Отклонить", callback_data=f"m9:reject:{identity}"
                                    )
                                ],
                            ]
                            + keyboard.inline_keyboard
                        )
                elif action == "experiment":
                    row = await context.backend.experiment_view(identity)
                    definition = row["definition"]
                    lines = [
                        html.escape(row["name"]),
                        html.escape(row["status"]),
                        bounded_escape(definition["hypothesis"]),
                    ]
                    for arm in ("control", "treatment"):
                        spec = definition[arm]
                        lines.append(
                            html.escape(
                                f"{arm}: {spec['route']} / {spec['prompt']} / "
                                f"{spec['variant']} / {spec['phase']}"
                            )
                        )
                    if row["runs"]:
                        run = row["runs"][0]
                        counts = run["counts"]
                        lines.append(
                            f"requested={counts['requested']}, eligible={counts['eligible']}, "
                            f"paired={counts.get('paired', 0)}"
                        )
                        comparison = run.get("comparison")
                        if comparison:
                            lines.append(html.escape(comparison["interpretation"]))
                            for name in ("binary_brier", "binary_log_loss"):
                                delta = comparison["paired_deltas"].get(name)
                                if delta:
                                    lines.append(
                                        f"Δ {name}: {delta['treatment_minus_control']:.4g} "
                                        f"(n={delta['sample_size']})"
                                    )
                    lines.append("Измерения; значимость и превосходство не доказаны.")
                    text = "\n".join(lines)
                else:
                    raise ValueError("invalid callback")
    except (ValueError, IndexError, KeyError, TypeError, BackendClientError):
        text = SAFE_BACKEND_ERROR
    await context.transport.edit_text(
        callback.message.chat.id, callback.message.message_id, text, reply_markup=keyboard
    )
