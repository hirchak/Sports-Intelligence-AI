from __future__ import annotations

import io
import json
import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from sports_intelligence.api.app import create_app
from sports_intelligence.core.config import Settings
from sports_intelligence.core.logging import setup_logging
from sports_intelligence.core.redaction import redact_payload, register_secrets
from sports_intelligence.providers.errors import ProviderConfigError
from sports_intelligence.providers.sports.factory import build_sports_provider
from sports_intelligence.workers.observability import task_finished, task_started


@pytest.mark.parametrize("env", ["sandbox", "live_local"])
def test_non_mock_sports_cannot_return_synthetic_data(env):
    with pytest.raises(ProviderConfigError, match="Mock sports provider refused"):
        build_sports_provider(Settings(_env_file=None, app_env=env, sports_provider="mock"))


def test_production_like_debug_refused_and_allowlist_ids_validated():
    with pytest.raises(ValidationError, match="forbids DEBUG"):
        Settings(_env_file=None, production_like=True, log_level="DEBUG")
    with pytest.raises(ValidationError, match="positive"):
        Settings(_env_file=None, telegram_allowed_user_ids=[-1])


async def test_bot_empty_allowlist_refuses_start_before_any_network(monkeypatch):
    from sports_intelligence.bot import __main__ as bot

    monkeypatch.setattr(
        bot,
        "get_settings",
        lambda: Settings(
            _env_file=None, telegram_bot_token="test-token", telegram_allowed_user_ids=[]
        ),
    )
    with pytest.raises(SystemExit):
        await bot.run()


def test_exception_header_query_and_registered_secret_redaction():
    secret = "synthetic-credential-redaction-only"
    register_secrets({"sports_api_key": secret})
    stream = io.StringIO()
    setup_logging(stream=stream)
    try:
        raise ValueError(f"provider failed {secret} https://example.invalid?apiKey=hidden-query")
    except ValueError:
        logging.getLogger("test").exception("Authorization: Bearer hidden-header")
    rendered = stream.getvalue()
    assert not any(value in rendered for value in (secret, "hidden-query", "hidden-header"))
    assert json.loads(rendered)["exc_info"]
    sanitized = redact_payload({"input_tokens": 123, "api_key": "never-display", "password": "bad"})
    assert sanitized == {"input_tokens": 123, "api_key": "[REDACTED]", "password": "[REDACTED]"}


def test_worker_lifecycle_ids_duration_and_context_cleanup():
    stream = io.StringIO()
    setup_logging(stream=stream)
    task_started(
        "task-a",
        SimpleNamespace(name="experiment.replay_batch"),
        {"job_id": "job-a", "run_id": "run-a", "api_key": "must-not-log"},
    )
    task_finished("task-a", "SUCCESS")
    logging.getLogger("test").info("outside task")
    start, end, outside = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert start["experiment_run_id"] == "run-a" and start["job_id"] == "job-a"
    assert end["duration_ms"] >= 0 and end["status"] == "SUCCESS"
    assert "task_id" not in outside and "must-not-log" not in stream.getvalue()


def test_correlation_safe_docs_disabled_and_no_cors(monkeypatch):
    # No startup or dependencies required for process-health/config transport acceptance.
    app = create_app(Settings(_env_file=None, production_like=True))
    stream = io.StringIO()
    setup_logging(stream=stream)
    client = TestClient(app)
    first = client.get("/health?token=untrusted-input", headers={"X-Correlation-ID": "safe-id"})
    assert first.status_code == 200 and first.headers["x-correlation-id"] == "safe-id"
    assert client.get("/docs").status_code == 404
    assert "access-control-allow-origin" not in first.headers
    assert "untrusted-input" not in stream.getvalue()
    assert all(
        json.loads(line)["correlation_id"] == "safe-id"
        for line in stream.getvalue().splitlines()[:1]
    )
    assert (
        client.get("/health", headers={"X-Correlation-ID": "a" * 100}).headers["x-correlation-id"]
        != "a" * 100
    )
