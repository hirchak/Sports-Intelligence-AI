from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, TextIO

LOG_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar("sports_log_context", default=None)

CONTEXT_FIELD_NAMES = ("correlation_id", "job_id", "fixture_id", "prediction_run_id")


def _current_context() -> dict[str, Any]:
    return LOG_CONTEXT.get() or {}


class LogContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in _current_context().items():
            setattr(record, key, value)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field_name in CONTEXT_FIELD_NAMES:
            value = getattr(record, field_name, None)
            if value is not None:
                payload[field_name] = value
        if record.exc_info is not None:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO", stream: TextIO | None = None) -> None:
    handler = logging.StreamHandler(stream if stream is not None else sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(LogContextFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())


def set_log_context(**fields: Any) -> None:
    LOG_CONTEXT.set({**_current_context(), **fields})


def clear_log_context() -> None:
    LOG_CONTEXT.set(None)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
