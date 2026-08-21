from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from sports_intelligence.providers.errors import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from sports_intelligence.providers.sports.api_football import ApiFootballProvider

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "provider" / "api_football"
RECORDED = json.loads((FIXTURES_DIR / "fixtures_by_date.json").read_text())
API_KEY = "secret-key-123456"


def make_provider(
    handler: httpx.MockTransport,
    api_key: str = API_KEY,
) -> ApiFootballProvider:
    return ApiFootballProvider(
        api_key=api_key,
        base_url="https://v3.football.api-sports.io",
        client=httpx.AsyncClient(transport=handler),
        max_attempts=3,
        backoff_seconds=0.01,
    )


def _recorded_handler(
    payload: object = RECORDED, status: int = 200, headers: dict[str, str] | None = None
):
    response_headers = {"content-type": "application/json"}
    if headers:
        response_headers.update(headers)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload, headers=response_headers)

    return handler


async def test_fixtures_by_date_returns_normalized_dtos() -> None:
    transport = httpx.MockTransport(_recorded_handler())
    provider = make_provider(transport)

    result = await provider.get_fixtures_by_date(date(2026, 8, 21))

    assert len(result.fixtures) == 4
    first = result.fixtures[0]
    assert first.provider_fixture_id == 100001
    assert first.provider_league_id == 39
    assert first.home_team_name == "FC Mockton"
    assert first.away_team_name == "Sporting Placeholder"
    assert first.kickoff_utc == datetime(2026, 8, 21, 19, 0, tzinfo=UTC)
    assert first.status_short == "NS"
    assert first.venue == "Mock Arena"
    assert first.round == "Regular Season - 2"


async def test_home_and_away_identity_is_preserved() -> None:
    transport = httpx.MockTransport(_recorded_handler())
    provider = make_provider(transport)

    result = await provider.get_fixtures_by_date(date(2026, 8, 21))

    fixture = result.fixtures[0]
    assert fixture.provider_home_team_id == 2001
    assert fixture.provider_away_team_id == 2002
    assert fixture.home_team_name != fixture.away_team_name


async def test_missing_optional_fields_become_none() -> None:
    transport = httpx.MockTransport(_recorded_handler())
    provider = make_provider(transport)

    result = await provider.get_fixtures_by_date(date(2026, 8, 21))

    nulled = result.fixtures[1]
    assert nulled.venue is None
    assert nulled.round is None
    assert nulled.provider_season is None


async def test_offset_kickoff_is_normalized_to_utc() -> None:
    transport = httpx.MockTransport(_recorded_handler())
    provider = make_provider(transport)

    result = await provider.get_fixtures_by_date(date(2026, 8, 21))

    offset = result.fixtures[3]
    assert offset.kickoff_utc == datetime(2026, 8, 21, 17, 0, tzinfo=UTC)


async def test_auth_error_is_not_retried() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(403, json={"message": "forbidden"})

    provider = make_provider(httpx.MockTransport(handler))

    with pytest.raises(ProviderAuthError):
        await provider.get_fixtures_by_date(date(2026, 8, 21))
    assert len(calls) == 1


async def test_transient_server_error_retries_then_succeeds() -> None:
    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        if state["calls"] == 1:
            return httpx.Response(500, json={"message": "boom"})
        return httpx.Response(200, json=RECORDED, headers={"content-type": "application/json"})

    provider = make_provider(httpx.MockTransport(handler))

    result = await provider.get_fixtures_by_date(date(2026, 8, 21))
    assert state["calls"] == 2
    assert len(result.fixtures) == 4


async def test_persistent_rate_limit_raises_after_bounded_retries() -> None:
    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        return httpx.Response(
            429, json={"message": "too many"}, headers={"x-ratelimit-requests-remaining": "0"}
        )

    provider = make_provider(httpx.MockTransport(handler))

    with pytest.raises(ProviderRateLimitError):
        await provider.get_fixtures_by_date(date(2026, 8, 21))
    assert state["calls"] == 3


async def test_timeout_raises_normalized_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    provider = make_provider(httpx.MockTransport(handler))

    with pytest.raises(ProviderTimeoutError):
        await provider.get_fixtures_by_date(date(2026, 8, 21))


async def test_malformed_payload_raises_response_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="this is not json")

    provider = make_provider(httpx.MockTransport(handler))

    with pytest.raises(ProviderResponseError):
        await provider.get_fixtures_by_date(date(2026, 8, 21))


async def test_api_key_is_sent_but_never_leaked(caplog: pytest.LogCaptureFixture) -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("x-apisports-key", "")
        return httpx.Response(200, json=RECORDED, headers={"content-type": "application/json"})

    provider = make_provider(httpx.MockTransport(handler), api_key=API_KEY)
    await provider.get_fixtures_by_date(date(2026, 8, 21))
    assert captured["auth"] == API_KEY

    with pytest.raises(ProviderAuthError):
        await make_provider(
            httpx.MockTransport(lambda request: httpx.Response(403, json={"error": "bad key"})),
            api_key=API_KEY,
        ).get_fixtures_by_date(date(2026, 8, 21))

    assert API_KEY not in caplog.text


async def test_response_metadata_carries_rate_limit_and_evidence() -> None:
    transport = httpx.MockTransport(
        _recorded_handler(headers={"x-ratelimit-requests-remaining": "88"})
    )
    provider = make_provider(transport)

    result = await provider.get_fixtures_by_date(date(2026, 8, 21))

    assert result.metadata.provider == "api_football"
    assert result.metadata.endpoint_family == "fixtures_by_date"
    assert result.metadata.request_fingerprint == "api_football:fixtures_by_date:date=2026-08-21"
    assert result.metadata.rate_limit_remaining == 88
    assert result.raw_payload is not None
    assert result.raw_payload["results"] == 4


async def test_single_request_serves_all_fixtures_no_n_plus_one() -> None:
    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        return httpx.Response(200, json=RECORDED, headers={"content-type": "application/json"})

    provider = make_provider(httpx.MockTransport(handler))

    result = await provider.get_fixtures_by_date(date(2026, 8, 21))

    assert len(result.fixtures) == 4
    assert state["calls"] == 1
