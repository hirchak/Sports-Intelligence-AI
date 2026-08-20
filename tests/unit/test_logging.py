from __future__ import annotations

import io
import json
import logging

from sports_intelligence.core.logging import (
    clear_log_context,
    set_log_context,
    setup_logging,
)


def test_json_logs_are_valid_json_with_standard_fields() -> None:
    buffer = io.StringIO()
    setup_logging("INFO", stream=buffer)
    logging.getLogger("test.logger").info("hello world")
    payload = json.loads(buffer.getvalue())
    assert payload["message"] == "hello world"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.logger"
    assert "timestamp" in payload


def test_log_context_fields_are_included() -> None:
    buffer = io.StringIO()
    setup_logging("INFO", stream=buffer)
    set_log_context(correlation_id="corr-123", job_id="job-456")
    logging.getLogger("test.logger").warning("contextual message")
    clear_log_context()
    payload = json.loads(buffer.getvalue())
    assert payload["correlation_id"] == "corr-123"
    assert payload["job_id"] == "job-456"


def test_cleared_context_is_not_included() -> None:
    buffer = io.StringIO()
    setup_logging("INFO", stream=buffer)
    set_log_context(correlation_id="corr-123")
    clear_log_context()
    logging.getLogger("test.logger").info("plain message")
    payload = json.loads(buffer.getvalue())
    assert "correlation_id" not in payload
