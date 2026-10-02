"""Celery logging hooks; identifiers only, no task payloads or credentials."""

from __future__ import annotations

import logging
import time
from typing import Any

from celery import signals

from sports_intelligence.core.config import get_settings
from sports_intelligence.core.logging import (
    clear_log_context,
    get_logger,
    set_log_context,
    setup_logging,
)
from sports_intelligence.core.redaction import register_secrets

logger = get_logger(__name__)
_started: dict[str, float] = {}


@signals.setup_logging.connect  # type: ignore[untyped-decorator]
def configure_worker_logging(loglevel: int = logging.INFO, **_: Any) -> None:
    register_secrets(get_settings().model_dump())
    setup_logging(logging.getLevelName(loglevel))


@signals.task_prerun.connect  # type: ignore[untyped-decorator]
def task_started(task_id: str, task: Any, kwargs: dict[str, Any] | None = None, **_: Any) -> None:
    clear_log_context()
    values = kwargs or {}
    fields = {
        k: str(values[k]) for k in ("job_id", "fixture_id", "correlation_id") if values.get(k)
    }
    if values.get("run_id"):
        key = "experiment_run_id" if task.name.startswith("experiment.") else "prediction_run_id"
        fields[key] = str(values["run_id"])
    set_log_context(task_id=task_id, task_name=task.name, **fields)
    _started[task_id] = time.monotonic()
    logger.info("task started")


@signals.task_postrun.connect  # type: ignore[untyped-decorator]
def task_finished(task_id: str, state: str, **_: Any) -> None:
    started = _started.pop(task_id, time.monotonic())
    logger.info(
        "task completed",
        extra={"status": state, "duration_ms": round((time.monotonic() - started) * 1000, 2)},
    )
    clear_log_context()
