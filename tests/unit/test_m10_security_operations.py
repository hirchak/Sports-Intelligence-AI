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
    assert "inline-redis-credential" not in redact_payload(
        "redis://:inline-redis-credential@host/0"
    )
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


def test_startup_validation_never_renders_input_credentials():
    secret = "synthetic-startup-credential-test-only"
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, production_like=True, log_level="DEBUG", sports_api_key=secret)
    rendered = str(error.value)
    assert secret not in rendered and "input_value" not in rendered
    assert "forbids DEBUG" in rendered


@pytest.mark.parametrize("kind", ["sports", "odds"])
@pytest.mark.parametrize("failure", ["timeout", "429", "503"])
async def test_runtime_factories_do_not_hide_physical_retries(kind, failure):
    from datetime import date

    import httpx

    from sports_intelligence.providers.errors import ProviderError
    from sports_intelligence.providers.odds.factory import build_odds_provider

    settings = Settings(
        _env_file=None,
        app_env="sandbox",
        sports_provider="api_football",
        sports_api_key="synthetic-physical-attempt-test",
        odds_provider="the_odds_api",
        odds_api_key="synthetic-physical-attempt-test",
    )
    provider = (
        build_sports_provider(settings) if kind == "sports" else build_odds_provider(settings)
    )
    await provider._client.aclose()
    requests = []

    def handle(request):
        requests.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("synthetic timeout", request=request)
        return httpx.Response(int(failure), json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider._client = client
        with pytest.raises(ProviderError):
            if kind == "sports":
                await provider.get_fixtures_by_date(date(2026, 8, 21), "UTC")
            else:
                await provider.fetch_event_odds(
                    sport_key="soccer_epl", event_id="event", markets=["h2h"], regions=["eu"]
                )
    assert len(requests) == 1


def test_operational_schedule_times_explicit_and_validated():
    from sports_intelligence.workers.celery_app import create_celery_app

    settings = Settings(
        _env_file=None,
        improvement_schedule_enabled=True,
        improvement_schedule_day_of_week="fri",
        improvement_schedule_hour=17,
        improvement_schedule_minute=35,
    )
    schedule = create_celery_app(settings).conf.beat_schedule["improvements.weekly"]["schedule"]
    assert schedule.day_of_week == {5} and schedule.hour == {17} and schedule.minute == {35}
    with pytest.raises(ValidationError):
        Settings(_env_file=None, scheduler_discovery_morning_hour=24)


async def test_odds_event_observers_are_isolated_between_concurrent_tasks():
    import asyncio

    import httpx

    from sports_intelligence.providers.odds.factory import TheOddsApiProvider

    entered = 0
    ready = asyncio.Event()
    observed = []

    async def handle(request):
        nonlocal entered
        entered += 1
        if entered == 2:
            ready.set()
        await ready.wait()
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = TheOddsApiProvider(
            "synthetic-concurrent-observers",
            "https://synthetic.invalid",
            client=client,
            max_attempts=1,
        )

        async def request(label):
            async def observe(started, response, error):
                observed.append((label, response.request.url.params["scope"]))

            provider.event_observer = observe
            try:
                await provider._get_json_any("/sports/test/events", {"scope": label})
            finally:
                provider.event_observer = None

        await asyncio.gather(request("a"), request("b"))
        assert sorted(observed) == [("a", "a"), ("b", "b")]
        assert provider.event_observer is None
