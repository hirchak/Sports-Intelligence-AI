from __future__ import annotations

import logging

import httpx
import pytest

from sports_intelligence.providers.errors import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderServerError,
    ProviderTimeoutError,
    ProviderTransportError,
)
from sports_intelligence.providers.odds.factory import TheOddsApiProvider


def _provider(transport: httpx.MockTransport) -> TheOddsApiProvider:
    client = httpx.AsyncClient(timeout=1.0, transport=transport)
    return TheOddsApiProvider(
        api_key="secret-key-value",
        base_url="https://example.test/v4",
        client=client,
        max_attempts=2,
        backoff_seconds=0.001,
        timeout_seconds=1.0,
    )


@pytest.mark.asyncio
async def test_theoddsapi_401_raises_auth_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "unauthorized"})

    p = _provider(httpx.MockTransport(handler))
    with pytest.raises(ProviderAuthError):
        await p.fetch_odds(fixture_id="fixture-1", markets=["h2h"], regions=["eu"])
    await p.aclose()


@pytest.mark.asyncio
async def test_theoddsapi_429_raises_rate_limit_after_retries() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(429, json={"message": "rate-limited"})

    p = _provider(httpx.MockTransport(handler))
    with pytest.raises(ProviderRateLimitError):
        await p.fetch_odds(fixture_id="fixture-1", markets=["h2h"], regions=["eu"])
    # 1 attempt (configured max_attempts) — retry policy applied, 1 call.
    assert len(calls) == 2
    await p.aclose()


@pytest.mark.asyncio
async def test_theoddsapi_500_raises_server_error_after_retries() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "boom"})

    p = _provider(httpx.MockTransport(handler))
    with pytest.raises(ProviderServerError):
        await p.fetch_odds(fixture_id="fixture-1", markets=["h2h"], regions=["eu"])
    await p.aclose()


@pytest.mark.asyncio
async def test_theoddsapi_timeout_raises_timeout_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("boom")

    p = _provider(httpx.MockTransport(handler))
    with pytest.raises(ProviderTimeoutError):
        await p.fetch_odds(fixture_id="fixture-1", markets=["h2h"], regions=["eu"])
    await p.aclose()


@pytest.mark.asyncio
async def test_theoddsapi_connect_error_raises_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    p = _provider(httpx.MockTransport(handler))
    with pytest.raises(ProviderTransportError):
        await p.fetch_odds(fixture_id="fixture-1", markets=["h2h"], regions=["eu"])
    await p.aclose()


@pytest.mark.asyncio
async def test_theoddsapi_malformed_json_raises_response_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json at all")

    p = _provider(httpx.MockTransport(handler))
    with pytest.raises(ProviderResponseError):
        await p.fetch_odds(fixture_id="fixture-1", markets=["h2h"], regions=["eu"])
    await p.aclose()


@pytest.mark.asyncio
async def test_theoddsapi_does_not_leak_api_key_in_logs(caplog) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "evt-1",
                "home_team": "Arsenal",
                "away_team": "Coventry",
                "last_update": "2026-08-21T10:00:00Z",
                "bookmakers": [
                    {
                        "key": "sportsbook",
                        "title": "Sportsbook",
                        "last_update": "2026-08-21T10:00:00Z",
                        "markets": [
                            {
                                "key": "h2h",
                                "outcomes": [
                                    {"name": "Arsenal", "price": 2.10},
                                    {"name": "Draw", "price": 3.40},
                                    {"name": "Coventry", "price": 3.60},
                                ],
                            }
                        ],
                    }
                ],
            },
        )

    p = _provider(httpx.MockTransport(handler))
    with caplog.at_level(logging.DEBUG):
        result = await p.fetch_odds(fixture_id="fixture-1", markets=["h2h"], regions=["eu"])
    assert result.prices
    await p.aclose()
    # The apiKey value must never appear in any captured log record.
    for record in caplog.records:
        assert "secret-key-value" not in record.getMessage()
        assert "secret-key-value" not in str(record.__dict__)
