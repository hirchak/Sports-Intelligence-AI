from __future__ import annotations

import html
import uuid
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from sports_intelligence.bot.backend_client import BackendClientError
from sports_intelligence.bot.context import AppContext
from sports_intelligence.bot.menu import back_to_main_keyboard
from sports_intelligence.bot.strings import SAFE_BACKEND_ERROR

router = Router(name="m8_evaluation")


def stats_keyboard(period: str = "30d") -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text=label, callback_data=f"stats:{value}:summary")
            for label, value in (("7 дней", "7d"), ("30 дней", "30d"), ("Всё время", "all"))
        ]
    ]
    rows += [
        [InlineKeyboardButton(text=label, callback_data=f"stats:{period}:{facet}")]
        for label, facet in (
            ("По лиге", "league"),
            ("По рынку", "market"),
            ("По модели", "model"),
            ("По коэффициентам", "odds_bucket"),
        )
    ]
    rows += [[InlineKeyboardButton(text="Последние результаты", callback_data="results:recent")]]
    return InlineKeyboardMarkup(inline_keyboard=rows + back_to_main_keyboard().inline_keyboard)


def render_stats(payload: dict[str, Any], period: str = "30d") -> str:
    title = {"7d": "Последние 7 дней", "30d": "Последние 30 дней", "all": "Всё время"}[period]
    lines = [f"<b>{title}</b>"]
    if payload.get("status") != "SUCCEEDED":
        return "\n".join(lines + ["Оценка пока недоступна. Размер выборки: 0."])
    if not payload.get("groups"):
        lines.append("Вероятностей: 0; доступных измерений для сегмента нет.")
    labels = (
        ("evaluated_predictions", "Прогнозов оценено"),
        ("forecast_coverage", "Покрытие"),
        ("binary_brier", "Brier (binary)"),
        ("binary_log_loss", "Log Loss"),
        ("calibration_ece", "Калибровка ECE"),
        ("candidate_hit_rate", "Hit rate кандидатов"),
        ("research_roi_fixed_unit", "Research ROI (1 unit)"),
    )
    for group in payload.get("groups", [])[:6]:
        lines.append(html.escape(" / ".join(group["dimensions"].values())))
        lines.append(f"Вероятностей: {group['sample_size']}")
        for key, label in labels:
            row = group["metrics"].get(key)
            if row:
                value = "—" if row["value"] is None else f"{row['value']:.4g}"
                lines.append(f"{label}: {value} (n={row['sample_size']})")
    lines.append("Исследовательские измерения; статистическая значимость не рассчитана.")
    if payload.get("has_more"):
        lines.append("Показана часть сегментов; полная выборка доступна через API.")
    return "\n".join(lines)


@router.message(Command("stats"))
async def stats_command(message: Message, context: AppContext) -> None:
    try:
        payload = await context.backend.evaluation_summary()
        text = render_stats(payload)
    except BackendClientError:
        text = SAFE_BACKEND_ERROR
    await context.transport.send_text(message.chat.id, text, reply_markup=stats_keyboard())


@router.message(Command("results"))
async def results_command(message: Message, context: AppContext) -> None:
    try:
        rows = await context.backend.recent_results()
        text = f"Последние результаты (n={len(rows)})"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=(
                            f"{row['status']} {row['regulation_home']}:"
                            f"{row['regulation_away']} / v{row['version']}"
                        ),
                        callback_data=f"result:{row['fixture_id']}",
                    )
                ]
                for row in rows[:8]
            ]
            + back_to_main_keyboard().inline_keyboard
        )
    except BackendClientError:
        text, keyboard = SAFE_BACKEND_ERROR, back_to_main_keyboard()
    await context.transport.send_text(message.chat.id, text, reply_markup=keyboard)


@router.message(Command("evaluate"))
async def evaluate_command(message: Message, context: AppContext) -> None:
    try:
        result = await context.backend.evaluate()
        text = f"Оценка поставлена в очередь: {result['evaluation_id']}"
    except BackendClientError:
        text = SAFE_BACKEND_ERROR
    await context.transport.send_text(message.chat.id, text, reply_markup=stats_keyboard())


@router.callback_query(
    F.data.startswith("stats:")
    | F.data.startswith("result:")
    | (F.data == "menu:stats")
    | (F.data == "results:recent")
)
async def stats_callback(callback: CallbackQuery, context: AppContext) -> None:
    await context.transport.answer_callback(callback.id)
    if callback.message is None:
        return
    try:
        value = callback.data or ""
        if value == "results:recent":
            await results_command(callback.message, context)
            return
        if value.startswith("result:"):
            fid = str(uuid.UUID(value.split(":")[1]))
            payload = await context.backend.result_detail(fid)
            rows = await context.backend.settlements(fid)
            latest = payload["latest"]
            text = (
                f"Результат v{latest['version']}: {html.escape(latest['status'])}\n"
                f"Основное время: {latest['regulation_home']}:{latest['regulation_away']}\n"
                f"Settlements (n={len(rows)})\n"
                + "\n".join(
                    f"{html.escape(row['role'])} / {html.escape(row['variant'])}: "
                    f"{html.escape(row['selection'])} → {html.escape(row['outcome'])}"
                    for row in rows[:24]
                )
            )
            keyboard = stats_keyboard()
        else:
            parts = value.split(":")
            period, facet = ("30d", "summary") if value == "menu:stats" else (parts[1], parts[2])
            if period not in ("7d", "30d", "all") or facet not in (
                "summary",
                "league",
                "market",
                "model",
                "odds_bucket",
            ):
                raise ValueError("invalid stats callback")
            payload = await context.backend.evaluation_summary(
                period=period, group_by=None if facet == "summary" else facet
            )
            text, keyboard = render_stats(payload, period), stats_keyboard(period)
    except (ValueError, IndexError, BackendClientError):
        text, keyboard = SAFE_BACKEND_ERROR, stats_keyboard()
    await context.transport.edit_text(
        callback.message.chat.id, callback.message.message_id, text, reply_markup=keyboard
    )
