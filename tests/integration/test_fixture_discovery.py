from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import date
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from sports_intelligence.api.app import create_app
from sports_intelligence.core.config import Settings
from sports_intelligence.core.league_config import LeagueConfig, LeagueConfigEntry
from sports_intelligence.db.models import (
    Fixture,
    Job,
    League,
    ProviderEntityId,
    RawProviderPayload,
    Season,
    Team,
)
from sports_intelligence.pipelines.discover_fixtures import FixtureDiscoveryService
from sports_intelligence.providers.sports.api_football import ApiFootballProvider
from sports_intelligence.providers.sports.mock import MockSportsDataProvider

pytestmark = pytest.mark.integration

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "")

requires_services = pytest.mark.skipif(
    not (TEST_DATABASE_URL and TEST_REDIS_URL),
    reason="TEST_DATABASE_URL and TEST_REDIS_URL are required",
)

pytestmark = [pytest.mark.integration, requires_services]

_DISCOVERY_TABLES = (
    "jobs",
    "raw_provider_payloads",
    "provider_entity_ids",
    "fixtures",
    "teams",
    "seasons",
    "leagues",
)


@pytest.fixture(scope="module", autouse=True)
def clean_discovery_tables() -> None:
    if TEST_DATABASE_URL:
        asyncio.run(_truncate())


async def _truncate() -> None:
    from sqlalchemy import text

    from sports_intelligence.db.session import create_engine

    engine = create_engine(TEST_DATABASE_URL)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("TRUNCATE " + ", ".join(_DISCOVERY_TABLES) + " RESTART IDENTITY CASCADE")
            )
    finally:
        await engine.dispose()


FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "provider" / "api_football"
RECORDED = json.loads((FIXTURES_DIR / "fixtures_by_date.json").read_text())

CONFIG = LeagueConfig(
    leagues=[
        LeagueConfigEntry(
            slug="premier-league",
            name="Premier League",
            country="England",
            enabled=True,
            provider_ids={"api_football": 39},
        ),
        LeagueConfigEntry(
            slug="la-liga",
            name="La Liga",
            country="Spain",
            enabled=False,
            provider_ids={"api_football": 140},
        ),
    ]
)


def _build_service(
    service_settings: Settings,
    provider: MockSportsDataProvider | ApiFootballProvider,
) -> FixtureDiscoveryService:
    from sports_intelligence.db.session import create_engine, create_session_factory

    engine = create_engine(service_settings.database_url)
    session_factory = create_session_factory(engine)
    return FixtureDiscoveryService(
        provider=provider, session_factory=session_factory, league_config=CONFIG
    )


async def _row_count(service_settings: Settings, model: type) -> int:
    from sports_intelligence.db.session import create_engine, create_session_factory

    engine = create_engine(service_settings.database_url)
    try:
        async with create_session_factory(engine)() as session:
            return int(
                (await session.execute(select(func.count()).select_from(model))).scalar_one()
            )
    finally:
        await engine.dispose()


async def _run_discovery(
    service_settings: Settings,
    provider: MockSportsDataProvider,
    fixture_date: str,
):
    service = _build_service(service_settings, provider)
    return await service.discover(date.fromisoformat(fixture_date))


def _mock_provider(provider_name: str, fixture_date: str) -> MockSportsDataProvider:
    return MockSportsDataProvider(responses={fixture_date: RECORDED}, provider_name=provider_name)


def _counts(service_settings: Settings) -> dict[type, int]:
    models = (League, Season, Team, Fixture, ProviderEntityId, RawProviderPayload)
    return {model: asyncio.run(_row_count(service_settings, model)) for model in models}


def test_discovery_persists_entities_and_mappings(service_settings: Settings) -> None:
    before = _counts(service_settings)
    provider = _mock_provider("mock-persists", "2026-08-21")
    summary = asyncio.run(_run_discovery(service_settings, provider, "2026-08-21"))

    assert summary.fixtures_received == 4
    assert summary.fixtures_eligible == 3
    assert summary.fixtures_created == 3
    assert summary.teams_created == 6
    assert summary.seasons_created == 1
    assert summary.leagues_processed == 1
    assert summary.raw_payload_stored is True

    after = _counts(service_settings)
    assert after[RawProviderPayload] - before[RawProviderPayload] == 1
    assert after[Fixture] - before[Fixture] == 3
    assert after[Team] - before[Team] == 6
    assert after[Season] - before[Season] == 1
    assert after[League] - before[League] == 1
    assert after[ProviderEntityId] - before[ProviderEntityId] == 10


def test_discovery_is_idempotent_on_second_run(service_settings: Settings) -> None:
    provider = _mock_provider("mock-idem", "2026-08-21")

    first = asyncio.run(_run_discovery(service_settings, provider, "2026-08-21"))
    assert first.fixtures_created == 3
    assert first.raw_payload_stored is True

    before_second = _counts(service_settings)
    second = asyncio.run(_run_discovery(service_settings, provider, "2026-08-21"))
    assert second.fixtures_created == 0
    assert second.fixtures_updated == 3
    assert second.teams_created == 0
    assert second.seasons_created == 0
    assert second.raw_payload_stored is False

    after_second = _counts(service_settings)
    assert after_second == before_second


def test_disabled_leagues_are_filtered_out(service_settings: Settings) -> None:
    provider = _mock_provider("mock-disabled", "2026-08-23")
    asyncio.run(_run_discovery(service_settings, provider, "2026-08-23"))

    from sports_intelligence.db.session import create_engine

    async def la_liga_count() -> int:
        engine = create_engine(service_settings.database_url)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(
                    select(func.count()).select_from(League).where(League.slug == "la-liga")
                )
                return int(result.scalar_one())
        finally:
            await engine.dispose()

    assert asyncio.run(la_liga_count()) == 0


def _shifted_payload(iso_date: str) -> dict:
    payload = json.loads(json.dumps(RECORDED))
    for entry in payload["response"]:
        fixture = entry["fixture"]
        fixture["date"] = iso_date + fixture["date"][10:]
    return payload


def test_fixtures_api_filters_by_date_and_league(service_settings: Settings) -> None:
    provider = MockSportsDataProvider(
        responses={"2026-08-24": _shifted_payload("2026-08-24")},
        provider_name="mock-api-test",
    )
    asyncio.run(_run_discovery(service_settings, provider, "2026-08-24"))

    with TestClient(create_app(service_settings)) as client:
        response = client.get("/v1/fixtures", params={"date": "2026-08-24"})
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 3
        assert {item["home_team"] for item in body} >= {"FC Mockton", "Nullfield United"}

        premier = client.get(
            "/v1/fixtures", params={"date": "2026-08-24", "league": "premier-league"}
        )
        assert len(premier.json()) == 3

        empty_league = client.get(
            "/v1/fixtures", params={"date": "2026-08-24", "league": "la-liga"}
        )
        assert empty_league.json() == []

        other_date = client.get("/v1/fixtures", params={"date": "2026-08-25"})
        assert other_date.json() == []

        fixture_id = body[0]["id"]
        detail = client.get(f"/v1/fixtures/{fixture_id}")
        assert detail.status_code == 200
        assert detail.json()["id"] == fixture_id

        missing = client.get(f"/v1/fixtures/{uuid.uuid4()}")
        assert missing.status_code == 404


def test_discover_job_endpoint_is_idempotent(
    service_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sports_intelligence.workers.tasks import sports as sports_tasks

    enqueued: list[list[object]] = []
    monkeypatch.setattr(
        sports_tasks.discover_fixtures_task,
        "apply_async",
        lambda args=None, queue=None, **kwargs: enqueued.append(args or []),
    )

    with TestClient(create_app(service_settings)) as client:
        first = client.post("/v1/jobs/discover", json={"date": "2026-08-24"})
        assert first.status_code == 200
        first_body = first.json()
        assert first_body["job_id"]
        assert first_body["already_queued"] is False

        second = client.post("/v1/jobs/discover", json={"date": "2026-08-24"})
        assert second.status_code == 200
        second_body = second.json()
        assert second_body["job_id"] == first_body["job_id"]
        assert second_body["already_queued"] is True

    assert len(enqueued) == 1


def test_discovery_makes_single_provider_request_for_many_fixtures(
    service_settings: Settings,
) -> None:
    state = {"calls": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["calls"] += 1
        return httpx.Response(200, json=RECORDED, headers={"content-type": "application/json"})

    provider = ApiFootballProvider(
        api_key="test-key",
        base_url="https://v3.football.api-sports.io",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        max_attempts=1,
        backoff_seconds=0.0,
    )
    service = _build_service(service_settings, provider)

    async def run() -> None:
        summary = await service.discover(date(2026, 8, 25))
        assert summary.fixtures_eligible == 3

    asyncio.run(run())
    assert state["calls"] == 1


def test_job_row_created_with_pending_status(service_settings: Settings) -> None:
    with TestClient(create_app(service_settings)) as client:
        client.post("/v1/jobs/discover", json={"date": "2026-08-26"})

    async def job_count_for_key() -> int:
        from sports_intelligence.db.session import create_engine, create_session_factory

        engine = create_engine(service_settings.database_url)
        try:
            async with create_session_factory(engine)() as session:
                return int(
                    (
                        await session.execute(
                            select(func.count())
                            .select_from(Job)
                            .where(Job.idempotency_key == "discover:mock:2026-08-26")
                        )
                    ).scalar_one()
                )
        finally:
            await engine.dispose()

    assert asyncio.run(job_count_for_key()) == 1
