"""M4 — automated match-data collection, odds, quota/freshness (integration).

These tests exercise the M4 stack against real PostgreSQL + Redis:

- collectors persist snapshots (standings, team stats, availability,
  lineups, odds) via the run_collector pipeline;
- standings are shared by multiple fixtures for the same league;
- quota ledger records every external request;
- pre-match scan plans idempotently;
- status API endpoints surface fresh data from PostgreSQL;
- GET endpoints never trigger external provider calls (DB-first UX);
- the discovery task records `job_attempts` rows on success.
"""

from __future__ import annotations

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
import sports_intelligence.collectors.sports_collectors  # noqa: F401  — registers collectors
from sports_intelligence.collectors.framework import (
    CollectorContext,
    CollectorResult,
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
    LineupSnapshot,
    OddsPrice,
    OddsSnapshotSet,
    QuotaBucket,
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
async def m4_settings(service_settings: Settings) -> Settings:
    return service_settings


@pytest.fixture
async def m4_engine(m4_settings: Settings) -> Iterator[Any]:
    engine = create_engine(m4_settings.database_url)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def m4_session_factory(m4_settings: Settings) -> Iterator[Any]:
    factory = create_session_factory(create_engine(m4_settings.database_url))
    try:
        yield factory
    finally:
        await factory().close()
        engine = create_engine(m4_settings.database_url)
        await engine.dispose()


@pytest.fixture
async def redis_client(m4_settings: Settings) -> Iterator[Redis]:
    client = Redis.from_url(m4_settings.redis_url)
    try:
        yield client
    finally:
        await client.aclose()


async def _seed_league_team_fixture(
    factory: Any,
    *,
    kickoff_at: datetime,
    with_season: bool = True,
    slug_suffix: str = "",
    league_id: uuid.UUID | None = None,
    season_id: uuid.UUID | None = None,
) -> dict[str, uuid.UUID]:
    """Create a league + season + two teams + one fixture. The league is
    enabled in the YAML config so collectors and the discovery task see it.

    If `league_id` is supplied, the league (and optionally season) are
    reused — useful for standings-shared-across-multiple-fixtures tests.
    """
    slug = f"integration-m4-{slug_suffix or uuid.uuid4().hex[:8]}"
    async with factory() as session:
        if league_id is None:
            league = League(
                slug=slug, name=f"Integration M4 {slug_suffix}", country="Test", enabled=True
            )
            session.add(league)
            await session.flush()
            league_id = league.id
        if with_season and season_id is None:
            season = Season(league_id=league_id, name="2026-2027", active=True)
            session.add(season)
            await session.flush()
            season_id = season.id
        home = Team(name=f"Arsenal M4-{slug_suffix}-{uuid.uuid4().hex[:6]}", country="Test")
        away = Team(name=f"Coventry M4-{slug_suffix}-{uuid.uuid4().hex[:6]}", country="Test")
        session.add(home)
        session.add(away)
        await session.flush()
        fixture = Fixture(
            league_id=league_id,
            season_id=season_id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=kickoff_at,
            status="NS",
        )
        session.add(fixture)
        await session.commit()
        return {
            "league_id": league_id,
            "season_id": season_id if season_id is not None else uuid.uuid4(),
            "home_team_id": home.id,
            "away_team_id": away.id,
            "fixture_id": fixture.id,
        }


def _ctx(*, factory: Any, redis: Redis, settings: Settings, provider: Any) -> CollectorContext:
    locks = CoalesceLockManager(redis, settings)
    quota = QuotaManager(settings, factory)
    return CollectorContext(
        provider=provider,
        quota=quota,
        locks=locks,
        freshness=FreshnessPolicy(settings),
        session_factory=factory,
        settings=settings,
        redis=redis,
        phase=ForecastPhase.PREMATCH,
    )


@pytest.mark.asyncio
async def test_standings_collector_persists_snapshot(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    seeded = await _seed_league_team_fixture(
        m4_session_factory,
        kickoff_at=datetime.now(UTC) + timedelta(days=1),
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
    assert rows[0].captured_at is not None
    assert ref.captured_at is not None
    # Ledger: at least one external request recorded for `standings`.
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
    assert ledger, "external_api_requests ledger row missing for standings"


@pytest.mark.asyncio
async def test_standings_shared_across_multiple_fixtures(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    """Two upcoming fixtures in the same league → standings fetched
    exactly once (coalesced via Redis lock + freshness policy)."""
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
    assert seeded_a["league_id"] == seeded_b["league_id"]
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
    # Two runs of run_collector, but the second is fresh because the
    # first persisted a snapshot within TTL: only the first emits a
    # provider call (recorded in the ledger as exactly one row).
    assert len(ledger) == 1


@pytest.mark.asyncio
async def test_lineup_collector_persists_unconfirmed_with_empty_players(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    """Lineup unavailable != empty lineup: persist keeps confirmed=False
    and players=[] instead of collapsing into None. We exercise the
    MOCK home and away paths and check both states round-trip."""
    seeded = await _seed_league_team_fixture(
        m4_session_factory, kickoff_at=datetime.now(UTC) + timedelta(minutes=20)
    )
    ctx = _ctx(
        factory=m4_session_factory,
        redis=redis_client,
        settings=m4_settings,
        provider=_recorded_provider(),
    )
    await run_collector(
        ctx,
        "lineups",
        inputs={"fixture_id": seeded["fixture_id"], "team_id": seeded["home_team_id"]},
    )
    async with m4_session_factory() as session:
        snapshots = (
            (
                await session.execute(
                    select(LineupSnapshot).where(LineupSnapshot.fixture_id == seeded["fixture_id"])
                )
            )
            .scalars()
            .all()
        )
    assert len(snapshots) == 1
    # The home side of the MOCK fixture-mock-1 is confirmed=True with
    # named starters; persistence must round-trip both the boolean and
    # the players list.
    home = snapshots[0]
    assert home.confirmed is True
    assert home.formation == "4-3-3"
    assert len(home.players_jsonb) >= 11

    # Persist a separate away lineup with the documented "not yet
    # published" shape: confirmed=False, players=[] — collect persist
    # must NOT collapse this into None.
    from sports_intelligence.collectors.sports_collectors import LineupCollector

    collector = LineupCollector()
    result = CollectorResult(
        raw_payload=None,
        normalized={"confirmed": False, "formation": None, "players": []},
    )
    await collector.persist(
        ctx,
        result,
        captured_at=datetime.now(UTC),
        source_fingerprint="mock:lineups:away-unconfirmed",
        fixture_id=seeded["fixture_id"],
        team_id=seeded["away_team_id"],
    )
    async with m4_session_factory() as session:
        away = (
            (
                await session.execute(
                    select(LineupSnapshot).where(
                        LineupSnapshot.fixture_id == seeded["fixture_id"],
                        LineupSnapshot.team_id == seeded["away_team_id"],
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(away) == 1
    assert away[0].confirmed is False
    assert away[0].players_jsonb == []
    assert away[0].formation is None


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
        async def fetch_odds(self, *, fixture_id, markets, regions):
            return OddsProviderResult(
                provider=self.name,
                fixture_id=fixture_id,
                captured_at="2026-08-21T10:00:00+00:00",
                prices=(
                    OddsSelectionPrice(
                        bookmaker="mockbookie",
                        market="h2h_1x2",
                        selection="home",
                        line=None,
                        decimal_odds=Decimal("2.10"),
                    ),
                    OddsSelectionPrice(
                        bookmaker="mockbookie",
                        market="h2h_1x2",
                        selection="draw",
                        line=None,
                        decimal_odds=Decimal("3.40"),
                    ),
                    OddsSelectionPrice(
                        bookmaker="mockbookie",
                        market="h2h_1x2",
                        selection="away",
                        line=None,
                        decimal_odds=Decimal("3.60"),
                    ),
                ),
            )

    ctx = _ctx(
        factory=m4_session_factory,
        redis=redis_client,
        settings=m4_settings,
        provider=_UuidAwareMockOdds(),
    )
    await run_collector(
        ctx,
        "odds",
        inputs={"fixture_id": seeded["fixture_id"]},
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
    # All three 1X2 selections must be present (no-vig derived).
    selections = {p.selection for p in prices}
    assert selections == {"home", "draw", "away"}


@pytest.mark.asyncio
async def test_odds_history_is_immutable_across_runs(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    """Two consecutive odds runs preserve both snapshots — history is
    immutable; nothing is overwritten."""
    seeded = await _seed_league_team_fixture(
        m4_session_factory, kickoff_at=datetime.now(UTC) + timedelta(days=1)
    )
    ctx = _ctx(
        factory=m4_session_factory,
        redis=redis_client,
        settings=m4_settings,
        provider=MockOddsProvider(),
    )
    await run_collector(ctx, "odds", inputs={"fixture_id": seeded["fixture_id"]})
    # Force a fresh captured_at on the second run by skipping the cache:
    # we re-run the fetch directly so persistence produces a new
    # snapshot_set rather than coalescing into the cached one.
    from sports_intelligence.collectors.odds_collector import OddsCollector

    collector = OddsCollector()
    captured_at = datetime.now(UTC) + timedelta(seconds=1)
    result = await collector.fetch(ctx, fixture_id=seeded["fixture_id"])
    await collector.persist(
        ctx,
        result,
        captured_at=captured_at,
        source_fingerprint="manual:odds:second",
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
    captured_ats = sorted(s.captured_at for s in sets)
    assert captured_ats[1] > captured_ats[0]


@pytest.mark.asyncio
async def test_quota_record_persists_buckets_and_external_requests(
    m4_session_factory: Any, redis_client: Redis, m4_settings: Settings
) -> None:
    from sports_intelligence.collectors.quota import parse_provider_headers

    headers = {
        "x-ratelimit-requests-remaining": "99",
        "x-ratelimit-requests-limit": "100",
        "x-ratelimit-minutes-remaining": "5",
    }
    parsed = parse_provider_headers(headers)
    quota = QuotaManager(m4_settings, m4_session_factory)
    started_at = datetime.now(UTC)
    seeded = await _seed_league_team_fixture(
        m4_session_factory,
        kickoff_at=datetime.now(UTC) + timedelta(days=1),
    )
    await quota.record(
        provider="mock",
        endpoint_category="standings",
        fixture_id=None,
        league_id=seeded["league_id"],
        started_at=started_at,
        duration_ms=42,
        status_code=200,
        cache_hit=False,
        headers=headers,
        priority=__import__("sports_intelligence.core.phases", fromlist=["Priority"]).Priority.P2,
    )
    async with m4_session_factory() as session:
        ext = (
            (
                await session.execute(
                    select(ExternalApiRequest).where(
                        ExternalApiRequest.endpoint_category == "standings"
                    )
                )
            )
            .scalars()
            .all()
        )
        buckets = (
            (await session.execute(select(QuotaBucket).where(QuotaBucket.provider == "mock")))
            .scalars()
            .all()
        )
    assert ext, "external_api_requests row missing after quota.record"
    assert buckets, "quota_buckets rows missing after quota.record"
    # The daily bucket parsed the header correctly.
    daily = next((b for b in buckets if b.window == "daily"), None)
    assert daily is not None
    assert daily.remaining_value == parsed.daily_remaining


@pytest.mark.asyncio
async def test_discovery_task_records_job_attempt_on_success(
    m4_session_factory: Any, m4_settings: Settings, tmp_path
) -> None:
    """Worker executions MUST record a `job_attempts` row (closes the
    deferred M4 debt). We test the recording pathway directly via the
    `record_job_attempt` helper used by `_run_discovery` — the higher
    level worker task is covered by the existing M2 integration tests.
    """
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

    started_at = datetime.now(UTC)
    finished_at = started_at + timedelta(seconds=2)
    from sports_intelligence.workers.utils import record_job_attempt

    await record_job_attempt(
        m4_session_factory,
        job_id=job_id,
        attempt_number=1,
        started_at=started_at,
        finished_at=finished_at,
        outcome="SUCCEEDED",
        error=None,
    )

    async with m4_session_factory() as session:
        attempts = (
            (await session.execute(select(JobAttempt).where(JobAttempt.job_id == job_id)))
            .scalars()
            .all()
        )
    assert len(attempts) == 1
    attempt = attempts[0]
    assert attempt.status == "SUCCEEDED"
    assert attempt.error_class is None
    assert attempt.worker and attempt.worker != ""  # hostname:pid format
    assert attempt.started_at == started_at
    assert attempt.finished_at == finished_at


@pytest.mark.asyncio
async def test_status_api_returns_freshness_per_category(
    m4_session_factory: Any,
    redis_client: Redis,
    m4_settings: Settings,
    service_client: TestClient,
) -> None:
    seeded = await _seed_league_team_fixture(
        m4_session_factory,
        kickoff_at=datetime.now(UTC) + timedelta(days=1),
    )
    # Persist a standings snapshot so the freshness view reflects it.
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
async def test_status_api_system_endpoint_reports_scheduler_flag(
    service_client: TestClient,
) -> None:
    response = service_client.get("/v1/system/status")
    assert response.status_code == 200
    body = response.json()
    assert body["scheduler_enabled"] is False
    assert body["degradation_mode"] == "NORMAL"


@pytest.mark.asyncio
async def test_get_fixtures_does_not_trigger_provider_calls(
    m4_session_factory: Any,
    redis_client: Redis,
    m4_settings: Settings,
    service_client: TestClient,
) -> None:
    """Database-first UX: a Telegram-style read flow (`/v1/fixtures`
    + `/v1/fixtures/{id}/status`) generates ZERO external provider
    calls — no `external_api_requests` rows are written."""
    seeded = await _seed_league_team_fixture(
        m4_session_factory,
        kickoff_at=datetime.now(UTC) + timedelta(days=1),
    )
    ctx = _ctx(
        factory=m4_session_factory,
        redis=redis_client,
        settings=m4_settings,
        provider=_recorded_provider(),
    )
    # Pre-populate fresh snapshots to ensure read endpoints have data.
    await run_collector(
        ctx,
        "standings",
        inputs={"league_id": seeded["league_id"], "season_id": seeded["season_id"]},
    )

    # Baseline: count external_api_requests rows after seeding.
    async with m4_session_factory() as session:
        baseline = (await session.execute(select(ExternalApiRequest))).scalars().all()
    baseline_count = len(baseline)

    # Read-only endpoints.
    today = datetime.now(UTC).date().isoformat()
    response = service_client.get(f"/v1/fixtures?date={today}")
    assert response.status_code == 200
    detail = service_client.get(f"/v1/fixtures/{seeded['fixture_id']}")
    assert detail.status_code == 200
    status_response = service_client.get(f"/v1/fixtures/{seeded['fixture_id']}/status")
    assert status_response.status_code == 200
    health = service_client.get("/ready")
    assert health.status_code in (200, 503)

    # No new external_api_requests rows after the read flow.
    async with m4_session_factory() as session:
        after = (await session.execute(select(ExternalApiRequest))).scalars().all()
    assert len(after) == baseline_count


@pytest.mark.asyncio
async def test_pre_match_scan_planner_idempotent_for_enabled_league(
    m4_session_factory: Any,
    m4_settings: Settings,
    tmp_path,
) -> None:
    scan_slug = f"integration-m4-scan-{uuid.uuid4().hex[:8]}"
    config_path = tmp_path / "leagues.yaml"
    config_path.write_text(
        f"""
version: 1
leagues:
  - slug: "{scan_slug}"
    name: "Integration M4 Scan"
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
        league = League(
            slug=scan_slug,
            name="Integration M4 Scan",
            country="Test",
            enabled=True,
        )
        session.add(league)
        await session.flush()
        home = Team(name="Arsenal SCAN", country="Test")
        away = Team(name="Coventry SCAN", country="Test")
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
    # Running the planner twice yields identical plan length (no
    # new state — pure DB read).
    decisions_again = await plan_for_date(
        m4_session_factory, settings, day=kickoff.astimezone(UTC).date()
    )
    assert len(decisions) == len(decisions_again)
