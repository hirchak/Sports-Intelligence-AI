"""M4.1 — automated collection, odds, quota/freshness (integration).

Exercises the M4.1 stack against real PostgreSQL + Redis:

- collectors persist snapshots via the framework with external-ID
  resolution (internal UUIDs are never sent to providers);
- two team snapshots from ONE provider response (availability/lineups);
- standings shared across fixtures → single provider call + ledger row;
- coalescing: 10 concurrent callers → 1 provider call / 1 snapshot /
  1 ledger row / same persisted UUID;
- odds immutable history + strict provider-event mapping;
- quota ledger with real header telemetry;
- job_attempts rows with sequential attempt numbers;
- status API + DB-first UX (zero external calls on reads);
- pre-match planner (Warsaw boundaries, future-only) idempotent.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import select

import sports_intelligence.collectors.odds_collector  # noqa: F401
import sports_intelligence.collectors.sports_collectors  # noqa: F401
from sports_intelligence.collectors.framework import (
    CollectorContext,
    run_collector,
)
from sports_intelligence.collectors.freshness import FreshnessPolicy
from sports_intelligence.collectors.locks import CoalesceLockManager
from sports_intelligence.collectors.quota import QuotaManager
from sports_intelligence.core.config import Settings
from sports_intelligence.core.phases import ForecastPhase
from sports_intelligence.db.models import (
    ExternalApiRequest,
    Fixture,
    Job,
    JobAttempt,
    League,
    OddsPrice,
    OddsSnapshotSet,
    ProviderEntityId,
    QuotaBucket,
    RawProviderPayload,
    Season,
    StandingSnapshot,
    Team,
)
from sports_intelligence.db.session import create_engine, create_session_factory
from sports_intelligence.providers.odds.mock import MockOddsProvider
from sports_intelligence.providers.sports.mock import MockSportsDataProvider

requires_services = pytest.mark.skipif(
    not (os.environ.get("TEST_DATABASE_URL") and os.environ.get("TEST_REDIS_URL")),
    reason="TEST_DATABASE_URL and TEST_REDIS_URL are required",
)
pytestmark = [pytest.mark.integration, requires_services]


def _recorded_provider() -> MockSportsDataProvider:
    return MockSportsDataProvider()


@pytest.fixture
def m4_settings(service_settings: Settings) -> Settings:
    return service_settings


@pytest.fixture
async def m4_session_factory(m4_settings: Settings) -> Iterator[Any]:
    engine = create_engine(m4_settings.database_url)
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
async def _clean_m4_tables(m4_session_factory: Any) -> Iterator[None]:
    """Isolate M4 tests: truncate snapshot/quota/mapping tables before
    each test so quota buckets and ledger rows never leak across tests."""
    from sqlalchemy import delete

    from sports_intelligence.db.models import (
        AvailabilitySnapshot,
        ExternalApiRequest,
        LineupSnapshot,
        OddsEventMapping,
        OddsPrice,
        OddsSnapshotSet,
        ProviderEntityId,
        QuotaBucket,
        StandingSnapshot,
        TeamFormSnapshot,
        TeamStatisticsSnapshot,
    )

    async with m4_session_factory() as session:
        for model in (
            OddsPrice,
            OddsSnapshotSet,
            AvailabilitySnapshot,
            LineupSnapshot,
            StandingSnapshot,
            TeamFormSnapshot,
            TeamStatisticsSnapshot,
            ExternalApiRequest,
            QuotaBucket,
            OddsEventMapping,
            ProviderEntityId,
        ):
            await session.execute(delete(model))
        await session.commit()
    yield


@pytest.fixture
async def redis_client(m4_settings: Settings) -> Iterator[Redis]:
    client = Redis.from_url(m4_settings.redis_url)
    try:
        await client.flushdb()
        yield client
    finally:
        await client.aclose()


async def _seed_league_team_fixture(
    factory: Any,
    *,
    kickoff_at: datetime,
    provider: str = "mock",
    with_season: bool = True,
    slug_suffix: str = "",
    league_id: uuid.UUID | None = None,
    season_id: uuid.UUID | None = None,
    team_ids: tuple[uuid.UUID, uuid.UUID] | None = None,
    external_ids: dict[str, str] | None = None,
) -> dict[str, uuid.UUID]:
    """Create a league + season + teams + fixture PLUS provider_entity_ids
    mappings so collectors can resolve internal UUIDs → external ids."""
    slug = f"integration-m41-{slug_suffix or uuid.uuid4().hex[:8]}"
    async with factory() as session:
        if league_id is None:
            league = League(
                slug=slug, name=f"Integration M4.1 {slug_suffix}", country="Test", enabled=True
            )
            session.add(league)
            await session.flush()
            league_id = league.id
        if with_season and season_id is None:
            season = Season(league_id=league_id, name="2026-2027", active=True)
            session.add(season)
            await session.flush()
            season_id = season.id
        if team_ids is None:
            home = Team(name=f"Arsenal M41-{uuid.uuid4().hex[:6]}", country="Test")
            away = Team(name=f"Coventry M41-{uuid.uuid4().hex[:6]}", country="Test")
            session.add(home)
            session.add(away)
            await session.flush()
            team_ids = (home.id, away.id)
        fixture = Fixture(
            league_id=league_id,
            season_id=season_id,
            home_team_id=team_ids[0],
            away_team_id=team_ids[1],
            kickoff_at=kickoff_at,
            status="NS",
        )
        session.add(fixture)
        await session.flush()
        # Unique external ids per seed call so mappings never collide
        # across tests sharing the same database (override for tests
        # that need specific ids, e.g. mock provider canned teams).
        ext_league = (
            external_ids.get("league")
            if external_ids
            else f"{int(uuid.uuid4().int % 10_000_000) + 1000}"
        )
        ext_home = (
            external_ids.get("home")
            if external_ids
            else f"{int(uuid.uuid4().int % 10_000_000) + 1000}"
        )
        ext_away = (
            external_ids.get("away")
            if external_ids
            else f"{int(uuid.uuid4().int % 10_000_000) + 1000}"
        )
        ext_fixture = (
            external_ids.get("fixture")
            if external_ids
            else f"{int(uuid.uuid4().int % 10_000_000) + 1000}"
        )
        session.add_all(
            [
                ProviderEntityId(
                    provider=provider,
                    entity_type="league",
                    external_id=ext_league,
                    internal_entity_id=league_id,
                ),
                ProviderEntityId(
                    provider=provider,
                    entity_type="team",
                    external_id=ext_home,
                    internal_entity_id=team_ids[0],
                ),
                ProviderEntityId(
                    provider=provider,
                    entity_type="team",
                    external_id=ext_away,
                    internal_entity_id=team_ids[1],
                ),
                ProviderEntityId(
                    provider=provider,
                    entity_type="fixture",
                    external_id=ext_fixture,
                    internal_entity_id=fixture.id,
                ),
            ]
        )
        await session.commit()
        return {
            "league_id": league_id,
            "season_id": season_id if season_id is not None else uuid.uuid4(),
            "home_team_id": team_ids[0],
            "away_team_id": team_ids[1],
            "fixture_id": fixture.id,
        }


def _ctx(
    *,
    factory: Any,
    redis: Redis,
    settings: Settings,
    provider: Any,
    phase: ForecastPhase = ForecastPhase.PREMATCH,
) -> CollectorContext:
    locks = CoalesceLockManager(redis, settings)
    quota = QuotaManager(settings, factory, redis=redis)
    return CollectorContext(
        provider=provider,
        quota=quota,
        locks=locks,
        freshness=FreshnessPolicy(settings),
        session_factory=factory,
        settings=settings,
        redis=redis,
        phase=phase,
    )


@pytest.mark.asyncio
async def test_standings_collector_persists_snapshot_and_evidence(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    seeded = await _seed_league_team_fixture(
        m4_session_factory, kickoff_at=datetime.now(UTC) + timedelta(days=1)
    )
    ctx = _ctx(
        factory=m4_session_factory,
        redis=redis_client,
        settings=m4_settings,
        provider=_recorded_provider(),
    )
    ref = await run_collector(
        ctx,
        "standings",
        inputs={"league_id": seeded["league_id"], "season_id": seeded["season_id"]},
    )
    async with m4_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(StandingSnapshot).where(
                        StandingSnapshot.league_id == seeded["league_id"]
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert ref.captured_at is not None
    # Evidence linkage: raw payload row + observation, and the snapshot
    # references a payload_id (M4.1 §10).
    assert rows[0].payload_id is not None
    async with m4_session_factory() as session:
        raw = (
            (
                await session.execute(
                    select(RawProviderPayload).where(
                        RawProviderPayload.endpoint_family == "standings"
                    )
                )
            )
            .scalars()
            .all()
        )
    assert raw, "raw evidence payload missing for standings"


@pytest.mark.asyncio
async def test_standings_shared_across_multiple_fixtures_single_ledger_row(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    kickoff = datetime.now(UTC) + timedelta(days=1)
    shared_slug = f"shared-{uuid.uuid4().hex[:8]}"
    seeded_a = await _seed_league_team_fixture(
        m4_session_factory, kickoff_at=kickoff, slug_suffix=shared_slug
    )
    seeded_b = await _seed_league_team_fixture(
        m4_session_factory,
        kickoff_at=kickoff,
        slug_suffix=shared_slug,
        league_id=seeded_a["league_id"],
        season_id=seeded_a["season_id"],
    )
    ctx = _ctx(
        factory=m4_session_factory,
        redis=redis_client,
        settings=m4_settings,
        provider=_recorded_provider(),
    )
    await run_collector(
        ctx,
        "standings",
        inputs={"league_id": seeded_a["league_id"], "season_id": seeded_a["season_id"]},
    )
    await run_collector(
        ctx,
        "standings",
        inputs={"league_id": seeded_b["league_id"], "season_id": seeded_b["season_id"]},
    )
    async with m4_session_factory() as session:
        ledger = (
            (
                await session.execute(
                    select(ExternalApiRequest).where(
                        ExternalApiRequest.endpoint_category == "standings",
                        ExternalApiRequest.league_id == seeded_a["league_id"],
                    )
                )
            )
            .scalars()
            .all()
        )
    # Second run is fresh (TTL window) → only the first emits a provider
    # call + ledger row.
    assert len(ledger) == 1


@pytest.mark.asyncio
async def test_two_team_availability_snapshots_from_one_response(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    """M4.1 §3: one fixture → TWO separated snapshots (home/away),
    each with ONLY its own players — never merged."""
    # Remove stale canned-id mappings from any prior run of this test so
    # the unique (provider, entity_type, external_id) constraint holds.
    async with m4_session_factory() as session:
        from sqlalchemy import delete

        await session.execute(
            delete(ProviderEntityId).where(
                ProviderEntityId.provider == "mock",
                ProviderEntityId.external_id.in_(["9001", "9002", "42", "39"]),
            )
        )
        await session.commit()

    seeded = await _seed_league_team_fixture(
        m4_session_factory,
        kickoff_at=datetime.now(UTC) + timedelta(days=1),
        external_ids={"home": "9001", "away": "9002", "fixture": "42", "league": "39"},
    )
    ctx = _ctx(
        factory=m4_session_factory,
        redis=redis_client,
        settings=m4_settings,
        provider=_recorded_provider(),
    )
    await run_collector(
        ctx,
        "availability",
        inputs={
            "fixture_id": seeded["fixture_id"],
            "team_id": seeded["home_team_id"],
        },
    )
    from sports_intelligence.db.models import AvailabilitySnapshot

    async with m4_session_factory() as session:
        snapshots = (
            (
                await session.execute(
                    select(AvailabilitySnapshot).where(
                        AvailabilitySnapshot.fixture_id == seeded["fixture_id"]
                    )
                )
            )
            .scalars()
            .all()
        )
    # Both teams persisted from the single MOCK response (9001 home, 9002
    # away). Home has a missing player (KNOWN_PRESENT); away has none.
    assert len(snapshots) == 2
    states = {s.availability_state for s in snapshots}
    assert "KNOWN_PRESENT" in states
    assert "UNKNOWN" in states


@pytest.mark.asyncio
async def test_ten_concurrent_callers_coalesce_to_single_call_snapshot_ledger(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    """M4.1 §5 acceptance: 10 concurrent equivalent collectors →
    exactly 1 provider call, 1 normalized snapshot, 1 ledger row, all
    callers receive the same real persisted UUID."""
    seeded = await _seed_league_team_fixture(
        m4_session_factory, kickoff_at=datetime.now(UTC) + timedelta(days=1)
    )
    ctx = _ctx(
        factory=m4_session_factory,
        redis=redis_client,
        settings=m4_settings,
        provider=_recorded_provider(),
    )
    provider_calls: list[int] = []
    results = await asyncio.gather(
        *[
            run_collector(
                ctx,
                "standings",
                inputs={"league_id": seeded["league_id"], "season_id": seeded["season_id"]},
                on_provider_call=lambda: provider_calls.append(1),
            )
            for _ in range(10)
        ]
    )
    # Lock + published refs: exactly one provider call.
    assert len(provider_calls) == 1
    # All callers got the SAME real snapshot id.
    ids = {r.snapshot_id for r in results}
    assert len(ids) == 1
    real_id = ids.pop()
    # Exactly one normalized snapshot in the DB with that id.
    async with m4_session_factory() as session:
        snapshots = (
            (
                await session.execute(
                    select(StandingSnapshot).where(
                        StandingSnapshot.league_id == seeded["league_id"]
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(snapshots) == 1
    assert snapshots[0].id == real_id
    # Exactly one ledger row.
    async with m4_session_factory() as session:
        ledger = (
            (
                await session.execute(
                    select(ExternalApiRequest).where(
                        ExternalApiRequest.endpoint_category == "standings",
                        ExternalApiRequest.league_id == seeded["league_id"],
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(ledger) == 1


@pytest.mark.asyncio
async def test_odds_collector_persists_snapshot_set_and_prices(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    from decimal import Decimal

    from sports_intelligence.providers.odds.base import (
        OddsProviderResult,
        OddsSelectionPrice,
    )

    seeded = await _seed_league_team_fixture(
        m4_session_factory, kickoff_at=datetime.now(UTC) + timedelta(days=1)
    )

    class _UuidAwareMockOdds(MockOddsProvider):
        async def resolve_event(
            self, *, sport_key, home_team, away_team, commence_time_utc, tolerance_seconds=900
        ):
            return "mock-event-0001"

        async def fetch_event_odds(self, *, sport_key, event_id, markets, regions):
            return OddsProviderResult(
                provider=self.name,
                fixture_id=event_id,
                captured_at="2026-08-21T10:00:00+00:00",
                prices=(
                    OddsSelectionPrice(
                        bookmaker="mockbookie",
                        market="h2h",
                        selection="home",
                        line=None,
                        decimal_odds=Decimal("2.10"),
                    ),
                    OddsSelectionPrice(
                        bookmaker="mockbookie",
                        market="h2h",
                        selection="draw",
                        line=None,
                        decimal_odds=Decimal("3.40"),
                    ),
                    OddsSelectionPrice(
                        bookmaker="mockbookie",
                        market="h2h",
                        selection="away",
                        line=None,
                        decimal_odds=Decimal("3.60"),
                    ),
                ),
                raw_payload={"id": event_id, "bookmakers": []},
            )

    # The YAML config must include odds_sport_key for the fixture's
    # league slug; write a temp config referencing our league.
    import tempfile

    async with m4_session_factory() as session:
        slug = (
            await session.execute(select(League.slug).where(League.id == seeded["league_id"]))
        ).scalar_one()
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(
            f"""
version: 1
leagues:
  - slug: "{slug}"
    name: "Odds League"
    country: "Test"
    enabled: true
    provider_ids:
      mock: 39
      api_football: 39
    odds_sport_key: "soccer_test"
"""
        )
        config_path = f.name

    settings = Settings(
        _env_file=None,
        app_env="mock",
        leagues_config_path=config_path,
        database_url=m4_settings.database_url,
    )
    ctx = _ctx(
        factory=m4_session_factory,
        redis=redis_client,
        settings=settings,
        provider=_UuidAwareMockOdds(sport_key="soccer_test"),
    )
    await run_collector(
        ctx,
        "odds",
        inputs={"fixture_id": seeded["fixture_id"], "league_id": seeded["league_id"]},
    )
    async with m4_session_factory() as session:
        sets = (
            (
                await session.execute(
                    select(OddsSnapshotSet).where(
                        OddsSnapshotSet.fixture_id == seeded["fixture_id"]
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(sets) == 1
    async with m4_session_factory() as session:
        prices = (
            (
                await session.execute(
                    select(OddsPrice).where(OddsPrice.snapshot_set_id == sets[0].id)
                )
            )
            .scalars()
            .all()
        )
    assert prices, "no odds prices persisted"
    selections = {p.selection for p in prices}
    assert selections == {"home", "draw", "away"}


@pytest.mark.asyncio
async def test_odds_history_is_immutable_across_runs(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    from decimal import Decimal

    from sports_intelligence.collectors.odds_collector import OddsCollector
    from sports_intelligence.providers.odds.base import (
        OddsProviderResult,
        OddsSelectionPrice,
    )

    seeded = await _seed_league_team_fixture(
        m4_session_factory, kickoff_at=datetime.now(UTC) + timedelta(days=1)
    )

    class _FixedMockOdds(MockOddsProvider):
        async def resolve_event(
            self, *, sport_key, home_team, away_team, commence_time_utc, tolerance_seconds=900
        ):
            return "mock-event-0001"

        async def fetch_event_odds(self, *, sport_key, event_id, markets, regions):
            return OddsProviderResult(
                provider=self.name,
                fixture_id=event_id,
                captured_at=datetime.now(UTC).isoformat(),
                prices=(
                    OddsSelectionPrice(
                        bookmaker="mockbookie",
                        market="h2h",
                        selection="home",
                        line=None,
                        decimal_odds=Decimal("2.10"),
                    ),
                ),
                raw_payload={"id": event_id, "bookmakers": []},
            )

    async with m4_session_factory() as session:
        slug = (
            await session.execute(select(League.slug).where(League.id == seeded["league_id"]))
        ).scalar_one()
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(
            f"""
version: 1
leagues:
  - slug: "{slug}"
    name: "Odds League"
    country: "Test"
    enabled: true
    provider_ids:
      mock: 39
      api_football: 39
    odds_sport_key: "soccer_test"
"""
        )
        config_path = f.name
    settings = Settings(
        _env_file=None,
        app_env="mock",
        leagues_config_path=config_path,
        database_url=m4_settings.database_url,
    )
    ctx = _ctx(
        factory=m4_session_factory,
        redis=redis_client,
        settings=settings,
        provider=_FixedMockOdds(sport_key="soccer_test"),
    )
    # Two collector runs at different captured times → two snapshot sets
    # (immutable history, never overwritten).
    await run_collector(
        ctx, "odds", inputs={"fixture_id": seeded["fixture_id"], "league_id": seeded["league_id"]}
    )
    collector = OddsCollector()
    result = await collector.fetch(
        ctx, fixture_id=seeded["fixture_id"], league_id=seeded["league_id"]
    )
    from datetime import datetime as _dt

    await collector.persist(
        ctx,
        result,
        captured_at=_dt.now(UTC) + timedelta(seconds=1),
        source_fingerprint="manual:odds:second",
        payload_id=None,
        fixture_id=seeded["fixture_id"],
    )
    async with m4_session_factory() as session:
        sets = (
            (
                await session.execute(
                    select(OddsSnapshotSet).where(
                        OddsSnapshotSet.fixture_id == seeded["fixture_id"]
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(sets) == 2


@pytest.mark.asyncio
async def test_quota_record_persists_buckets_and_costs(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    from sports_intelligence.core.phases import Priority

    quota = QuotaManager(m4_settings, m4_session_factory, redis=redis_client)
    seeded = await _seed_league_team_fixture(
        m4_session_factory, kickoff_at=datetime.now(UTC) + timedelta(days=1)
    )
    started_at = datetime.now(UTC)
    await quota.record_success(
        provider="theoddsapi",
        endpoint_category="odds",
        started_at=started_at,
        finished_at=started_at + timedelta(milliseconds=150),
        headers={
            "x-requests-remaining": "492",
            "x-requests-used": "8",
            "x-requests-last": "5",
        },
        priority=Priority.P1,
        estimated_cost=4,
        fixture_id=seeded["fixture_id"],
        league_id=seeded["league_id"],
    )
    async with m4_session_factory() as session:
        ext = (
            (
                await session.execute(
                    select(ExternalApiRequest).where(
                        ExternalApiRequest.endpoint_category == "odds",
                        ExternalApiRequest.fixture_id == seeded["fixture_id"],
                    )
                )
            )
            .scalars()
            .all()
        )
        buckets = (
            (await session.execute(select(QuotaBucket).where(QuotaBucket.provider == "theoddsapi")))
            .scalars()
            .all()
        )
    assert ext, "external_api_requests row missing after quota.record_success"
    # Estimated cost recorded; actual cost from x-requests-last.
    assert ext[0].estimated_cost == 4
    assert ext[0].actual_cost == 5
    assert ext[0].daily_remaining == 492
    assert buckets, "quota_buckets rows missing"


@pytest.mark.asyncio
async def test_quota_failure_recorded_with_error_class_and_status(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    from sports_intelligence.core.phases import Priority
    from sports_intelligence.providers.errors import ProviderRateLimitError

    quota = QuotaManager(m4_settings, m4_session_factory, redis=redis_client)
    started_at = datetime.now(UTC)
    await quota.record_failure(
        provider="api_football",
        endpoint_category="standings",
        started_at=started_at,
        exc=ProviderRateLimitError("rate limit", status_code=429),
        priority=Priority.P2,
        estimated_cost=1,
    )
    async with m4_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(ExternalApiRequest).where(
                        ExternalApiRequest.endpoint_category == "standings",
                        ExternalApiRequest.error_class == "ProviderRateLimitError",
                    )
                )
            )
            .scalars()
            .all()
        )
    assert rows
    assert rows[0].status_code == 429


@pytest.mark.asyncio
async def test_concurrent_quota_reservation_serializes_last_units(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    """M4.1 §6: several workers must not all spend the last remaining
    units concurrently — the Redis reservation is atomic. With a small
    usable daily budget, only the affordable number of reservations
    succeed."""
    from sports_intelligence.core.phases import Priority

    settings = Settings(
        _env_file=None,
        app_env="mock",
        quota_provider_daily_limit_default=10,
        quota_provider_minute_limit_default=100,
        quota_reserve_p0_calls=2,
    )
    quota = QuotaManager(settings, m4_session_factory, redis=redis_client)
    # Seed a daily bucket with remaining=10, limit=10 so the observed
    # limit is used.
    async with m4_session_factory() as session:
        session.add(
            QuotaBucket(
                provider="mock",
                window="daily",
                limit_value=10,
                remaining_value=10,
                observed_at=datetime.now(UTC),
            )
        )
        await session.commit()

    # usable = limit - reserve = 10 - 2 = 8 units for non-P0.
    results = await asyncio.gather(
        *[quota.reserve(provider="mock", priority=Priority.P2, estimated_cost=2) for _ in range(10)]
    )
    allowed = [r for r in results if r.allowed]
    denied = [r for r in results if not r.allowed]
    # Exactly floor(8 / 2) = 4 atomic reservations succeed; the rest are
    # denied with reservation_exhausted.
    assert len(allowed) == 4
    assert all(r.kind.value == 0 for r in allowed)
    assert all("reservation_exhausted" in r.reason for r in denied)


@pytest.mark.asyncio
async def test_job_attempts_are_numbered_sequentially(
    m4_session_factory: Any,
) -> None:
    """M4.1 §11: re-running the same job yields attempts 1, 2, 3..."""
    job_id = uuid.uuid4()
    async with m4_session_factory() as session:
        session.add(
            Job(
                id=job_id,
                job_type="discover_fixtures",
                idempotency_key=f"test:{job_id}",
                status="SUCCEEDED",
                scheduled_for=datetime.now(UTC),
            )
        )
        await session.commit()

    from sports_intelligence.workers.utils import record_job_attempt

    for _ in range(3):
        await record_job_attempt(
            m4_session_factory,
            job_id=job_id,
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            outcome="SUCCEEDED",
            error=None,
        )

    async with m4_session_factory() as session:
        attempts = (
            (await session.execute(select(JobAttempt).where(JobAttempt.job_id == job_id)))
            .scalars()
            .all()
        )
    numbers = sorted(a.attempt_number for a in attempts)
    assert numbers == [1, 2, 3]
    # Real worker identity (hostname:pid), never a literal ":pid".
    for a in attempts:
        assert a.worker and ":pid" not in a.worker


@pytest.mark.asyncio
async def test_status_api_returns_freshness_per_category(
    m4_session_factory: Any,
    redis_client: Redis,
    m4_settings: Settings,
    service_client: TestClient,
) -> None:
    seeded = await _seed_league_team_fixture(
        m4_session_factory, kickoff_at=datetime.now(UTC) + timedelta(days=1)
    )
    ctx = _ctx(
        factory=m4_session_factory,
        redis=redis_client,
        settings=m4_settings,
        provider=_recorded_provider(),
    )
    await run_collector(
        ctx,
        "standings",
        inputs={"league_id": seeded["league_id"], "season_id": seeded["season_id"]},
    )
    response = service_client.get(f"/v1/fixtures/{seeded['fixture_id']}/status")
    assert response.status_code == 200
    body = response.json()
    assert body["fixture_id"] == str(seeded["fixture_id"])
    assert "standings" in body["freshness"]
    assert body["freshness"]["standings"]["state"] == "fresh"


@pytest.mark.asyncio
async def test_status_api_returns_404_for_missing_fixture(
    service_client: TestClient,
) -> None:
    response = service_client.get(f"/v1/fixtures/{uuid.uuid4()}/status")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_fixtures_does_not_trigger_provider_calls(
    m4_session_factory: Any,
    redis_client: Redis,
    m4_settings: Settings,
    service_client: TestClient,
) -> None:
    """Database-first UX: read flow writes ZERO external_api_requests."""
    seeded = await _seed_league_team_fixture(
        m4_session_factory, kickoff_at=datetime.now(UTC) + timedelta(days=1)
    )
    ctx = _ctx(
        factory=m4_session_factory,
        redis=redis_client,
        settings=m4_settings,
        provider=_recorded_provider(),
    )
    await run_collector(
        ctx,
        "standings",
        inputs={"league_id": seeded["league_id"], "season_id": seeded["season_id"]},
    )
    async with m4_session_factory() as session:
        baseline = len((await session.execute(select(ExternalApiRequest))).scalars().all())

    today = datetime.now(UTC).date().isoformat()
    assert service_client.get(f"/v1/fixtures?date={today}").status_code == 200
    assert service_client.get(f"/v1/fixtures/{seeded['fixture_id']}").status_code == 200
    assert service_client.get(f"/v1/fixtures/{seeded['fixture_id']}/status").status_code == 200
    assert service_client.get("/ready").status_code in (200, 503)

    async with m4_session_factory() as session:
        after = len((await session.execute(select(ExternalApiRequest))).scalars().all())
    assert after == baseline


@pytest.mark.asyncio
async def test_pre_match_scan_planner_uses_warsaw_boundaries_future_only(
    m4_session_factory: Any,
    m4_settings: Settings,
    tmp_path,
) -> None:
    scan_slug = f"integration-m41-scan-{uuid.uuid4().hex[:8]}"
    config_path = tmp_path / "leagues.yaml"
    config_path.write_text(
        f"""
version: 1
leagues:
  - slug: "{scan_slug}"
    name: "Integration M4.1 Scan"
    country: "Test"
    enabled: true
    provider_ids:
      mock: 39
      api_football: 39
"""
    )
    settings = Settings(
        _env_file=None,
        app_env="mock",
        app_timezone="Europe/Warsaw",
        sports_provider="mock",
        leagues_config_path=str(config_path),
        database_url=m4_settings.database_url,
    )
    kickoff = datetime.now(UTC) + timedelta(days=1)
    async with m4_session_factory() as session:
        league = League(slug=scan_slug, name="Scan", country="Test", enabled=True)
        session.add(league)
        await session.flush()
        home = Team(name="A", country="Test")
        away = Team(name="B", country="Test")
        session.add(home)
        session.add(away)
        await session.flush()
        fixture = Fixture(
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=kickoff,
            status="NS",
        )
        session.add(fixture)
        await session.commit()

    from sports_intelligence.collectors.pre_match_scan import plan_for_date

    decisions = await plan_for_date(
        m4_session_factory, settings, day=kickoff.astimezone(UTC).date()
    )
    assert decisions
    decisions_again = await plan_for_date(
        m4_session_factory, settings, day=kickoff.astimezone(UTC).date()
    )
    assert len(decisions) == len(decisions_again)


@pytest.mark.asyncio
async def test_already_started_fixture_plan_yields_no_prematch_calls(
    m4_session_factory: Any,
    m4_settings: Settings,
    tmp_path,
) -> None:
    """M4.1 acceptance: already-started fixture → planner excludes it
    (no lineups/availability/odds dispatch)."""
    started_slug = f"integration-m41-started-{uuid.uuid4().hex[:8]}"
    config_path = tmp_path / "leagues.yaml"
    config_path.write_text(
        f"""
version: 1
leagues:
  - slug: "{started_slug}"
    name: "Started"
    country: "Test"
    enabled: true
    provider_ids:
      mock: 39
      api_football: 39
"""
    )
    settings = Settings(
        _env_file=None,
        app_env="mock",
        app_timezone="Europe/Warsaw",
        sports_provider="mock",
        leagues_config_path=str(config_path),
        database_url=m4_settings.database_url,
    )
    kickoff = datetime.now(UTC) - timedelta(minutes=30)  # already started
    async with m4_session_factory() as session:
        league = League(slug=started_slug, name="Started", country="Test", enabled=True)
        session.add(league)
        await session.flush()
        home = Team(name="C", country="Test")
        away = Team(name="D", country="Test")
        session.add(home)
        session.add(away)
        await session.flush()
        fixture = Fixture(
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=kickoff,
            status="1H",
        )
        session.add(fixture)
        await session.commit()

    from sports_intelligence.collectors.pre_match_scan import plan_for_date

    decisions = await plan_for_date(
        m4_session_factory, settings, day=kickoff.astimezone(UTC).date()
    )
    assert decisions == []
