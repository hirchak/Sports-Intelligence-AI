from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest

from sports_intelligence.core.config import Settings
from sports_intelligence.providers.errors import ProviderConfigError
from sports_intelligence.providers.sports.api_football import ApiFootballProvider
from sports_intelligence.providers.sports.factory import build_sports_provider
from sports_intelligence.providers.sports.mock import MockSportsDataProvider

API_KEY = "test-key-123"


def test_unknown_provider_fails_fast() -> None:
    settings = Settings(
        _env_file=None, app_env="mock", sports_provider="api_footbal", sports_api_key="x"
    )
    with pytest.raises(ProviderConfigError):
        build_sports_provider(settings)


def test_empty_provider_fails_fast() -> None:
    settings = Settings(_env_file=None, app_env="mock", sports_provider="")
    with pytest.raises(ProviderConfigError):
        build_sports_provider(settings)


def test_explicit_mock_returns_mock_provider() -> None:
    settings = Settings(_env_file=None, app_env="mock", sports_provider="mock")
    assert isinstance(build_sports_provider(settings), MockSportsDataProvider)


def test_api_football_returns_real_adapter() -> None:
    settings = Settings(
        _env_file=None,
        app_env="mock",
        sports_provider="api_football",
        sports_api_key=API_KEY,
    )
    provider = build_sports_provider(settings)
    assert isinstance(provider, ApiFootballProvider)
    asyncio.run(provider.aclose())


async def test_retrieved_at_is_after_final_response_with_retry() -> None:
    state = {"calls": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        if state["calls"] == 1:
            await asyncio.sleep(0.15)
            return httpx.Response(500, json={"message": "boom"})
        await asyncio.sleep(0.05)
        return httpx.Response(
            200,
            json={
                "get": "fixtures",
                "errors": [],
                "results": 0,
                "paging": {"current": 1, "total": 1},
                "response": [],
            },
            headers={"content-type": "application/json"},
        )

    provider = ApiFootballProvider(
        api_key=API_KEY,
        base_url="https://v3.football.api-sports.io",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        max_attempts=3,
        backoff_seconds=0.01,
    )

    started_at = datetime.now(UTC)
    result = await provider.get_fixtures_by_date(date(2026, 8, 21), timezone_name="Europe/Warsaw")

    assert state["calls"] == 2
    assert result.metadata.retrieved_at >= started_at + timedelta(seconds=0.15)


async def test_adapter_sends_timezone_parameter() -> None:
    captured: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.url.params))
        return httpx.Response(
            200,
            json={
                "get": "fixtures",
                "errors": [],
                "results": 0,
                "paging": {"current": 1, "total": 1},
                "response": [],
            },
            headers={"content-type": "application/json"},
        )

    provider = ApiFootballProvider(
        api_key=API_KEY,
        base_url="https://v3.football.api-sports.io",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        max_attempts=1,
        backoff_seconds=0.0,
    )

    await provider.get_fixtures_by_date(date(2026, 8, 21), timezone_name="Europe/Warsaw")

    assert captured["date"] == "2026-08-21"
    assert captured["timezone"] == "Europe/Warsaw"
