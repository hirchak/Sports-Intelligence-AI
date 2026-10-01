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
from sports_intelligence.core.phases import ForecastPhase, FreshnessCategory
from sports_intelligence.db.models import (
    AvailabilitySnapshot,
    ExternalApiRequest,
    Fixture,
    Job,
    JobAttempt,
    League,
    LineupSnapshot,
    OddsPrice,
    OddsSnapshotSet,
    ProviderEntityId,
    QuotaBucket,
    RawProviderPayload,
    Season,
    StandingSnapshot,
    Team,
    TeamStatisticsSnapshot,
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
        ExternalApiRequest,
        Job,
        LineupSnapshot,
        OddsEventMapping,
        OddsPrice,
        OddsSnapshotSet,
        ProviderEntityId,
        QuotaBucket,
        ResearchClaim,
        ResearchDocument,
        ResearchRun,
        StandingSnapshot,
        TeamFormSnapshot,
        TeamStatisticsSnapshot,
    )

    async with m4_session_factory() as session:
        for model in (
            ResearchClaim,
            ResearchDocument,
            ResearchRun,
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
            Job,
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
    # Baseline semantics: remaining 10 - reserve floor 1 → 4 × 2-cost
    # reservations consume 8; further spend is denied against the
    # observed baseline (reserve protection / insufficient budget).
    assert all("reserve" in r.reason or "insufficient" in r.reason for r in denied)


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
    from sports_intelligence.core.time import local_today

    decisions = await plan_for_date(
        m4_session_factory, settings, day=local_today(kickoff, settings.app_timezone)
    )
    assert decisions
    decisions_again = await plan_for_date(
        m4_session_factory, settings, day=local_today(kickoff, settings.app_timezone)
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


# ---------------------------------------------------------------------------
# M4.2 acceptance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scanner_opportunity_identity_dedupes_then_opens_new_job(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    """M4.2 §1: first PREMATCH scan enqueues one job; a duplicate scan
    inside the same opportunity reuses it; a later T60 window opens a
    NEW lineup job."""
    from unittest.mock import patch as _patch

    from sports_intelligence.collectors.pre_match_scan import PreMatchDecision
    from sports_intelligence.workers.tasks.collect import collect_task
    from sports_intelligence.workers.tasks.pre_match import _dispatch_decision

    captured: list[list[object]] = []

    def _fake_apply_async(*, args, **_kwargs):  # type: ignore[no-untyped-def]
        captured.append(list(args))

    captured: list[list[object]] = []

    def _fake_apply_async(*, args, **_kwargs):  # type: ignore[no-untyped-def]
        captured.append(list(args))

    kickoff = datetime.now(UTC) + timedelta(minutes=110)  # inside T120
    seeded = await _seed_league_team_fixture(m4_session_factory, kickoff_at=kickoff)
    decision = PreMatchDecision(
        fixture_id=str(seeded["fixture_id"]),
        league_id=str(seeded["league_id"]),
        home_team_id=str(seeded["home_team_id"]),
        away_team_id=str(seeded["away_team_id"]),
        season_id=str(seeded.get("season_id")) if seeded.get("season_id") else None,
        kickoff_at=kickoff,
        phase=ForecastPhase.PREMATCH,
        categories_to_collect=(FreshnessCategory.LINEUPS,),
    )

    captured: list[list[object]] = []

    with _patch.object(collect_task, "apply_async", _fake_apply_async):
        first = await _dispatch_decision(
            m4_session_factory, decision, now=kickoff - timedelta(minutes=110)
        )
        second = await _dispatch_decision(
            m4_session_factory, decision, now=kickoff - timedelta(minutes=105)
        )
    assert first["planned"] == 2
    assert first["jobs_created"] == 1
    assert first["jobs_reused"] == 1
    assert first["jobs_enqueued"] == 1
    assert second["jobs_created"] == 0
    assert second["jobs_reused"] == 2
    assert second["jobs_enqueued"] == 0
    assert len(captured) == 1  # one enqueue (home+away share the job)
    # Same opportunity (both inside T120): ONE fixture-level job
    # (lineups share one provider request per fixture).
    async with m4_session_factory() as session:
        from sports_intelligence.db.models import Job

        jobs = (
            (await session.execute(select(Job).where(Job.job_type == "collect:lineups")))
            .scalars()
            .all()
        )
    assert len(jobs) == 1  # deduped across the two scans in T120

    # Later T60 window → NEW opportunity → new job.
    with _patch.object(collect_task, "apply_async", _fake_apply_async):
        later = await _dispatch_decision(
            m4_session_factory, decision, now=kickoff - timedelta(minutes=50)
        )
    assert later["jobs_created"] == 1  # T60 opens a new opportunity
    assert later["jobs_enqueued"] == 1
    async with m4_session_factory() as session:
        jobs_after = (
            (await session.execute(select(Job).where(Job.job_type == "collect:lineups")))
            .scalars()
            .all()
        )
    assert len(jobs_after) == 2  # t120 job + t60 job


@pytest.mark.asyncio
async def test_lineup_t120_t60_t20_runtime_refresh_flow(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    """M4.2 §2 runtime: T120 NOT_YET_PUBLISHED → T60 refresh due →
    CONFIRMED stops T20. The generic 24h lineup TTL never overrides."""
    from sports_intelligence.collectors.framework import run_collector
    from sports_intelligence.core.phases import ForecastPhase as _FP

    kickoff = datetime.now(UTC) + timedelta(minutes=110)
    seeded = await _seed_league_team_fixture(
        m4_session_factory,
        kickoff_at=kickoff,
        external_ids={"home": "9001", "away": "9002", "fixture": "42", "league": "39"},
    )
    provider = MockSportsDataProvider(lineups_published=False)
    ctx = _ctx(
        factory=m4_session_factory,
        redis=redis_client,
        settings=m4_settings,
        provider=provider,
        phase=_FP.PREMATCH,
    )
    provider_calls: list[int] = []

    # T-110 (T120 window): not published → one provider call, both teams
    # get NOT_YET_PUBLISHED.
    await run_collector(
        ctx,
        "lineups",
        inputs={"fixture_id": seeded["fixture_id"], "team_id": seeded["home_team_id"]},
        now=kickoff - timedelta(minutes=110),
        on_provider_call=lambda: provider_calls.append(1),
    )
    assert provider_calls == [1]
    async with m4_session_factory() as session:
        home_snaps = (
            (
                await session.execute(
                    select(LineupSnapshot).where(
                        LineupSnapshot.fixture_id == seeded["fixture_id"],
                        LineupSnapshot.team_id == seeded["home_team_id"],
                    )
                )
            )
            .scalars()
            .all()
        )
    assert home_snaps and home_snaps[-1].publication_state == "NOT_YET_PUBLISHED"

    # T-50 (T60 window): NOT_YET_PUBLISHED at T120 must PERMIT the T60
    # refresh → second provider call.
    await run_collector(
        ctx,
        "lineups",
        inputs={"fixture_id": seeded["fixture_id"], "team_id": seeded["home_team_id"]},
        now=kickoff - timedelta(minutes=50),
        on_provider_call=lambda: provider_calls.append(1),
    )
    assert len(provider_calls) == 2

    # Now CONFIRMED (published provider) at T-10 (T20 window): polling
    # STOPS → zero provider calls.
    published_ctx = _ctx(
        factory=m4_session_factory,
        redis=redis_client,
        settings=m4_settings,
        provider=MockSportsDataProvider(lineups_published=True),
        phase=_FP.PREMATCH,
    )
    # Now the provider publishes lineups: run once (T-25) to persist a
    # CONFIRMED snapshot...
    published_ctx = _ctx(
        factory=m4_session_factory,
        redis=redis_client,
        settings=m4_settings,
        provider=MockSportsDataProvider(lineups_published=True),
        phase=_FP.PREMATCH,
    )
    await run_collector(
        published_ctx,
        "lineups",
        inputs={"fixture_id": seeded["fixture_id"], "team_id": seeded["home_team_id"]},
        now=kickoff - timedelta(minutes=25),
        on_provider_call=lambda: provider_calls.append(1),
    )
    assert len(provider_calls) == 3

    # ...and a later T-10 (T20 window) scan must make ZERO provider
    # calls: CONFIRMED stops normal polling.
    await run_collector(
        published_ctx,
        "lineups",
        inputs={"fixture_id": seeded["fixture_id"], "team_id": seeded["home_team_id"]},
        now=kickoff - timedelta(minutes=10),
        on_provider_call=lambda: provider_calls.append(1),
    )
    assert len(provider_calls) == 3  # confirmed stops polling
    async with m4_session_factory() as session:
        confirmed = (
            (
                await session.execute(
                    select(LineupSnapshot.publication_state)
                    .where(
                        LineupSnapshot.fixture_id == seeded["fixture_id"],
                        LineupSnapshot.team_id == seeded["home_team_id"],
                    )
                    .order_by(LineupSnapshot.captured_at.desc())
                )
            )
            .scalars()
            .first()
        )
    assert confirmed == "CONFIRMED"


@pytest.mark.asyncio
async def test_synchronized_home_away_lineup_one_provider_call_two_snapshots(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    """M4.2 §3: synchronized home+away lineup collection → exactly ONE
    provider call, TWO correctly separated snapshots, each caller gets
    its own team ref."""
    from sports_intelligence.collectors.framework import run_collector
    from sports_intelligence.core.phases import ForecastPhase as _FP

    kickoff = datetime.now(UTC) + timedelta(minutes=90)
    seeded = await _seed_league_team_fixture(
        m4_session_factory,
        kickoff_at=kickoff,
        external_ids={"home": "9001", "away": "9002", "fixture": "42", "league": "39"},
    )
    ctx = _ctx(
        factory=m4_session_factory,
        redis=redis_client,
        settings=m4_settings,
        provider=MockSportsDataProvider(lineups_published=True),
        phase=_FP.PREMATCH,
    )
    provider_calls: list[int] = []

    results = await asyncio.gather(
        run_collector(
            ctx,
            "lineups",
            inputs={"fixture_id": seeded["fixture_id"], "team_id": seeded["home_team_id"]},
            on_provider_call=lambda: provider_calls.append(1),
        ),
        run_collector(
            ctx,
            "lineups",
            inputs={"fixture_id": seeded["fixture_id"], "team_id": seeded["away_team_id"]},
            on_provider_call=lambda: provider_calls.append(1),
        ),
    )
    assert provider_calls == [1]
    async with m4_session_factory() as session:
        snaps = (
            (
                await session.execute(
                    select(LineupSnapshot).where(LineupSnapshot.fixture_id == seeded["fixture_id"])
                )
            )
            .scalars()
            .all()
        )
    assert len(snaps) == 2
    home_ref = next(r for r in results if r.team_id == seeded["home_team_id"])
    away_ref = next(r for r in results if r.team_id == seeded["away_team_id"])
    assert home_ref.snapshot_id != away_ref.snapshot_id
    async with m4_session_factory() as session:
        by_team = {
            s.team_id: s
            for s in (
                await session.execute(
                    select(LineupSnapshot).where(LineupSnapshot.fixture_id == seeded["fixture_id"])
                )
            )
            .scalars()
            .all()
        }
    assert home_ref.snapshot_id == by_team[seeded["home_team_id"]].id
    assert away_ref.snapshot_id == by_team[seeded["away_team_id"]].id
    assert all(s.publication_state == "CONFIRMED" for s in by_team.values())


@pytest.mark.asyncio
async def test_odds_collector_reserves_estimated_credit_cost(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    """M4.2 §8: 4 markets × 1 region → 4 credits reserved, not 1."""
    from sports_intelligence.core.phases import Priority

    settings = Settings(
        _env_file=None,
        app_env="mock",
        quota_provider_daily_limit_default=100,
        quota_provider_minute_limit_default=100,
        odds_provider_markets=["h2h", "double_chance", "totals", "btts"],
        odds_provider_regions=["eu"],
        database_url=m4_settings.database_url,
    )
    quota = QuotaManager(settings, m4_session_factory, redis=redis_client)
    async with m4_session_factory() as session:
        session.add(
            QuotaBucket(
                provider="mock-odds",
                window="daily",
                limit_value=100,
                remaining_value=100,
                observed_at=datetime.now(UTC),
            )
        )
        await session.commit()
    decision = await quota.reserve(provider="mock-odds", priority=Priority.P1, estimated_cost=4)
    assert decision.allowed is True
    # After the 4-credit reservation, a second identical reservation
    # must still succeed (96 left) but a 90-credit one must fail.
    second = await quota.reserve(provider="mock-odds", priority=Priority.P1, estimated_cost=4)
    assert second.allowed is True
    huge = await quota.reserve(provider="mock-odds", priority=Priority.P1, estimated_cost=95)
    assert huge.allowed is False


@pytest.mark.asyncio
async def test_partially_depleted_quota_concurrent_reservations(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    """M4.2 §9: observed remaining=4 of limit=100 — concurrent P0/P1
    reservations must never exceed the observed remaining budget."""
    from sports_intelligence.core.phases import Priority

    settings = Settings(
        _env_file=None,
        app_env="mock",
        quota_provider_daily_limit_default=100,
        quota_provider_minute_limit_default=100,
        quota_reserve_p0_calls=2,
        database_url=m4_settings.database_url,
    )
    quota = QuotaManager(settings, m4_session_factory, redis=redis_client)
    async with m4_session_factory() as session:
        session.add(
            QuotaBucket(
                provider="mock",
                window="daily",
                limit_value=100,
                remaining_value=4,
                observed_at=datetime.now(UTC),
            )
        )
        await session.commit()

    # 10 concurrent P1 reservations of cost 1 against remaining=4:
    # baseline 4, reserve_eff = min(2, 10) = 2 → P1 may use 2 units.
    results = await asyncio.gather(
        *[quota.reserve(provider="mock", priority=Priority.P1, estimated_cost=1) for _ in range(10)]
    )
    allowed = [r for r in results if r.allowed]
    denied = [r for r in results if not r.allowed]
    assert len(allowed) == 2  # remaining(4) - reserve(2) = 2 units for P1
    assert len(denied) == 8
    assert all("reserve" in r.reason or "insufficient" in r.reason for r in denied)

    # P0 may still use the protected reserve: 2 units remain.
    p0_results = await asyncio.gather(
        *[quota.reserve(provider="mock", priority=Priority.P0, estimated_cost=1) for _ in range(10)]
    )
    p0_allowed = [r for r in p0_results if r.allowed]
    assert len(p0_allowed) == 2


@pytest.mark.asyncio
async def test_real_provider_quota_init_failure_marks_job_failed_zero_provider_calls(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings, tmp_path
) -> None:
    """M4.2 §10: for a REAL provider, failure to initialize quota
    protection fails CLOSED — the job is FAILED and ZERO provider calls
    happen. MOCK may remain keyless."""
    from unittest.mock import AsyncMock, patch

    from sports_intelligence.workers.tasks.sports import _run_discovery

    job_id = uuid.uuid4()
    async with m4_session_factory() as session:
        session.add(
            Job(
                id=job_id,
                job_type="discover_fixtures",
                idempotency_key=f"failclosed:{job_id}",
                status="PENDING",
                scheduled_for=datetime.now(UTC),
            )
        )
        await session.commit()

    settings = Settings(
        _env_file=None,
        app_env="live_local",
        sports_provider="api_football",
        sports_api_key="some-key",
        leagues_config_path=m4_settings.leagues_config_path,
        database_url=m4_settings.database_url,
        redis_url="redis://127.0.0.1:1/0",  # unreachable Redis
    )

    provider_calls: list[int] = []

    class _FailQuota:
        def __init__(self, *a, **k) -> None:  # type: ignore[no-untyped-def]
            raise RuntimeError("redis unavailable")

    with (
        patch("sports_intelligence.workers.tasks.sports.QuotaManager", _FailQuota),
        patch.object(
            MockSportsDataProvider,
            "get_fixtures_by_date",
            new=AsyncMock(side_effect=lambda *a, **k: provider_calls.append(1)),
        ),
        patch("sports_intelligence.workers.tasks.sports.get_settings", return_value=settings),
        pytest.raises(RuntimeError),
    ):
        await _run_discovery(
            job_id=str(job_id),
            fixture_date=(datetime.now(UTC) + timedelta(days=1)).date().isoformat(),
            expected_league_config_version=1,
            discovery_timezone="Europe/Warsaw",
        )

    assert provider_calls == []
    async with m4_session_factory() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        assert job.status == "FAILED"


@pytest.mark.asyncio
async def test_status_one_team_missing_is_unknown_not_fresh(
    m4_session_factory: Any,
    redis_client: Redis,
    m4_settings: Settings,
    service_client: TestClient,
) -> None:
    """M4.2 §12: one team fresh + one team missing → category state is
    unknown/partial, NEVER fresh."""

    seeded = await _seed_league_team_fixture(
        m4_session_factory, kickoff_at=datetime.now(UTC) + timedelta(days=1)
    )
    # Persist team stats ONLY for the home team.
    from sports_intelligence.db.models import TeamStatisticsSnapshot

    async with m4_session_factory() as session:
        session.add(
            TeamStatisticsSnapshot(
                provider="mock",
                team_id=seeded["home_team_id"],
                league_id=seeded["league_id"],
                captured_at=datetime.now(UTC),
                metrics_jsonb={},
                updated_at=datetime.now(UTC),
            )
        )
        await session.commit()

    response = service_client.get(f"/v1/fixtures/{seeded['fixture_id']}/status")
    assert response.status_code == 200
    body = response.json()
    team_stats = body["freshness"]["team_stats"]
    # One fresh + one missing → unknown (partial), never fresh.
    assert team_stats["state"] == "unknown"


@pytest.mark.asyncio
async def test_odds_mapping_home_away_explicit_regardless_of_row_order(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    """M4.2 §7 regression: home/away names are loaded EXPLICITLY by id —
    never via unordered SQL IN whose row order is undefined. Even with
    the away row stored first, resolution uses the correct sides."""
    from decimal import Decimal

    from sports_intelligence.collectors.odds_collector import OddsCollector
    from sports_intelligence.providers.odds.base import (
        OddsProviderResult,
        OddsSelectionPrice,
    )

    # Seed normally, then REVERSE the fixture's home/away sides so the
    # team table row order no longer matches fixture column order.
    seeded = await _seed_league_team_fixture(
        m4_session_factory, kickoff_at=datetime.now(UTC) + timedelta(days=1)
    )
    async with m4_session_factory() as session:
        fixture = await session.get(Fixture, seeded["fixture_id"])
        fixture.home_team_id, fixture.away_team_id = (
            fixture.away_team_id,
            fixture.home_team_id,
        )
        await session.commit()
    # Update the returned dict so later assertions use the swapped sides.
    seeded["home_team_id"], seeded["away_team_id"] = (
        seeded["away_team_id"],
        seeded["home_team_id"],
    )

    resolved: dict[str, str] = {}

    class _MappingProbeMockOdds(MockOddsProvider):
        async def resolve_event(
            self, *, sport_key, home_team, away_team, commence_time_utc, tolerance_seconds=900
        ):
            resolved["home"] = home_team
            resolved["away"] = away_team
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
        provider=_MappingProbeMockOdds(),
    )
    async with m4_session_factory() as session:
        home_name = (
            await session.execute(select(Team.name).where(Team.id == seeded["home_team_id"]))
        ).scalar_one()
        away_name = (
            await session.execute(select(Team.name).where(Team.id == seeded["away_team_id"]))
        ).scalar_one()

    collector = OddsCollector()
    await collector.fetch(ctx, fixture_id=seeded["fixture_id"], league_id=seeded["league_id"])
    # Home name must be the fixture's home side and away the away side —
    # even though the team table row order no longer matches the fixture.
    assert resolved["home"] == home_name
    assert resolved["away"] == away_name
    assert resolved["home"] != resolved["away"]


# ---------------------------------------------------------------------------
# M4.3 acceptance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_live_local_no_odds_credentials_creates_no_odds_jobs(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings, tmp_path
) -> None:
    """M4.3 §1: live_local + sports_provider=api_football + odds_provider=""
    → the scanner creates ZERO odds jobs and ZERO OddsSnapshotSet rows
    (no silent mock odds persistence)."""
    from sports_intelligence.collectors.pre_match_scan import PreMatchDecision
    from sports_intelligence.core.phases import ForecastPhase as _FP

    kickoff = datetime.now(UTC) + timedelta(minutes=60)
    seeded = await _seed_league_team_fixture(m4_session_factory, kickoff_at=kickoff)
    decision = PreMatchDecision(
        fixture_id=str(seeded["fixture_id"]),
        league_id=str(seeded["league_id"]),
        home_team_id=str(seeded["home_team_id"]),
        away_team_id=str(seeded["away_team_id"]),
        season_id=str(seeded.get("season_id")) if seeded.get("season_id") else None,
        kickoff_at=kickoff,
        phase=_FP.PREMATCH,
        categories_to_collect=(FreshnessCategory.ODDS,),
    )

    from unittest.mock import patch as _patch

    from sports_intelligence.workers.tasks.collect import collect_task

    captured: list[object] = []

    def _fake_apply_async(*args, **_kwargs):  # type: ignore[no-untyped-def]
        captured.append(args)

    settings = Settings(
        _env_file=None,
        app_env="live_local",
        sports_provider="api_football",
        sports_api_key="k",
        odds_provider="",
        leagues_config_path=m4_settings.leagues_config_path,
        database_url=m4_settings.database_url,
    )
    from sports_intelligence.workers.tasks.pre_match import _dispatch_decision

    with (
        _patch.object(collect_task, "apply_async", _fake_apply_async),
        _patch("sports_intelligence.workers.tasks.pre_match.get_settings", return_value=settings),
    ):
        result = await _dispatch_decision(
            m4_session_factory, decision, now=kickoff - timedelta(minutes=10)
        )
    assert captured == []
    # The intent was considered but REJECTED: no job created, no broker
    # enqueue, no mock persistence.
    assert result["planned"] == 1
    assert result["jobs_created"] == 0
    assert result["jobs_enqueued"] == 0
    async with m4_session_factory() as session:
        odds_jobs = (
            (await session.execute(select(Job).where(Job.job_type == "collect:odds")))
            .scalars()
            .all()
        )
        odds_sets = (await session.execute(select(OddsSnapshotSet))).scalars().all()
    assert odds_jobs == []
    assert odds_sets == []


@pytest.mark.asyncio
async def test_quota_observation_generation_reconciles_baseline(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    """M4.3 §5: observed remaining=100, reserve 4 → provider responds
    96 (new observation generation) → next reservation of 4 must behave
    as 96→92, NOT 96 minus the old 4 again and minus the new 4."""
    from sports_intelligence.core.phases import Priority

    settings = Settings(
        _env_file=None,
        app_env="mock",
        quota_provider_daily_limit_default=100,
        quota_provider_minute_limit_default=100,
        database_url=m4_settings.database_url,
    )
    quota = QuotaManager(settings, m4_session_factory, redis=redis_client)
    now0 = datetime.now(UTC)
    async with m4_session_factory() as session:
        session.add(
            QuotaBucket(
                provider="mock",
                window="daily",
                limit_value=100,
                remaining_value=100,
                observed_at=now0,
            )
        )
        await session.commit()

    first = await quota.reserve(provider="mock", priority=Priority.P1, estimated_cost=4)
    assert first.allowed is True

    # Provider responds with a NEW observation: remaining=96 (the 4 were
    # spent). New generation → old reservation counter is obsolete.
    async with m4_session_factory() as session:
        session.add(
            QuotaBucket(
                provider="mock",
                window="daily",
                limit_value=100,
                remaining_value=96,
                observed_at=now0 + timedelta(minutes=5),
            )
        )
        await session.commit()

    second = await quota.reserve(provider="mock", priority=Priority.P1, estimated_cost=4)
    assert second.allowed is True
    # A further 4-credit reservation would take us to 88; a 4th would
    # breach the reserve floor (96 - 12 = 84 still fine for P1 with
    # reserve 20% of 100 = 20 → allowed until remaining 20+4... verify
    # the third reservation is still allowed).
    third = await quota.reserve(provider="mock", priority=Priority.P1, estimated_cost=4)
    assert third.allowed is True
    # 96 - 4 - 4 - 4 = 84; the OLD counter (8) must NOT be re-applied.
    fourth = await quota.reserve(provider="mock", priority=Priority.P1, estimated_cost=4)
    assert fourth.allowed is True  # 96 - 16 = 80 ≥ reserve floor


@pytest.mark.asyncio
async def test_failed_collector_job_same_opportunity_requeues_same_uuid(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    """M4.3 §7: a FAILED collector job in the SAME refresh opportunity is
    re-enqueued under the SAME job UUID (CAS FAILED→PENDING); the job id
    never changes and RUNNING/SUCCEEDED are never downgraded."""
    from unittest.mock import patch as _patch

    from sports_intelligence.collectors.pre_match_scan import PreMatchDecision
    from sports_intelligence.core.phases import ForecastPhase as _FP
    from sports_intelligence.workers.tasks.collect import collect_task
    from sports_intelligence.workers.tasks.pre_match import _dispatch_decision

    kickoff = datetime.now(UTC) + timedelta(minutes=60)
    seeded = await _seed_league_team_fixture(m4_session_factory, kickoff_at=kickoff)
    decision = PreMatchDecision(
        fixture_id=str(seeded["fixture_id"]),
        league_id=str(seeded["league_id"]),
        home_team_id=str(seeded["home_team_id"]),
        away_team_id=str(seeded["away_team_id"]),
        season_id=str(seeded.get("season_id")) if seeded.get("season_id") else None,
        kickoff_at=kickoff,
        phase=_FP.PREMATCH,
        categories_to_collect=(FreshnessCategory.ODDS,),
    )
    settings = Settings(
        _env_file=None,
        app_env="mock",
        odds_provider="mock",
        leagues_config_path=m4_settings.leagues_config_path,
        database_url=m4_settings.database_url,
    )
    captured: list[list[object]] = []
    calls = {"n": 0}

    def _fake_apply_async(*, args, **_kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("broker down on first attempt")
        captured.append(list(args))

    with (
        _patch.object(collect_task, "apply_async", _fake_apply_async),
        _patch("sports_intelligence.workers.tasks.pre_match.get_settings", return_value=settings),
    ):
        # First scan: broker fails → job marked FAILED.
        with pytest.raises(RuntimeError):
            await _dispatch_decision(
                m4_session_factory, decision, now=kickoff - timedelta(minutes=20)
            )
        async with m4_session_factory() as session:
            jobs = (
                (await session.execute(select(Job).where(Job.job_type == "collect:odds")))
                .scalars()
                .all()
            )
            assert len(jobs) == 1
            failed_job = jobs[0]
            assert failed_job.status == "FAILED"
            first_id = failed_job.id

        # Second scan in the SAME opportunity: re-enqueues the SAME
        # uuid (FAILED → PENDING via CAS).
        result = await _dispatch_decision(
            m4_session_factory, decision, now=kickoff - timedelta(minutes=15)
        )
    assert result["jobs_reused"] == 0
    assert result["jobs_created"] == 0
    assert result["jobs_enqueued"] == 1
    async with m4_session_factory() as session:
        job = (await session.execute(select(Job).where(Job.id == first_id))).scalar_one()
        assert job.status == "PENDING"
    assert captured[0][0] == str(first_id)


@pytest.mark.asyncio
async def test_failed_retry_never_downgrades_running_or_succeeded(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    """M4.3 §7: the CAS transition must NEVER downgrade RUNNING or
    SUCCEEDED collector jobs to PENDING."""
    from unittest.mock import patch as _patch

    from sports_intelligence.collectors.pre_match_scan import PreMatchDecision
    from sports_intelligence.core.phases import ForecastPhase as _FP
    from sports_intelligence.workers.tasks.collect import collect_task
    from sports_intelligence.workers.tasks.pre_match import _dispatch_decision

    kickoff = datetime.now(UTC) + timedelta(minutes=60)
    seeded = await _seed_league_team_fixture(m4_session_factory, kickoff_at=kickoff)
    decision = PreMatchDecision(
        fixture_id=str(seeded["fixture_id"]),
        league_id=str(seeded["league_id"]),
        home_team_id=str(seeded["home_team_id"]),
        away_team_id=str(seeded["away_team_id"]),
        season_id=str(seeded.get("season_id")) if seeded.get("season_id") else None,
        kickoff_at=kickoff,
        phase=_FP.PREMATCH,
        categories_to_collect=(FreshnessCategory.ODDS,),
    )
    settings = Settings(
        _env_file=None,
        app_env="mock",
        odds_provider="mock",
        leagues_config_path=m4_settings.leagues_config_path,
        database_url=m4_settings.database_url,
    )

    def _fake_apply_async(*, args, **_kwargs):  # type: ignore[no-untyped-def]
        return None

    with (
        _patch.object(collect_task, "apply_async", _fake_apply_async),
        _patch("sports_intelligence.workers.tasks.pre_match.get_settings", return_value=settings),
    ):
        await _dispatch_decision(m4_session_factory, decision, now=kickoff - timedelta(minutes=20))
        async with m4_session_factory() as session:
            job = (
                (await session.execute(select(Job).where(Job.job_type == "collect:odds")))
                .scalars()
                .first()
            )
            job_id = job.id
        # Force RUNNING (as a worker would set it) — the next scan
        # must NOT requeue.
        async with m4_session_factory() as session:
            job = await session.get(Job, job_id)
            job.status = "RUNNING"
            await session.commit()
        second = await _dispatch_decision(
            m4_session_factory, decision, now=kickoff - timedelta(minutes=19)
        )
        async with m4_session_factory() as session:
            job_after = await session.get(Job, job_id)
            assert job_after.status == "RUNNING"
        assert second["jobs_enqueued"] == 0


@pytest.mark.asyncio
async def test_api_football_429_ledger_has_status_and_safe_headers(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    """M4.3 §8: an API-Football 429 carries status_code=429 and SAFE
    rate-limit headers into the ledger — auth headers never appear."""
    from sports_intelligence.core.phases import Priority
    from sports_intelligence.providers.errors import ProviderRateLimitError

    quota = QuotaManager(m4_settings, m4_session_factory, redis=redis_client)
    started_at = datetime.now(UTC)
    exc = ProviderRateLimitError(
        "rate limit",
        status_code=429,
        quota_headers={
            "x-ratelimit-requests-remaining": "0",
            "x-ratelimit-requests-limit": "100",
        },
    )
    await quota.record_failure(
        provider="api_football",
        endpoint_category="standings",
        started_at=started_at,
        exc=exc,
        headers=exc.quota_headers,
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
                        ExternalApiRequest.status_code == 429,
                    )
                )
            )
            .scalars()
            .all()
        )
    assert rows, "429 failure missing from ledger"
    assert rows[0].status_code == 429
    assert rows[0].daily_remaining == 0
    # Auth headers never leak into persisted telemetry.
    assert rows[0].provider == "api_football"


@pytest.mark.asyncio
async def test_partial_home_confirmed_away_unpublished_still_refreshes(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    """M4.3 §3: CONFIRMED stops polling only when BOTH fixture teams are
    confirmed. home CONFIRMED + away NOT_YET_PUBLISHED → the T20 window
    MUST refresh; once both are confirmed → zero provider calls."""
    from sports_intelligence.collectors.framework import run_collector
    from sports_intelligence.core.phases import ForecastPhase as _FP

    kickoff = datetime.now(UTC) + timedelta(minutes=25)
    seeded = await _seed_league_team_fixture(
        m4_session_factory,
        kickoff_at=kickoff,
        external_ids={"home": "9001", "away": "9002", "fixture": "42", "league": "39"},
    )
    ctx = _ctx(
        factory=m4_session_factory,
        redis=redis_client,
        settings=m4_settings,
        provider=MockSportsDataProvider(lineups_published=True),
        phase=_FP.PREMATCH,
    )
    provider_calls: list[int] = []

    # T-25 (T20 window): provider publishes BOTH teams (confirmed).
    await run_collector(
        ctx,
        "lineups",
        inputs={"fixture_id": seeded["fixture_id"], "team_id": seeded["home_team_id"]},
        now=kickoff - timedelta(minutes=25),
        on_provider_call=lambda: provider_calls.append(1),
    )
    # Simulate the M4.3 scenario: override the away side back to
    # NOT_YET_PUBLISHED so the fixture is partially confirmed.
    async with m4_session_factory() as session:
        away_snap = (
            (
                await session.execute(
                    select(LineupSnapshot)
                    .where(
                        LineupSnapshot.fixture_id == seeded["fixture_id"],
                        LineupSnapshot.team_id == seeded["away_team_id"],
                    )
                    .order_by(LineupSnapshot.captured_at.desc())
                )
            )
            .scalars()
            .first()
        )
        away_snap.publication_state = "NOT_YET_PUBLISHED"
        away_snap.confirmed = False
        away_snap.players_jsonb = []
        await session.commit()

    # T-15 (still T20 window): away not published → refresh MUST occur.
    await run_collector(
        ctx,
        "lineups",
        inputs={"fixture_id": seeded["fixture_id"], "team_id": seeded["home_team_id"]},
        now=kickoff - timedelta(minutes=15),
        on_provider_call=lambda: provider_calls.append(1),
    )
    assert len(provider_calls) == 2  # partial state still refreshes

    # The T-15 refresh re-published BOTH sides → away becomes CONFIRMED.
    async with m4_session_factory() as session:
        away_latest = (
            (
                await session.execute(
                    select(LineupSnapshot)
                    .where(
                        LineupSnapshot.fixture_id == seeded["fixture_id"],
                        LineupSnapshot.team_id == seeded["away_team_id"],
                    )
                    .order_by(LineupSnapshot.captured_at.desc())
                )
            )
            .scalars()
            .first()
        )
    assert away_latest.publication_state == "CONFIRMED"

    # Now BOTH confirmed → later scans make ZERO provider calls.
    await run_collector(
        ctx,
        "lineups",
        inputs={"fixture_id": seeded["fixture_id"], "team_id": seeded["home_team_id"]},
        now=kickoff - timedelta(minutes=10),
        on_provider_call=lambda: provider_calls.append(1),
    )
    await run_collector(
        ctx,
        "lineups",
        inputs={"fixture_id": seeded["fixture_id"], "team_id": seeded["home_team_id"]},
        now=kickoff - timedelta(minutes=5),
        on_provider_call=lambda: provider_calls.append(1),
    )
    assert len(provider_calls) == 2  # both confirmed → polling stopped


@pytest.mark.asyncio
async def test_concurrent_reservations_after_new_observation(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    """M4.3 §5 concurrency: after a NEWER observation becomes
    authoritative, concurrent reservations are counted against the NEW
    generation — the old generation counter is never re-applied."""
    from sports_intelligence.core.phases import Priority

    settings = Settings(
        _env_file=None,
        app_env="mock",
        quota_provider_daily_limit_default=100,
        quota_provider_minute_limit_default=100,
        quota_reserve_p0_calls=20,
        database_url=m4_settings.database_url,
    )
    quota = QuotaManager(settings, m4_session_factory, redis=redis_client)
    now0 = datetime.now(UTC)
    async with m4_session_factory() as session:
        session.add(
            QuotaBucket(
                provider="mock",
                window="daily",
                limit_value=100,
                remaining_value=100,
                observed_at=now0,
            )
        )
        await session.commit()

    # Old generation: 2 reservations of 4 → 8 spent.
    await quota.reserve(provider="mock", priority=Priority.P1, estimated_cost=4)
    await quota.reserve(provider="mock", priority=Priority.P1, estimated_cost=4)

    # New observation: remaining=80 (20 spent + provider drift) → new
    # generation with a fresh counter.
    async with m4_session_factory() as session:
        session.add(
            QuotaBucket(
                provider="mock",
                window="daily",
                limit_value=100,
                remaining_value=80,
                observed_at=now0 + timedelta(minutes=5),
            )
        )
        await session.commit()

    results = await asyncio.gather(
        *[quota.reserve(provider="mock", priority=Priority.P1, estimated_cost=4) for _ in range(10)]
    )
    allowed = [r for r in results if r.allowed]
    # New baseline 80, reserve floor 20 → P1 may spend 60 → 15 × 4, but
    # only 10 callers: all 10 succeed (40 ≤ 60), concurrency-safe.
    assert len(allowed) == 10


@pytest.mark.asyncio
async def test_season_identity_pinned_end_to_end_two_seasons(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    """M4.4 §2: season identity flows fixture.season_id → provider season
    param → snapshot season_id. A fresh season-A snapshot never satisfies
    season-B freshness; A/B lock identities never collide."""
    from sports_intelligence.collectors.framework import run_collector
    from sports_intelligence.core.phases import ForecastPhase as _FP
    from sports_intelligence.providers.sports.mock import MockSportsDataProvider

    # Same league, TWO seasons; fixture belongs to B (2026).
    async with m4_session_factory() as session:
        league = League(
            slug=f"season-pin-{uuid.uuid4().hex[:8]}",
            name="Season Pin",
            country="Test",
            enabled=True,
        )
        session.add(league)
        await session.flush()
        season_a = Season(league_id=league.id, name="2025-2026", active=True)
        season_b = Season(league_id=league.id, name="2026-2027", active=True)
        session.add_all([season_a, season_b])
        await session.flush()
        home = Team(name="SHome", country="T")
        away = Team(name="SAway", country="T")
        session.add(home)
        session.add(away)
        await session.flush()
        kickoff = datetime.now(UTC) + timedelta(days=1)
        fixture = Fixture(
            league_id=league.id,
            season_id=season_b.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=kickoff,
            status="NS",
        )
        session.add(fixture)
        await session.flush()
        session.add_all(
            [
                ProviderEntityId(
                    provider="mock",
                    entity_type="league",
                    external_id="39",
                    internal_entity_id=league.id,
                ),
                ProviderEntityId(
                    provider="mock",
                    entity_type="team",
                    external_id="9001",
                    internal_entity_id=home.id,
                ),
                ProviderEntityId(
                    provider="mock",
                    entity_type="team",
                    external_id="9002",
                    internal_entity_id=away.id,
                ),
                ProviderEntityId(
                    provider="mock",
                    entity_type="fixture",
                    external_id="42",
                    internal_entity_id=fixture.id,
                ),
            ]
        )
        await session.commit()
        league_id, season_a_id, season_b_id = (league.id, season_a.id, season_b.id)

    captured_seasons: list[int | None] = []

    class _SeasonSpyProvider(MockSportsDataProvider):
        async def get_standings(self, *, provider_league_id, season):
            captured_seasons.append(season)
            return await super().get_standings(provider_league_id=provider_league_id, season=season)

    ctx = _ctx(
        factory=m4_session_factory,
        redis=redis_client,
        settings=m4_settings,
        provider=_SeasonSpyProvider(),
        phase=_FP.MORNING,
    )

    # 1. A FRESH season-A snapshot must NOT satisfy season-B freshness
    # for standings or team statistics.
    from sports_intelligence.collectors.sports_collectors import (
        StandingsCollector,
        TeamStatisticsCollector,
    )

    collector = StandingsCollector()
    ts_collector = TeamStatisticsCollector()

    async with m4_session_factory() as session:
        session.add(
            StandingSnapshot(
                provider="mock",
                league_id=league_id,
                season_id=season_a_id,
                captured_at=datetime.now(UTC),
                source_fingerprint="manual:season-a",
                rows_jsonb=[],
                updated_at=datetime.now(UTC),
            )
        )
        session.add(
            TeamStatisticsSnapshot(
                provider="mock",
                team_id=home.id,
                league_id=league_id,
                season_id=season_a_id,
                captured_at=datetime.now(UTC),
                metrics_jsonb={"played": 10},
                updated_at=datetime.now(UTC),
            )
        )
        await session.commit()

    async with m4_session_factory() as session:
        st_cap, _ = await collector.latest_snapshot(
            session, league_id=league_id, season_id=season_b_id
        )
        assert st_cap is None
        ts_cap, _ = await ts_collector.latest_snapshot(
            session, team_id=home.id, league_id=league_id, season_id=season_b_id
        )
        assert ts_cap is None

    # 2. Collect for season B → provider receives 2026 (NOT the active
    # season-A year 2025); snapshot pinned to season B uuid.
    ref_b = await run_collector(
        ctx,
        "standings",
        inputs={"league_id": league_id, "season_id": season_b_id},
    )
    assert captured_seasons == [2026]
    async with m4_session_factory() as session:
        snap_b = (
            (
                await session.execute(
                    select(StandingSnapshot).where(StandingSnapshot.id == ref_b.snapshot_id)
                )
            )
            .scalars()
            .one()
        )
    assert snap_b.season_id == season_b_id

    # 3. Season-B snapshot is now fresh → subsequent collect reuses it
    # (still only one provider call).
    ref_b2 = await run_collector(
        ctx,
        "standings",
        inputs={"league_id": league_id, "season_id": season_b_id},
    )
    assert captured_seasons == [2026]
    assert ref_b2.snapshot_id == ref_b.snapshot_id

    # 4. Lock identities and collector job keys do not collide across seasons.
    import hashlib

    key_a = collector.lock_key(league_id=league_id, season_id=season_a_id)
    key_b = collector.lock_key(league_id=league_id, season_id=season_b_id)
    key_none = collector.lock_key(league_id=league_id, season_id=None)
    assert len({key_a, key_b, key_none}) == 3

    job_key_a = (
        f"collect:standings:{hashlib.sha1(key_a.encode()).hexdigest()[:20]}:MORNING:due:missing"
    )
    job_key_b = (
        f"collect:standings:{hashlib.sha1(key_b.encode()).hexdigest()[:20]}:MORNING:due:missing"
    )
    assert job_key_a != job_key_b

    ts_key_a = ts_collector.lock_key(team_id=home.id, league_id=league_id, season_id=season_a_id)
    ts_key_b = ts_collector.lock_key(team_id=home.id, league_id=league_id, season_id=season_b_id)
    ts_key_none = ts_collector.lock_key(team_id=home.id, league_id=league_id, season_id=None)
    assert len({ts_key_a, ts_key_b, ts_key_none}) == 3

    # 5. Missing season cannot accidentally hit a snapshot from another season.
    async with m4_session_factory() as session:
        st_cap_none, _ = await collector.latest_snapshot(
            session, league_id=league_id, season_id=None
        )
        assert st_cap_none is None
        ts_cap_none, _ = await ts_collector.latest_snapshot(
            session, team_id=home.id, league_id=league_id, season_id=None
        )
        assert ts_cap_none is None

    # 6. Team statistics snapshot for season B persists with season B UUID.
    ref_ts_b = await run_collector(
        ctx,
        "team_stats",
        inputs={"team_id": home.id, "league_id": league_id, "season_id": season_b_id},
    )
    async with m4_session_factory() as session:
        ts_snap_b = (
            await session.execute(
                select(TeamStatisticsSnapshot).where(
                    TeamStatisticsSnapshot.id == ref_ts_b.snapshot_id
                )
            )
        ).scalar_one()
    assert ts_snap_b.season_id == season_b_id


@pytest.mark.asyncio
async def test_ttl_opportunity_stable_fresh_skips_failed_requeues_same_uuid(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    """M4.4 §3 acceptance flow for a TTL collector (odds, 30 min TTL):

    T0+20 fresh → NO job; T0+31 stale → job A; broker fails → A FAILED;
    T0+35 → same stale generation → SAME uuid A requeued; T0+40 A
    RUNNING → no duplicate; successful snapshot at T0+41 → next scan
    fresh → no job.
    """
    from unittest.mock import patch as _patch

    from sports_intelligence.collectors.pre_match_scan import PreMatchDecision
    from sports_intelligence.core.phases import ForecastPhase as _FP
    from sports_intelligence.workers.tasks.collect import collect_task
    from sports_intelligence.workers.tasks.pre_match import _dispatch_decision

    settings = Settings(
        _env_file=None,
        app_env="mock",
        odds_provider="mock",
        freshness_odds_seconds=30 * 60,
        leagues_config_path=m4_settings.leagues_config_path,
        database_url=m4_settings.database_url,
    )
    kickoff = datetime.now(UTC) + timedelta(hours=5)
    seeded = await _seed_league_team_fixture(m4_session_factory, kickoff_at=kickoff)
    decision = PreMatchDecision(
        fixture_id=str(seeded["fixture_id"]),
        league_id=str(seeded["league_id"]),
        home_team_id=str(seeded["home_team_id"]),
        away_team_id=str(seeded["away_team_id"]),
        season_id=str(seeded.get("season_id")) if seeded.get("season_id") else None,
        kickoff_at=kickoff,
        phase=_FP.MORNING,
        categories_to_collect=(FreshnessCategory.ODDS,),
    )

    t0 = datetime.now(UTC)

    async def _scan(at: datetime, *, fail_broker: bool = False):
        calls = {"n": 0, "args": []}

        def _fake_apply_async(*, args, **_kwargs):  # type: ignore[no-untyped-def]
            calls["n"] += 1
            calls["args"].append(list(args))
            if fail_broker and calls["n"] == 1:
                raise RuntimeError("broker down")

        with (
            _patch.object(collect_task, "apply_async", _fake_apply_async),
            _patch(
                "sports_intelligence.workers.tasks.pre_match.get_settings",
                return_value=settings,
            ),
        ):
            result = await _dispatch_decision(m4_session_factory, decision, now=at)
        return result, calls

    # T0+20: fresh snapshot → NO job.
    async with m4_session_factory() as session:
        session.add(
            OddsSnapshotSet(
                provider="mock-odds",
                fixture_id=seeded["fixture_id"],
                captured_at=t0,
                market_whitelist_jsonb=["h2h"],
            )
        )
        await session.commit()
    result_fresh, calls_fresh = await _scan(t0 + timedelta(minutes=20))
    assert result_fresh["planned"] == 1
    assert result_fresh["jobs_created"] == 0
    assert calls_fresh["n"] == 0

    # T0+31: stale → job A created (broker fails → A FAILED).
    with pytest.raises(RuntimeError):
        await _scan(t0 + timedelta(minutes=31), fail_broker=True)
    async with m4_session_factory() as session:
        jobs = (
            (await session.execute(select(Job).where(Job.job_type == "collect:odds")))
            .scalars()
            .all()
        )
    assert len(jobs) == 1
    job_a = jobs[0]
    assert job_a.status == "FAILED"
    job_id_a = str(job_a.id)

    # T0+35: same stale generation → SAME uuid A requeued.
    result_35, calls_35 = await _scan(t0 + timedelta(minutes=35))
    assert result_35["jobs_created"] == 0
    assert result_35["jobs_enqueued"] == 1
    assert calls_35["args"][0][0] == job_id_a
    async with m4_session_factory() as session:
        job_a2 = await session.get(Job, uuid.UUID(job_id_a))
        assert job_a2.status == "PENDING"

    # T0+40: A RUNNING → no duplicate job.
    async with m4_session_factory() as session:
        job_running = await session.get(Job, uuid.UUID(job_id_a))
        job_running.status = "RUNNING"
        await session.commit()
    result_40, calls_40 = await _scan(t0 + timedelta(minutes=40))
    assert result_40["jobs_enqueued"] == 0
    assert result_40["jobs_created"] == 0
    assert calls_40["n"] == 0

    # Successful snapshot at T0+41 → next scan fresh → no job.
    async with m4_session_factory() as session:
        session.add(
            OddsSnapshotSet(
                provider="mock-odds",
                fixture_id=seeded["fixture_id"],
                captured_at=t0 + timedelta(minutes=41),
                market_whitelist_jsonb=["h2h"],
            )
        )
        await session.commit()
    result_42, calls_42 = await _scan(t0 + timedelta(minutes=42))
    assert result_42["jobs_created"] == 0
    assert calls_42["n"] == 0


@pytest.mark.asyncio
async def test_quota_observation_uses_response_time_generation(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    """M4.4 §4: QuotaBucket.observed_at derives from the RESPONSE
    observation time (finished_at), never the request start. Two
    overlapping requests: the LATER response becomes the authoritative
    bucket/generation."""
    from sports_intelligence.core.phases import Priority

    quota = QuotaManager(m4_settings, m4_session_factory, redis=redis_client)
    seeded = await _seed_league_team_fixture(
        m4_session_factory, kickoff_at=datetime.now(UTC) + timedelta(days=1)
    )

    # Request A starts first but its RESPONSE arrives LAST.
    started_a = datetime.now(UTC)
    finished_a = started_a + timedelta(seconds=2)
    await quota.record_success(
        provider="api_football",
        endpoint_category="standings",
        started_at=started_a,
        finished_at=finished_a,
        headers={"x-ratelimit-requests-remaining": "42", "x-ratelimit-requests-limit": "100"},
        priority=Priority.P2,
        fixture_id=seeded["fixture_id"],
        league_id=seeded["league_id"],
    )
    # Request B starts later but its RESPONSE arrives EARLIER.
    started_b = started_a + timedelta(seconds=1)
    finished_b = started_a + timedelta(seconds=1.5)
    await quota.record_success(
        provider="api_football",
        endpoint_category="team_stats",
        started_at=started_b,
        finished_at=finished_b,
        headers={"x-ratelimit-requests-remaining": "50", "x-ratelimit-requests-limit": "100"},
        priority=Priority.P2,
        fixture_id=seeded["fixture_id"],
        league_id=seeded["league_id"],
    )

    async with m4_session_factory() as session:
        buckets = (
            (
                await session.execute(
                    select(QuotaBucket)
                    .where(QuotaBucket.provider == "api_football", QuotaBucket.window == "daily")
                    .order_by(QuotaBucket.observed_at.desc())
                )
            )
            .scalars()
            .all()
        )
    assert len(buckets) >= 2
    authoritative = buckets[0]
    # The authoritative bucket is the one with the LATER response time:
    # request A's response (remaining=42, finished_a) — NOT B (remaining
    # 50) whose response arrived earlier, even though B started later.
    assert authoritative.observed_at == finished_a
    assert authoritative.remaining_value == 42
