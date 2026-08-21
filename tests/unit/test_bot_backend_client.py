from __future__ import annotations

from datetime import date

import httpx
import pytest

from sports_intelligence.bot.backend_client import (
    BackendClient,
    BackendPayloadError,
    BackendResponseError,
    BackendUnavailableError,
    DiscoverResult,
    FixtureView,
    HealthStatus,
)

FIXTURE_UUID = "11111111-2222-3333-4444-555555555555"
JOB_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

FIXTURE_JSON = {
    "id": FIXTURE_UUID,
    "league_slug": "premier-league",
    "home_team": "Arsenal",
    "away_team": None,
    "kickoff_at": "2026-08-21T18:30:00Z",
    "venue": "Emirates",
    "round": None,
    "status": "NS",
}


def _json_response(status: int, payload: object) -> httpx.Response:
    return httpx.Response(status, json=payload, headers={"content-type": "application/json"})


def _client(handler: httpx.MockTransportHandler) -> BackendClient:
    return BackendClient(
        base_url="http://internal-backend:8000",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


async def test_health_reports_all_components_ok() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return _json_response(200, {"status": "ok"})
        return _json_response(200, {"status": "ready", "checks": {"database": "ok", "redis": "ok"}})

    client = _client(handler)
    status = await client.health()
    assert status == HealthStatus(api=True, database=True, redis=True)


async def test_health_reports_degraded_components_from_readiness() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return _json_response(200, {"status": "ok"})
        return _json_response(
            503, {"status": "not_ready", "checks": {"database": "ok", "redis": "unavailable"}}
        )

    status = await _client(handler).health()
    assert status == HealthStatus(api=True, database=True, redis=False)


async def test_health_api_unreachable_marks_api_down() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    status = await _client(handler).health()
    assert status == HealthStatus(api=False)


async def test_health_ready_probe_failure_keeps_components_unknown() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return _json_response(200, {"status": "ok"})
        raise httpx.ConnectError("connection refused")

    status = await _client(handler).health()
    assert status == HealthStatus(api=True, database=None, redis=None)


async def test_list_fixtures_parses_nullable_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("date") == "2026-08-21"
        return _json_response(200, [FIXTURE_JSON])

    fixtures = await _client(handler).list_fixtures(fixture_date=date(2026, 8, 21))
    if fixtures is None:
        raise AssertionError("expected fixtures")
    fixture = fixtures[0]
    assert fixture.id.hex == FIXTURE_UUID.replace("-", "")
    assert fixture.home_team == "Arsenal"
    assert fixture.away_team is None
    assert fixture.kickoff_at.isoformat() == "2026-08-21T18:30:00+00:00"


async def test_list_fixtures_rejects_non_list_payload() -> None:
    client = _client(lambda request: _json_response(200, {"fixtures": []}))
    with pytest.raises(BackendPayloadError):
        await client.list_fixtures()


async def test_list_fixtures_rejects_malformed_entries() -> None:
    client = _client(lambda request: _json_response(200, [{"id": "not-a-uuid"}]))
    with pytest.raises(BackendPayloadError):
        await client.list_fixtures()


async def test_backend_500_raises_bot_safe_response_error() -> None:
    client = _client(lambda request: _json_response(500, {"detail": "internal crash"}))
    with pytest.raises(BackendResponseError) as exc_info:
        await client.list_fixtures()
    error = exc_info.value
    assert error.status_code == 500
    assert "internal crash" not in str(error)
    assert "internal-backend" not in str(error)


async def test_backend_timeout_raises_unavailable_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("read timed out")

    client = _client(handler)
    with pytest.raises(BackendUnavailableError) as exc_info:
        await client.list_fixtures()
    assert "timed out" not in str(exc_info.value)


async def test_get_fixture_returns_none_for_404() -> None:
    client = _client(lambda request: _json_response(404, {"detail": "fixture not found"}))
    assert await client.get_fixture(FIXTURE_UUID) is None


async def test_get_fixture_parses_detail() -> None:
    client = _client(lambda request: _json_response(200, FIXTURE_JSON))
    fixture = await client.get_fixture(FIXTURE_UUID)
    assert isinstance(fixture, FixtureView)
    assert fixture.venue == "Emirates"


async def test_get_fixture_malformed_payload_raises() -> None:
    client = _client(lambda request: _json_response(200, {"wrong": True}))
    with pytest.raises(BackendPayloadError):
        await client.get_fixture(FIXTURE_UUID)


async def test_discover_returns_typed_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/jobs/discover"
        assert request.content  # body present
        return _json_response(
            200,
            {
                "job_id": JOB_UUID,
                "idempotency_key": "discover:mock:2026-08-21:v1:Europe/Warsaw",
                "status": "PENDING",
                "already_queued": False,
            },
        )

    result = await _client(handler).discover(fixture_date=date(2026, 8, 21))
    assert isinstance(result, DiscoverResult)
    assert str(result.job_id) == JOB_UUID
    assert result.already_queued is False


async def test_discover_502_raises_bot_safe_error() -> None:
    client = _client(lambda request: _json_response(502, {"detail": {"secret": "x"}}))
    with pytest.raises(BackendResponseError) as exc_info:
        await client.discover(fixture_date=date(2026, 8, 21))
    assert "secret" not in str(exc_info.value)


async def test_malformed_json_raises_payload_error() -> None:
    client = _client(lambda request: httpx.Response(200, content=b"not json"))
    with pytest.raises(BackendPayloadError):
        await client.list_fixtures()
