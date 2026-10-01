from __future__ import annotations

import html
import uuid

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from sports_intelligence.bot.backend_client import BackendClientError
from sports_intelligence.bot.context import AppContext
from sports_intelligence.bot.menu import back_to_main_keyboard
from sports_intelligence.bot.strings import SAFE_BACKEND_ERROR
from sports_intelligence.schemas.predictions import PredictionDetail

router = Router(name="m7_predictions")


def fixture_prediction_keyboard(fixture_id: uuid.UUID) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Прогноз", callback_data=f"predfx:{fixture_id}")],
            [InlineKeyboardButton(text="Запросить анализ", callback_data=f"analyze:{fixture_id}")],
            *back_to_main_keyboard().inline_keyboard,
        ]
    )


def prediction_keyboard(run: PredictionDetail) -> InlineKeyboardMarkup:
    # Rerun token is derived from persisted run ID; repeated taps on the same screen
    # reuse the same new run. A later new-run screen permits the next explicit rerun.
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=title, callback_data=f"pred:{view}:{run.id}")]
            for title, view in (
                ("Кандидаты", "top"),
                ("Все вероятности", "table"),
                ("Почему?", "why"),
                ("Риски", "risks"),
                ("Модель", "model"),
                ("Повторить прогноз", "rerun"),
            )
        ]
        + back_to_main_keyboard().inline_keyboard
    )


def render_prediction(run: PredictionDetail, view: str = "top") -> str:
    escape = html.escape
    title = f"<b>{escape(run.home_team or '—')} — {escape(run.away_team or '—')}</b>"
    meta = (
        f"{run.forecast_phase} / {run.role.value}\n"
        f"As of: {run.as_of.isoformat()}\nКачество данных: {run.data_quality:.0%}"
    )
    lines = [title, meta]
    if run.status == "ABSTAINED":
        lines += [
            "Прогноз не сформирован: недостаточно оснований.",
            escape(run.abstain_reason or "—"),
        ]
    elif run.status == "FAILED":
        lines += ["Прогноз не сформирован: ошибка обработки.", escape(run.error_code or "—")]
    elif run.status != "SUCCEEDED":
        lines += ["Прогноз в очереди или обрабатывается."]
    elif view == "table":
        lines += ["Все вероятности"] + [
            f"{p.selection.value}: {p.model_probability:.1%}" for p in run.probabilities
        ]
    elif view == "why":
        output = run.output or {}
        lines += [escape(str(output.get("summary", ""))[:700])]
        for key, label in (("evidence_for", "За"), ("evidence_against", "Против")):
            lines.append(label)
            for ref in output.get(key, [])[:4]:
                lines.append(f"• {escape(ref['path'])}: {escape(ref['observation'][:160])}")
    elif view == "risks":
        output = run.output or {}
        lines += ["Риски"] + [escape(r[:200]) for r in output.get("risk_flags", [])[:8]]
        confidence = output.get("confidence", {})
        lines.append(
            "Уверенность — диагностика, не вероятность: " + escape(confidence.get("level", "—"))
        )
        lines += [escape(r[:180]) for r in confidence.get("limitations", [])[:4]]
    elif view == "model":
        lines += [
            f"Provider: {escape(run.actual_provider or '—')}; "
            f"model: {escape(run.actual_model or '—')}",
            f"Вариант: {run.variant.value}",
            f"Prompt: {escape(run.prompt_name)} {escape(run.prompt_version)}",
            f"Prompt SHA-256: {run.prompt_hash}",
            f"Config SHA-256: {run.model_config_hash or '—'}",
            f"Context: {run.context_hash}",
            f"Latency: {run.latency_ms} ms; tokens: {run.input_tokens}/{run.output_tokens}",
        ]
    else:
        candidates = (
            [c for c in run.candidates if c.displayed] if run.role.value == "PRIMARY" else []
        )
        if run.role.value == "CHALLENGER":
            lines.append("Теневой прогноз; не используется как основной.")
        elif not candidates:
            lines.append("NO HIGH-CONFIDENCE OPPORTUNITY — нет кандидатов по текущим порогам.")
        for c in candidates[:3]:
            lines.append(
                f"{c.rank}. {c.selection.value}: {c.model_probability:.1%}\n"
                f"Коэффициент: {c.captured_odds}; рынок: {c.market_probability:.1%}\n"
                f"Edge: {c.edge:+.1%}; EV: {c.expected_value:+.1%}"
            )
    return "\n\n".join(lines)


@router.message(Command("predictions"))
async def predictions_command(message: Message, context: AppContext) -> None:
    try:
        runs = await context.backend.list_predictions(limit=8)
        if not runs:
            text, keyboard = "Прогнозов пока нет.", back_to_main_keyboard()
        else:
            text = "Последние основные прогнозы"
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=f"{r.forecast_phase} / {r.status} / {str(r.fixture_id)[:8]}",
                            callback_data=f"pred:top:{r.id}",
                        )
                    ]
                    for r in runs
                ]
                + back_to_main_keyboard().inline_keyboard
            )
    except BackendClientError:
        text, keyboard = SAFE_BACKEND_ERROR, back_to_main_keyboard()
    await context.transport.send_text(message.chat.id, text, reply_markup=keyboard)


@router.message(Command("analyze"))
async def analyze_command(message: Message, command: CommandObject, context: AppContext) -> None:
    try:
        fixture_id = uuid.UUID((command.args or "").strip())
    except ValueError:
        await context.transport.send_text(
            message.chat.id, "Формат: /analyze <fixture UUID>", reply_markup=back_to_main_keyboard()
        )
        return
    try:
        result = await context.backend.analyze_fixture(str(fixture_id))
        text = (
            f"Анализ поставлен в очередь. Job: {result.job_id}\n"
            f"Повторный запрос: {result.already_queued}"
        )
    except BackendClientError:
        text = SAFE_BACKEND_ERROR
    await context.transport.send_text(message.chat.id, text, reply_markup=back_to_main_keyboard())


@router.callback_query(F.data == "menu:predictions")
async def predictions_menu(callback: CallbackQuery, context: AppContext) -> None:
    await context.transport.answer_callback(callback.id)
    if callback.message:
        await predictions_command(callback.message, context)


@router.callback_query(
    F.data.startswith("predfx:") | F.data.startswith("analyze:") | F.data.startswith("pred:")
)
async def prediction_callback(callback: CallbackQuery, context: AppContext) -> None:
    await context.transport.answer_callback(callback.id)
    if callback.message is None:
        return
    text, keyboard = "Неизвестное действие.", back_to_main_keyboard()
    try:
        parts = (callback.data or "").split(":")
        if parts[0] in ("predfx", "analyze") and len(parts) == 2:
            fixture_id = uuid.UUID(parts[1])
            if parts[0] == "analyze":
                result = await context.backend.analyze_fixture(str(fixture_id))
                text = f"Анализ поставлен в очередь. Job: {result.job_id}"
            else:
                runs = await context.backend.list_predictions(fixture_id=str(fixture_id), limit=1)
                if runs:
                    run = await context.backend.get_prediction(str(runs[0].id))
                    text, keyboard = render_prediction(run), prediction_keyboard(run)
                else:
                    text = "Прогнозов пока нет."
        elif len(parts) == 3 and parts[1] in ("top", "table", "why", "risks", "model", "rerun"):
            run_id = uuid.UUID(parts[2])
            run = await context.backend.get_prediction(str(run_id))
            if parts[1] == "rerun":
                token = uuid.uuid5(run.id, "telegram_explicit_rerun")
                result = await context.backend.analyze_fixture(
                    str(run.fixture_id),
                    context_id=run.match_context_id,
                    phase=run.forecast_phase,
                    role=run.role,
                    variant=run.variant,
                    rerun_key=token,
                )
                text = f"Новый прогноз поставлен в очередь. Run: {result.run_id}"
            else:
                text, keyboard = render_prediction(run, parts[1]), prediction_keyboard(run)
    except (ValueError, BackendClientError):
        text = SAFE_BACKEND_ERROR
    try:
        await context.transport.edit_text(
            callback.message.chat.id, callback.message.message_id, text, reply_markup=keyboard
        )
    except Exception:
        await context.transport.send_text(callback.message.chat.id, text, reply_markup=keyboard)
