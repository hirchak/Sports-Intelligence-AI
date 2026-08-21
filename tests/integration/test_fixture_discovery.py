from __future__ import annotations

import asyncio
import json
import os
import threading
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from sports_intelligence.api.app import create_app
from sports_intelligence.core.config import Settings
from sports_intelligence.core.job_status import JobStatus
from sports_intelligence.core.league_config import LeagueConfig, LeagueConfigEntry
from sports_intelligence.core.time import utc_now
from sports_intelligence.db.models import (
    Fixture,
    Job,
    League,
    ProviderEntityId,
    ProviderObservation,
    RawProviderPayload,
    Season,
    Team,
)
from sports_intelligence.pipelines.discover_fixtures import FixtureDiscoveryService
from sports_intelligence.providers.errors import ProviderConfigError
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

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "provider" / "api_football"
RECORDED = json.loads((FIXTURES_DIR / "fixtures_by_date.json").read_text())

_DISCOVERY_TABLES = (
    "jobs",
    "provider_observations",
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


def _config_for(provider_name: str) -> LeagueConfig:
    return LeagueConfig(
        leagues=[
            LeagueConfigEntry(
                slug="premier-league",
                name="Premier League",
                country="England",
                enabled=True,
                provider_ids={provider_name: 39},
            ),
            LeagueConfigEntry(
                slug="la-liga",
                name="La Liga",
                country="Spain",
                enabled=False,
                provider_ids={provider_name: 140},
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
        provider=provider,
        session_factory=session_factory,
        league_config=_config_for(provider.capabilities.provider),
        app_timezone="Europe/Warsaw",
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
    models = (
        League,
        Season,
        Team,
        Fixture,
        ProviderEntityId,
        RawProviderPayload,
        ProviderObservation,
    )
    return {model: asyncio.run(_row_count(service_settings, model)) for model in models}


def _without_observations(counts: dict[type, int]) -> dict[type, int]:
    return {model: value for model, value in counts.items() if model is not ProviderObservation}


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
    assert after[ProviderObservation] - before[ProviderObservation] == 1
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
    assert _without_observations(after_second) == _without_observations(before_second)
    assert after_second[ProviderObservation] == before_second[ProviderObservation] + 1


def test_concurrent_discovery_creates_single_team_and_mapping(
    service_settings: Settings,
) -> None:
    provider = _mock_provider("mock-concurrent", "2026-08-21")
    before = _counts(service_settings)

    async def run_twice() -> None:
        service = _build_service(service_settings, provider)
        await asyncio.gather(
            service.discover(date(2026, 8, 21)),
            service.discover(date(2026, 8, 21)),
        )

    asyncio.run(run_twice())

    after = _counts(service_settings)
    assert after[Team] - before[Team] == 6
    assert after[ProviderEntityId] - before[ProviderEntityId] == 10
    assert after[Fixture] - before[Fixture] == 3


def test_fixture_refresh_updates_kickoff_keeping_same_uuid(
    service_settings: Settings,
) -> None:
    provider_name = "mock-refresh"
    provider = _mock_provider(provider_name, "2026-08-21")
    asyncio.run(_run_discovery(service_settings, provider, "2026-08-21"))

    from sports_intelligence.db.session import create_engine, create_session_factory

    async def fixture_by_provider_id(external_id: int) -> Fixture:
        engine = create_engine(service_settings.database_url)
        try:
            async with create_session_factory(engine)() as session:
                mapping_id = (
                    await session.execute(
                        select(ProviderEntityId.internal_entity_id).where(
                            ProviderEntityId.provider == provider_name,
                            ProviderEntityId.entity_type == "fixture",
                            ProviderEntityId.external_id == str(external_id),
                        )
                    )
                ).scalar_one()
                fixture = await session.get(Fixture, mapping_id)
                assert fixture is not None
                return fixture
        finally:
            await engine.dispose()

    original = asyncio.run(fixture_by_provider_id(100001))
    original_kickoff = original.kickoff_at
    original_uuid = original.id

    moved_payload = json.loads(json.dumps(RECORDED))
    for entry in moved_payload["response"]:
        if entry["fixture"]["id"] == 100001:
            entry["fixture"]["date"] = "2026-08-21T20:30:00+00:00"

    moved_provider = MockSportsDataProvider(
        responses={"2026-08-21": moved_payload}, provider_name=provider_name
    )
    asyncio.run(_run_discovery(service_settings, moved_provider, "2026-08-21"))

    refreshed = asyncio.run(fixture_by_provider_id(100001))
    assert refreshed.id == original_uuid
    assert refreshed.kickoff_at != original_kickoff
    assert refreshed.kickoff_at == datetime(2026, 8, 21, 20, 30, tzinfo=UTC)


def test_league_upsert_syncs_enabled_flag(service_settings: Settings) -> None:
    from sports_intelligence.db.repositories.discovery import upsert_league_id
    from sports_intelligence.db.session import create_engine, create_session_factory

    async def league_enabled() -> bool:
        engine = create_engine(service_settings.database_url)
        try:
            async with create_session_factory(engine)() as session:
                return bool(
                    (
                        await session.execute(
                            select(League.enabled).where(League.slug == "premier-league")
                        )
                    ).scalar_one()
                )
        finally:
            await engine.dispose()

    async def upsert(enabled: bool) -> None:
        engine = create_engine(service_settings.database_url)
        try:
            async with create_session_factory(engine)() as session:
                await upsert_league_id(
                    session, "premier-league", "Premier League", "England", enabled
                )
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(upsert(False))
    assert asyncio.run(league_enabled()) is False
    asyncio.run(upsert(True))
    assert asyncio.run(league_enabled()) is True
    asyncio.run(upsert(False))
    assert asyncio.run(league_enabled()) is False


def test_discovery_without_enabled_leagues_makes_no_provider_calls(
    service_settings: Settings,
) -> None:
    from sports_intelligence.db.session import create_engine, create_session_factory

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
    engine = create_engine(service_settings.database_url)
    session_factory = create_session_factory(engine)
    no_enabled = LeagueConfig(
        leagues=[
            LeagueConfigEntry(
                slug="premier-league",
                name="Premier League",
                enabled=False,
                provider_ids={"api_football": 39},
            )
        ]
    )
    service = FixtureDiscoveryService(
        provider=provider,
        session_factory=session_factory,
        league_config=no_enabled,
        app_timezone="Europe/Warsaw",
    )

    async def run() -> None:
        summary = await service.discover(date(2026, 8, 21))
        assert summary.fixtures_received == 0
        assert summary.fixtures_eligible == 0

    asyncio.run(run())
    assert state["calls"] == 0


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


def test_fixtures_api_filters_by_date_and_league(service_settings: Settings) -> None:
    provider = MockSportsDataProvider(
        responses={"2026-08-24": _shifted_payload("2026-08-24T19:00:00+00:00")},
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


def test_fixture_date_filter_uses_app_timezone_boundaries(service_settings: Settings) -> None:
    unique_kickoff = "2026-08-20T23:30:00+00:00"
    expected_serialized = "2026-08-20T23:30:00Z"
    late_utc_payload = _shifted_payload(unique_kickoff)
    provider = MockSportsDataProvider(
        responses={"2026-08-20": late_utc_payload},
        provider_name="mock-tz",
    )
    asyncio.run(_run_discovery(service_settings, provider, "2026-08-20"))

    with TestClient(create_app(service_settings)) as client:
        warsaw_day = client.get("/v1/fixtures", params={"date": "2026-08-21"})
        kickoffs = {item["kickoff_at"] for item in warsaw_day.json()}
        assert expected_serialized in kickoffs

        utc_day = client.get("/v1/fixtures", params={"date": "2026-08-20"})
        utc_kickoffs = {item["kickoff_at"] for item in utc_day.json()}
        assert expected_serialized not in utc_kickoffs


def _shifted_payload(iso_datetime: str) -> dict:
    payload = json.loads(json.dumps(RECORDED))
    for entry in payload["response"]:
        fixture = entry["fixture"]
        fixture["date"] = iso_datetime
    return payload


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


def test_discover_key_includes_config_version_and_timezone(
    service_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sports_intelligence.workers.tasks import sports as sports_tasks

    monkeypatch.setattr(
        sports_tasks.discover_fixtures_task,
        "apply_async",
        lambda args=None, queue=None, **kwargs: None,
    )

    with TestClient(create_app(service_settings)) as client:
        response = client.post("/v1/jobs/discover", json={"date": "2026-08-21"})
        assert response.status_code == 200
        assert response.json()["idempotency_key"] == "discover:mock:2026-08-21:v1:Europe/Warsaw"


def test_league_config_version_change_creates_new_job(
    service_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sports_intelligence.api.routes import jobs as jobs_route
    from sports_intelligence.workers.tasks import sports as sports_tasks

    enqueued: list[list[object]] = []
    monkeypatch.setattr(
        sports_tasks.discover_fixtures_task,
        "apply_async",
        lambda args=None, queue=None, **kwargs: enqueued.append(args or []),
    )

    with TestClient(create_app(service_settings)) as client:
        first = client.post("/v1/jobs/discover", json={"date": "2026-08-25"})
        assert first.status_code == 200
        assert first.json()["already_queued"] is False

        monkeypatch.setattr(
            jobs_route,
            "load_league_config",
            lambda path: LeagueConfig(version=2, leagues=[]),
        )
        second = client.post("/v1/jobs/discover", json={"date": "2026-08-25"})
        assert second.status_code == 200
        assert second.json()["already_queued"] is False
        assert second.json()["job_id"] != first.json()["job_id"]
        assert second.json()["idempotency_key"] == "discover:mock:2026-08-25:v2:Europe/Warsaw"

    assert len(enqueued) == 2


def test_timezone_is_part_of_discovery_identity(
    service_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sports_intelligence.workers.tasks import sports as sports_tasks

    enqueued: list[list[object]] = []
    monkeypatch.setattr(
        sports_tasks.discover_fixtures_task,
        "apply_async",
        lambda args=None, queue=None, **kwargs: enqueued.append(args or []),
    )

    warsaw_settings = service_settings.model_copy(update={"app_timezone": "Europe/Warsaw"})
    london_settings = service_settings.model_copy(update={"app_timezone": "Europe/London"})

    with TestClient(create_app(warsaw_settings)) as client:
        warsaw = client.post("/v1/jobs/discover", json={"date": "2026-09-01"})
        assert warsaw.status_code == 200
        assert warsaw.json()["idempotency_key"] == "discover:mock:2026-09-01:v1:Europe/Warsaw"

    with TestClient(create_app(london_settings)) as client:
        london = client.post("/v1/jobs/discover", json={"date": "2026-09-01"})
        assert london.status_code == 200
        assert london.json()["already_queued"] is False
        assert london.json()["idempotency_key"] == "discover:mock:2026-09-01:v1:Europe/London"
        assert london.json()["job_id"] != warsaw.json()["job_id"]

    assert len(enqueued) == 2


def test_enqueue_failure_marks_job_failed_and_repost_requeues(
    service_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sports_intelligence.workers.tasks import sports as sports_tasks

    calls: list[object] = []

    def failing_apply_async(*args: object, **kwargs: object) -> None:
        calls.append(args)
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(sports_tasks.discover_fixtures_task, "apply_async", failing_apply_async)

    with TestClient(create_app(service_settings)) as client:
        first = client.post("/v1/jobs/discover", json={"date": "2026-08-27"})
        assert first.status_code == 502
        assert first.json()["detail"]["status"] == JobStatus.FAILED.value
        failed_job_id = first.json()["detail"]["job_id"]

    ok_calls: list[list[object]] = []
    monkeypatch.setattr(
        sports_tasks.discover_fixtures_task,
        "apply_async",
        lambda args=None, queue=None, **kwargs: ok_calls.append(args or []),
    )

    with TestClient(create_app(service_settings)) as client:
        second = client.post("/v1/jobs/discover", json={"date": "2026-08-27"})
        assert second.status_code == 200
        assert second.json()["job_id"] == failed_job_id
        assert second.json()["already_queued"] is False
        assert second.json()["status"] == JobStatus.PENDING.value

    assert len(calls) == 1
    assert len(ok_calls) == 1


def test_discover_without_date_uses_app_timezone_local_date(
    service_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sports_intelligence.api.routes import jobs as jobs_route
    from sports_intelligence.workers.tasks import sports as sports_tasks

    enqueued: list[list[object]] = []
    monkeypatch.setattr(
        sports_tasks.discover_fixtures_task,
        "apply_async",
        lambda args=None, queue=None, **kwargs: enqueued.append(args or []),
    )
    fixed_now = datetime(2026, 9, 2, 23, 30, tzinfo=UTC)
    monkeypatch.setattr(jobs_route, "utc_now", lambda: fixed_now)

    with TestClient(create_app(service_settings)) as client:
        response = client.post("/v1/jobs/discover", json={})
        assert response.status_code == 200
        assert response.json()["idempotency_key"] == "discover:mock:2026-09-03:v1:Europe/Warsaw"

    assert len(enqueued) == 1
    assert enqueued[0][1] == "2026-09-03"


def test_job_row_created_with_pending_status(
    service_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sports_intelligence.workers.tasks import sports as sports_tasks

    monkeypatch.setattr(
        sports_tasks.discover_fixtures_task,
        "apply_async",
        lambda args=None, queue=None, **kwargs: None,
    )

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
                            .where(
                                Job.idempotency_key == "discover:mock:2026-08-26:v1:Europe/Warsaw"
                            )
                        )
                    ).scalar_one()
                )
        finally:
            await engine.dispose()

    assert asyncio.run(job_count_for_key()) == 1


async def _job_status(service_settings: Settings, job_id: str) -> str:
    from sports_intelligence.db.session import create_engine, create_session_factory

    engine = create_engine(service_settings.database_url)
    try:
        async with create_session_factory(engine)() as session:
            job = await session.get(Job, uuid.UUID(job_id))
            assert job is not None
            return job.status
    finally:
        await engine.dispose()


async def _set_job_status_directly(
    service_settings: Settings, job_id: str, status: JobStatus
) -> None:
    from sports_intelligence.db.session import create_engine, create_session_factory

    engine = create_engine(service_settings.database_url)
    try:
        async with create_session_factory(engine)() as session:
            job = await session.get(Job, uuid.UUID(job_id))
            assert job is not None
            job.status = status.value
            await session.commit()
    finally:
        await engine.dispose()


def test_enqueue_requeue_never_downgrades_running_job(
    service_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sports_intelligence.workers.tasks import sports as sports_tasks

    def failing_apply_async(*args: object, **kwargs: object) -> None:
        raise RuntimeError("broker unavailable")

    monkeypatch.setattr(sports_tasks.discover_fixtures_task, "apply_async", failing_apply_async)

    with TestClient(create_app(service_settings)) as client:
        first = client.post("/v1/jobs/discover", json={"date": "2026-08-28"})
        assert first.status_code == 502
        failed_job_id = first.json()["detail"]["job_id"]

    def racing_apply_async(*args: object, **kwargs: object) -> None:
        job_id = kwargs["args"][0]

        def mark_running_in_new_thread() -> None:
            asyncio.run(_set_job_status_directly(service_settings, job_id, JobStatus.RUNNING))

        thread = threading.Thread(target=mark_running_in_new_thread)
        thread.start()
        thread.join()

    monkeypatch.setattr(sports_tasks.discover_fixtures_task, "apply_async", racing_apply_async)

    with TestClient(create_app(service_settings)) as client:
        second = client.post("/v1/jobs/discover", json={"date": "2026-08-28"})
        assert second.status_code == 200
        body = second.json()
        assert body["job_id"] == failed_job_id
        assert body["status"] == JobStatus.RUNNING.value

    assert asyncio.run(_job_status(service_settings, failed_job_id)) == JobStatus.RUNNING.value


def test_concurrent_team_identity_produces_single_entity(
    service_settings: Settings,
) -> None:
    from sports_intelligence.db.repositories.discovery import get_or_create_team_id
    from sports_intelligence.db.session import create_engine, create_session_factory

    provider_name = "mock-team-race"
    external_id = 999001
    name = "Racing FC"
    participant_count = 6

    async def run_race() -> list[uuid.UUID]:
        engine = create_engine(service_settings.database_url)
        session_factory = create_session_factory(engine)
        barrier = asyncio.Barrier(participant_count)

        async def participant() -> uuid.UUID:
            await barrier.wait()
            async with session_factory() as session:
                resolved, _ = await get_or_create_team_id(session, provider_name, external_id, name)
                await session.commit()
                return resolved

        try:
            results = await asyncio.gather(*(participant() for _ in range(participant_count)))
        finally:
            await engine.dispose()
        return results

    results = asyncio.run(run_race())
    assert len(set(results)) == 1

    async def counts() -> tuple[int, int]:
        engine = create_engine(service_settings.database_url)
        try:
            async with create_session_factory(engine)() as session:
                mapping_count = int(
                    (
                        await session.execute(
                            select(func.count())
                            .select_from(ProviderEntityId)
                            .where(
                                ProviderEntityId.provider == provider_name,
                                ProviderEntityId.entity_type == "team",
                                ProviderEntityId.external_id == str(external_id),
                            )
                        )
                    ).scalar_one()
                )
                team_count = int(
                    (
                        await session.execute(
                            select(func.count()).select_from(Team).where(Team.id == results[0])
                        )
                    ).scalar_one()
                )
        finally:
            await engine.dispose()
        return mapping_count, team_count

    mapping_count, team_count = asyncio.run(counts())
    assert mapping_count == 1
    assert team_count == 1


def test_worker_init_failure_marks_job_failed(
    service_settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sports_intelligence.db.session import create_engine, create_session_factory
    from sports_intelligence.pipelines.discover_fixtures import create_or_get_job
    from sports_intelligence.workers.tasks import sports as sports_tasks

    monkeypatch.setattr(sports_tasks, "get_settings", lambda: service_settings)

    def boom(settings: Settings) -> object:
        raise ProviderConfigError("unknown provider")

    monkeypatch.setattr(sports_tasks, "build_sports_provider", boom)

    async def create_job() -> str:
        engine = create_engine(service_settings.database_url)
        factory = create_session_factory(engine)
        try:
            async with factory() as session:
                job, _ = await create_or_get_job(
                    session,
                    "discover_fixtures",
                    "discover:mock:2026-08-29",
                    utc_now(),
                )
                await session.commit()
                return str(job.id)
        finally:
            await engine.dispose()

    job_id = asyncio.run(create_job())

    with pytest.raises(ProviderConfigError):
        asyncio.run(sports_tasks._run_discovery(job_id, "2026-08-29"))

    assert asyncio.run(_job_status(service_settings, job_id)) == JobStatus.FAILED.value
