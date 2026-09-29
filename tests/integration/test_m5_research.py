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
from sqlalchemy import delete, select

import sports_intelligence.collectors.research_collector  # noqa: F401
from sports_intelligence.collectors.framework import (
    CollectorContext,
    run_collector,
)
from sports_intelligence.collectors.freshness import FreshnessPolicy
from sports_intelligence.collectors.locks import CoalesceLockManager
from sports_intelligence.collectors.quota import QuotaManager
from sports_intelligence.core.config import Settings
from sports_intelligence.core.phases import ForecastPhase, ResearchState
from sports_intelligence.db.models import (
    ExternalApiRequest,
    Fixture,
    League,
    QuotaBucket,
    ResearchClaim,
    ResearchDocument,
    ResearchRun,
    Season,
    Team,
)
from sports_intelligence.db.session import create_engine, create_session_factory
from sports_intelligence.providers.search.base import SearchResultItem
from sports_intelligence.providers.search.mock import MockSearchProvider
from sports_intelligence.research.query_builder import build_research_queries

requires_services = pytest.mark.skipif(
    not (os.environ.get("TEST_DATABASE_URL") and os.environ.get("TEST_REDIS_URL")),
    reason="TEST_DATABASE_URL and TEST_REDIS_URL are required",
)
pytestmark = [pytest.mark.integration, requires_services]


@pytest.fixture
def m5_settings(service_settings: Settings) -> Settings:
    return Settings(
        _env_file=None,
        app_env="mock",
        search_provider="mock",
        research_enabled=True,
        database_url=service_settings.database_url,
        redis_url=service_settings.redis_url,
    )


@pytest.fixture
async def m5_session_factory(m5_settings: Settings) -> Iterator[Any]:
    engine = create_engine(m5_settings.database_url)
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
async def _clean_m5_tables(m5_session_factory: Any) -> Iterator[None]:
    async with m5_session_factory() as session:
        for model in (
            ResearchClaim,
            ResearchDocument,
            ResearchRun,
            ExternalApiRequest,
            QuotaBucket,
            Fixture,
            Season,
            League,
            Team,
        ):
            await session.execute(delete(model))
        await session.commit()
    yield


@pytest.fixture
async def redis_client(m5_settings: Settings) -> Iterator[Redis]:
    client = Redis.from_url(m5_settings.redis_url)
    try:
        await client.flushdb()
        yield client
    finally:
        await client.aclose()


async def _seed_fixture(
    factory: Any,
    *,
    kickoff_at: datetime | None = None,
) -> dict[str, uuid.UUID]:
    if kickoff_at is None:
        kickoff_at = datetime.now(UTC) + timedelta(days=1)
    async with factory() as session:
        league = League(slug=f"league-{uuid.uuid4().hex[:6]}", name="Premier League", enabled=True)
        session.add(league)
        await session.flush()

        season = Season(league_id=league.id, name="2026", active=True)
        session.add(season)
        await session.flush()

        home = Team(name="Arsenal", country="England")
        away = Team(name="Chelsea", country="England")
        session.add_all([home, away])
        await session.flush()

        fixture = Fixture(
            league_id=league.id,
            season_id=season.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=kickoff_at,
            status="NS",
        )
        session.add(fixture)
        await session.commit()

        return {
            "fixture_id": fixture.id,
            "home_team_id": home.id,
            "away_team_id": away.id,
            "league_id": league.id,
        }


def _ctx(
    *,
    factory: Any,
    redis: Redis,
    settings: Settings,
    provider: Any,
    phase: ForecastPhase = ForecastPhase.MORNING,
) -> CollectorContext:
    return CollectorContext(
        provider=provider,
        quota=QuotaManager(settings, factory),
        locks=CoalesceLockManager(redis, settings),
        freshness=FreshnessPolicy(settings),
        session_factory=factory,
        settings=settings,
        redis=redis,
        phase=phase,
    )


@pytest.mark.asyncio
async def test_research_collector_persists_run_documents_claims(
    m5_session_factory: Any,
    redis_client: Redis,
    m5_settings: Settings,
) -> None:
    seeded = await _seed_fixture(m5_session_factory)
    provider = MockSearchProvider()
    ctx = _ctx(
        factory=m5_session_factory, redis=redis_client, settings=m5_settings, provider=provider
    )

    refs = await run_collector(
        ctx,
        "research",
        inputs={"fixture_id": str(seeded["fixture_id"]), "phase": ForecastPhase.MORNING.value},
    )

    ref = refs[0] if isinstance(refs, (list, tuple)) else refs
    assert ref.table == "research_runs"

    async with m5_session_factory() as session:
        # 1. Verify ResearchRun
        run = (
            await session.execute(
                select(ResearchRun).where(ResearchRun.fixture_id == seeded["fixture_id"])
            )
        ).scalar_one()
        assert run.status == ResearchState.AVAILABLE.value
        assert run.provider == "mock"
        assert run.phase == ForecastPhase.MORNING.value
        assert run.queries_count > 0
        assert run.documents_count > 0
        assert run.claims_count > 0

        # 2. Verify ResearchDocument
        docs = (
            (
                await session.execute(
                    select(ResearchDocument).where(
                        ResearchDocument.fixture_id == seeded["fixture_id"]
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(docs) == run.documents_count
        first_doc = docs[0]
        assert first_doc.url.startswith("http")
        assert first_doc.domain
        assert len(first_doc.content_hash) == 64
        assert first_doc.retrieved_at is not None

        # 3. Verify ResearchClaim
        claims = (
            (
                await session.execute(
                    select(ResearchClaim).where(ResearchClaim.fixture_id == seeded["fixture_id"])
                )
            )
            .scalars()
            .all()
        )
        assert len(claims) == run.claims_count
        for claim in claims:
            assert claim.claim_type
            assert claim.claim_text
            assert 0.0 <= claim.confidence <= 1.0
            assert claim.extracted_at is not None
            assert claim.document_id in {d.id for d in docs}


@pytest.mark.asyncio
async def test_research_collector_deduplicates_urls_and_content(
    m5_session_factory: Any,
    redis_client: Redis,
    m5_settings: Settings,
) -> None:
    seeded = await _seed_fixture(m5_session_factory)
    provider = MockSearchProvider()
    now = datetime.now(UTC)

    # Inject duplicate URLs with different tracking params and identical snippets
    duplicate_items = [
        SearchResultItem(
            url="https://theathletic.com/news/article-1?utm_source=twitter",
            domain="theathletic.com",
            title="Arsenal Injury Update",
            content="Bukayo Saka is ruled out with a hamstring injury.",
            published_at=now,
            retrieved_at=now,
            score=0.9,
        ),
        SearchResultItem(
            url="https://theathletic.com/news/article-1?utm_medium=email",
            domain="theathletic.com",
            title="Arsenal Injury Update Duplicate",
            content="Bukayo Saka is ruled out with a hamstring injury.",
            published_at=now,
            retrieved_at=now,
            score=0.85,
        ),
    ]
    # Set canned response for all queries
    for q in [
        "Arsenal vs Chelsea injury update",
        "Arsenal team news",
        "Chelsea team news",
    ]:
        provider.add_canned_response(q, duplicate_items)

    ctx = _ctx(
        factory=m5_session_factory, redis=redis_client, settings=m5_settings, provider=provider
    )
    await run_collector(
        ctx,
        "research",
        inputs={"fixture_id": str(seeded["fixture_id"]), "phase": ForecastPhase.MORNING.value},
    )

    async with m5_session_factory() as session:
        docs = (
            (
                await session.execute(
                    select(ResearchDocument).where(
                        ResearchDocument.fixture_id == seeded["fixture_id"]
                    )
                )
            )
            .scalars()
            .all()
        )
        # Both candidate items had the same canonical URL & content hash -> exactly 1 document
        athletic_docs = [d for d in docs if "theathletic.com" in d.domain]
        assert len(athletic_docs) == 1
        assert "utm_source" not in athletic_docs[0].url
        assert "utm_medium" not in athletic_docs[0].url


@pytest.mark.asyncio
async def test_research_collector_flags_conflicts(
    m5_session_factory: Any,
    redis_client: Redis,
    m5_settings: Settings,
) -> None:
    kickoff = datetime.now(UTC) + timedelta(days=1)
    seeded = await _seed_fixture(m5_session_factory, kickoff_at=kickoff)
    provider = MockSearchProvider()
    now = datetime.now(UTC)

    # Opposing claims for Arsenal: Saka ruled out vs Saka passed fitness test
    conflicting_items = [
        SearchResultItem(
            url="https://bbc.com/sport/football/story-1",
            domain="bbc.com",
            title="Arsenal Team News: Saka ruled out",
            content="Arsenal: Bukayo Saka is ruled out with an ankle sprain.",
            published_at=now,
            retrieved_at=now,
            score=0.9,
        ),
        SearchResultItem(
            url="https://skysports.com/football/story-2",
            domain="skysports.com",
            title="Arsenal Late Fitness: Saka cleared",
            content="Arsenal: Bukayo Saka passed fitness test and is fit to play for Arsenal.",
            published_at=now,
            retrieved_at=now,
            score=0.88,
        ),
    ]

    queries = build_research_queries(
        home_team_name="Arsenal",
        away_team_name="Chelsea",
        kickoff_at=kickoff,
        phase=ForecastPhase.MORNING,
    )
    for q in queries:
        provider.add_canned_response(q, conflicting_items)

    ctx = _ctx(
        factory=m5_session_factory, redis=redis_client, settings=m5_settings, provider=provider
    )
    await run_collector(
        ctx,
        "research",
        inputs={"fixture_id": str(seeded["fixture_id"]), "phase": ForecastPhase.MORNING.value},
    )

    async with m5_session_factory() as session:
        claims = (
            (
                await session.execute(
                    select(ResearchClaim).where(ResearchClaim.fixture_id == seeded["fixture_id"])
                )
            )
            .scalars()
            .all()
        )

        conflicted = [c for c in claims if c.conflict_flag]
        # Both opposing claims must be preserved and flagged
        assert len(conflicted) >= 2
        claim_a = conflicted[0]
        assert claim_a.conflicting_claim_id is not None
        claim_b = next(c for c in conflicted if c.id == claim_a.conflicting_claim_id)

        # Reciprocal referential integrity
        assert claim_a.conflicting_claim_id == claim_b.id
        assert claim_b.conflicting_claim_id == claim_a.id

        # Query referenced rows directly to verify foreign key integrity
        ref_b = await session.get(ResearchClaim, claim_a.conflicting_claim_id)
        assert ref_b is not None
        assert ref_b.id == claim_b.id

        ref_a = await session.get(ResearchClaim, claim_b.conflicting_claim_id)
        assert ref_a is not None
        assert ref_a.id == claim_a.id

        for c in conflicted:
            assert c.metadata_jsonb.get("conflict_detected") is True


@pytest.mark.asyncio
async def test_research_api_anti_leakage_as_of(
    m5_session_factory: Any,
    service_client: TestClient,
    m5_settings: Settings,
) -> None:
    seeded = await _seed_fixture(m5_session_factory)
    fid = seeded["fixture_id"]
    t0 = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)
    t1 = t0 + timedelta(hours=2)
    t2 = t0 + timedelta(hours=4)

    async with m5_session_factory() as session:
        run1 = ResearchRun(
            id=uuid.uuid4(),
            fixture_id=fid,
            phase="morning",
            status=ResearchState.AVAILABLE.value,
            provider="mock",
            queries_count=1,
            documents_count=1,
            claims_count=1,
            captured_at=t0,
        )
        session.add(run1)
        await session.flush()

        doc1 = ResearchDocument(
            id=uuid.uuid4(),
            fixture_id=fid,
            run_id=run1.id,
            url="https://site.com/early",
            domain="site.com",
            title="Early News",
            published_at=t0,
            retrieved_at=t0,
            content_hash="hash_early",
            provider="mock",
        )
        session.add(doc1)
        await session.flush()

        claim1 = ResearchClaim(
            id=uuid.uuid4(),
            document_id=doc1.id,
            fixture_id=fid,
            claim_type="availability",
            claim_text="Player is doubtful",
            confidence=0.8,
            extracted_at=t0,
            created_at=t0,
        )
        session.add(claim1)
        await session.flush()

        run2 = ResearchRun(
            id=uuid.uuid4(),
            fixture_id=fid,
            phase="prematch",
            status=ResearchState.AVAILABLE.value,
            provider="mock",
            queries_count=1,
            documents_count=1,
            claims_count=1,
            captured_at=t2,
        )
        session.add(run2)
        await session.flush()

        doc2 = ResearchDocument(
            id=uuid.uuid4(),
            fixture_id=fid,
            run_id=run2.id,
            url="https://site.com/late",
            domain="site.com",
            title="Late Breaking News",
            published_at=t2,
            retrieved_at=t2,
            content_hash="hash_late",
            provider="mock",
        )
        session.add(doc2)
        await session.flush()

        claim2 = ResearchClaim(
            id=uuid.uuid4(),
            document_id=doc2.id,
            fixture_id=fid,
            claim_type="availability",
            claim_text="Player is officially ruled out",
            confidence=0.95,
            extracted_at=t2,
            created_at=t2,
        )
        session.add(claim2)
        await session.commit()

    # Query with as_of=t1 (between early and late)
    resp_filtered = service_client.get(
        f"/v1/fixtures/{fid}/research",
        params={"as_of": t1.isoformat()},
    )
    assert resp_filtered.status_code == 200
    data_filtered = resp_filtered.json()
    assert data_filtered["documents_count"] == 1
    assert data_filtered["claims_count"] == 1
    assert data_filtered["documents"][0]["url"] == "https://site.com/early"

    # Query without as_of (default mode="latest_run"): returns evidence of latest run (run2)
    resp_latest = service_client.get(f"/v1/fixtures/{fid}/research")
    assert resp_latest.status_code == 200
    data_latest = resp_latest.json()
    assert data_latest["documents_count"] == 1
    assert data_latest["claims_count"] == 1
    assert data_latest["documents"][0]["url"] == "https://site.com/late"

    # Query without as_of in mode="accumulated": returns evidence across all runs
    resp_accum = service_client.get(
        f"/v1/fixtures/{fid}/research",
        params={"mode": "accumulated"},
    )
    assert resp_accum.status_code == 200
    data_accum = resp_accum.json()
    assert data_accum["documents_count"] == 2
    assert data_accum["claims_count"] == 2


@pytest.mark.asyncio
async def test_status_api_reflects_research_freshness(
    m5_session_factory: Any,
    redis_client: Redis,
    service_client: TestClient,
    m5_settings: Settings,
) -> None:
    seeded = await _seed_fixture(m5_session_factory)
    fid = seeded["fixture_id"]

    # 1. Before research collection: status is unknown
    resp1 = service_client.get(f"/v1/fixtures/{fid}/status")
    assert resp1.status_code == 200
    body1 = resp1.json()
    assert "research" in body1["freshness"]
    assert body1["freshness"]["research"]["state"] == "unknown"
    assert body1["freshness"]["research"]["captured_at"] is None

    # 2. Run research collector
    provider = MockSearchProvider()
    ctx = _ctx(
        factory=m5_session_factory, redis=redis_client, settings=m5_settings, provider=provider
    )
    await run_collector(
        ctx,
        "research",
        inputs={"fixture_id": str(fid), "phase": ForecastPhase.MORNING.value},
    )

    # 3. After research collection: status is fresh
    resp2 = service_client.get(f"/v1/fixtures/{fid}/status")
    assert resp2.status_code == 200
    body2 = resp2.json()
    assert body2["freshness"]["research"]["state"] == "fresh"
    assert body2["freshness"]["research"]["captured_at"] is not None
    assert body2["last_refresh"]["research"] is not None


@pytest.mark.asyncio
async def test_research_coalescing_lock(
    m5_session_factory: Any,
    redis_client: Redis,
    m5_settings: Settings,
) -> None:
    seeded = await _seed_fixture(m5_session_factory)
    fid = seeded["fixture_id"]
    provider = MockSearchProvider()
    ctx = _ctx(
        factory=m5_session_factory, redis=redis_client, settings=m5_settings, provider=provider
    )

    # Run 5 concurrent collectors on the same fixture
    tasks = [
        run_collector(
            ctx,
            "research",
            inputs={"fixture_id": str(fid), "phase": ForecastPhase.MORNING.value},
        )
        for _ in range(5)
    ]
    results = await asyncio.gather(*tasks)

    # All should return snapshot refs
    for res in results:
        ref = res[0] if isinstance(res, (list, tuple)) else res
        assert ref.table == "research_runs"

    # In database, exactly 1 research run was created because of coalescing
    async with m5_session_factory() as session:
        runs = (
            (await session.execute(select(ResearchRun).where(ResearchRun.fixture_id == fid)))
            .scalars()
            .all()
        )
        assert len(runs) == 1


@pytest.mark.asyncio
async def test_research_disabled_mode_zero_provider_calls(
    m5_session_factory: Any,
    redis_client: Redis,
    m5_settings: Settings,
) -> None:
    seeded = await _seed_fixture(m5_session_factory)
    fid = seeded["fixture_id"]

    disabled_settings = Settings(
        _env_file=None,
        app_env="mock",
        search_provider="",
        research_enabled=False,
        database_url=m5_settings.database_url,
        redis_url=m5_settings.redis_url,
    )
    # No provider passed
    ctx = _ctx(
        factory=m5_session_factory,
        redis=redis_client,
        settings=disabled_settings,
        provider=None,
    )

    refs = await run_collector(
        ctx,
        "research",
        inputs={"fixture_id": str(fid), "phase": ForecastPhase.MORNING.value},
    )

    ref = refs[0] if isinstance(refs, (list, tuple)) else refs
    assert ref.table == "research_runs"

    async with m5_session_factory() as session:
        run = (
            await session.execute(select(ResearchRun).where(ResearchRun.fixture_id == fid))
        ).scalar_one()
        assert run.status == ResearchState.DISABLED.value
        assert run.documents_count == 0
        assert run.claims_count == 0


@pytest.mark.asyncio
async def test_research_quota_and_request_ledger_exact_counts(
    m5_session_factory: Any,
    redis_client: Redis,
    m5_settings: Settings,
) -> None:
    """Regression for M5.1 §3:
    6 configured queries
    → exactly 6 search calls when budget permits
    → exactly 6 request ledger entries
    → 6 units consumed
    """
    seeded = await _seed_fixture(m5_session_factory)
    fid = seeded["fixture_id"]

    settings_6 = Settings(
        _env_file=None,
        app_env="mock",
        search_provider="mock",
        research_enabled=True,
        research_max_queries_per_fixture=6,
        database_url=m5_settings.database_url,
        redis_url=m5_settings.redis_url,
    )
    provider = MockSearchProvider()
    ctx = _ctx(
        factory=m5_session_factory,
        redis=redis_client,
        settings=settings_6,
        provider=provider,
    )

    await run_collector(
        ctx,
        "research",
        inputs={"fixture_id": str(fid), "phase": ForecastPhase.MORNING.value},
    )

    # 1. Exactly 6 queries executed by provider
    assert len(provider.history) == 6

    # 2. Exactly 6 rows in external_api_requests ledger
    async with m5_session_factory() as session:
        ledger_rows = (
            (
                await session.execute(
                    select(ExternalApiRequest).where(
                        ExternalApiRequest.endpoint_category == "research",
                        ExternalApiRequest.fixture_id == fid,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(ledger_rows) == 6
        for row in ledger_rows:
            assert row.provider == "mock"
            assert row.estimated_cost == 1
            assert row.status_code == 200
            assert row.fixture_id == fid


@pytest.mark.asyncio
async def test_research_quota_stops_before_third_call(
    m5_session_factory: Any,
    redis_client: Redis,
    m5_settings: Settings,
) -> None:
    """Regression for M5.1 §3:
    quota allows only 2
    → exactly 2 HTTP calls
    → no third call
    """
    from unittest.mock import AsyncMock, MagicMock

    seeded = await _seed_fixture(m5_session_factory)
    fid = seeded["fixture_id"]

    settings_6 = Settings(
        _env_file=None,
        app_env="mock",
        search_provider="mock",
        research_enabled=True,
        research_max_queries_per_fixture=6,
        database_url=m5_settings.database_url,
        redis_url=m5_settings.redis_url,
    )
    provider = MockSearchProvider()
    ctx = _ctx(
        factory=m5_session_factory,
        redis=redis_client,
        settings=settings_6,
        provider=provider,
    )

    # Mock quota: 2 allowed, 3rd denied
    allowed = MagicMock(denied=False, allowed=True, reason="ok")
    denied = MagicMock(denied=True, allowed=False, reason="budget exceeded")
    ctx.quota.reserve = AsyncMock(side_effect=[allowed, allowed, denied])

    await run_collector(
        ctx,
        "research",
        inputs={"fixture_id": str(fid), "phase": ForecastPhase.MORNING.value},
    )

    # Exactly 2 queries executed
    assert len(provider.history) == 2

    # Exactly 2 rows recorded in ledger
    async with m5_session_factory() as session:
        ledger_rows = (
            (
                await session.execute(
                    select(ExternalApiRequest).where(
                        ExternalApiRequest.endpoint_category == "research",
                        ExternalApiRequest.fixture_id == fid,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(ledger_rows) == 2


@pytest.mark.asyncio
async def test_fresh_research_zero_tavily_calls_and_zero_ledger_entries(
    m5_session_factory: Any,
    redis_client: Redis,
    m5_settings: Settings,
) -> None:
    """Regression for M5.1 §3:
    fresh research
    → zero search calls / zero new search request ledger entries.
    """
    seeded = await _seed_fixture(m5_session_factory)
    fid = seeded["fixture_id"]
    provider = MockSearchProvider()
    ctx = _ctx(
        factory=m5_session_factory,
        redis=redis_client,
        settings=m5_settings,
        provider=provider,
    )

    # Run 1: initial population
    ref1 = await run_collector(
        ctx,
        "research",
        inputs={"fixture_id": str(fid), "phase": ForecastPhase.MORNING.value},
    )
    initial_provider_calls = len(provider.history)
    assert initial_provider_calls > 0

    async with m5_session_factory() as session:
        initial_ledger_count = len(
            (
                await session.execute(
                    select(ExternalApiRequest).where(
                        ExternalApiRequest.endpoint_category == "research",
                        ExternalApiRequest.fixture_id == fid,
                    )
                )
            )
            .scalars()
            .all()
        )

    # Run 2: immediate second call while fresh
    ref2 = await run_collector(
        ctx,
        "research",
        inputs={"fixture_id": str(fid), "phase": ForecastPhase.MORNING.value},
    )

    # Returns same snapshot ref
    r1 = ref1[0] if isinstance(ref1, (list, tuple)) else ref1
    r2 = ref2[0] if isinstance(ref2, (list, tuple)) else ref2
    assert r1.snapshot_id == r2.snapshot_id

    # ZERO new provider calls
    assert len(provider.history) == initial_provider_calls

    # ZERO new request ledger entries
    async with m5_session_factory() as session:
        new_ledger_count = len(
            (
                await session.execute(
                    select(ExternalApiRequest).where(
                        ExternalApiRequest.endpoint_category == "research",
                        ExternalApiRequest.fixture_id == fid,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert new_ledger_count == initial_ledger_count


@pytest.mark.asyncio
async def test_research_structured_states_integration(
    m5_session_factory: Any,
    redis_client: Redis,
    m5_settings: Settings,
) -> None:
    """Regression for M5.1 §6:
    Structured states: PROVIDER_ERROR, EXTRACTION_UNAVAILABLE, NO_USEFUL_RESULTS, AVAILABLE.
    The overall football pipeline must continue even if research fails.
    """
    seeded = await _seed_fixture(m5_session_factory)
    fid = seeded["fixture_id"]

    # 1. PROVIDER_ERROR state
    failing_provider = MockSearchProvider(error_to_raise=RuntimeError("Search API unavailable"))
    ctx_error = _ctx(
        factory=m5_session_factory,
        redis=redis_client,
        settings=m5_settings,
        provider=failing_provider,
    )
    # Does not crash the caller
    ref_error = await run_collector(
        ctx_error,
        "research",
        inputs={"fixture_id": str(fid), "phase": ForecastPhase.MORNING.value},
    )
    assert ref_error is not None

    async with m5_session_factory() as session:
        run_error = (
            await session.execute(select(ResearchRun).where(ResearchRun.fixture_id == fid))
        ).scalar_one()
        assert run_error.status == ResearchState.PROVIDER_ERROR.value
        assert run_error.documents_count == 0
        assert run_error.claims_count == 0
        # Clean up for next state test
        await session.execute(delete(ResearchRun))
        await session.commit()

    # 2. NO_USEFUL_RESULTS state (provider returns empty results)
    empty_provider = MockSearchProvider()
    queries = build_research_queries(
        home_team_name="Arsenal",
        away_team_name="Chelsea",
        kickoff_at=datetime.now(UTC) + timedelta(days=1),
        phase=ForecastPhase.MORNING,
    )
    for q in queries:
        empty_provider.add_canned_response(q, [])

    ctx_empty = _ctx(
        factory=m5_session_factory,
        redis=redis_client,
        settings=m5_settings,
        provider=empty_provider,
    )
    await run_collector(
        ctx_empty,
        "research",
        inputs={"fixture_id": str(fid), "phase": ForecastPhase.MORNING.value},
    )

    async with m5_session_factory() as session:
        run_empty = (
            await session.execute(select(ResearchRun).where(ResearchRun.fixture_id == fid))
        ).scalar_one()
        assert run_empty.status == ResearchState.NO_USEFUL_RESULTS.value
        assert run_empty.documents_count == 0
        assert run_empty.claims_count == 0


@pytest.mark.asyncio
async def test_claim_level_as_of_safety_integration(
    m5_session_factory: Any,
    m5_settings: Settings,
) -> None:
    """Regression for M5.1 §2:
    Document retrieved at T0
    Claim extracted at T2
    Query as_of T1: document visible, claim NOT visible.
    Query as_of T3: claim visible.
    """
    from sports_intelligence.research.service import get_research_for_fixture

    seeded = await _seed_fixture(m5_session_factory)
    fid = seeded["fixture_id"]

    t0 = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)
    t1 = datetime(2026, 8, 20, 11, 0, tzinfo=UTC)
    t2 = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)
    t3 = datetime(2026, 8, 20, 13, 0, tzinfo=UTC)

    async with m5_session_factory() as session:
        run = ResearchRun(
            id=uuid.uuid4(),
            fixture_id=fid,
            phase="morning",
            status=ResearchState.AVAILABLE.value,
            provider="mock",
            queries_count=1,
            documents_count=1,
            claims_count=1,
            captured_at=t0,
        )
        session.add(run)
        await session.flush()

        doc = ResearchDocument(
            id=uuid.uuid4(),
            fixture_id=fid,
            run_id=run.id,
            url="https://site.com/doc",
            domain="site.com",
            title="Injury Doc",
            published_at=t0,
            retrieved_at=t0,
            content_hash="hash_doc_t0",
            provider="mock",
        )
        session.add(doc)
        await session.flush()

        claim = ResearchClaim(
            id=uuid.uuid4(),
            document_id=doc.id,
            fixture_id=fid,
            claim_type="availability",
            claim_text="Late extracted claim at T2",
            confidence=0.9,
            extracted_at=t2,
            created_at=t2,
        )
        session.add(claim)
        await session.commit()

    async with m5_session_factory() as session:
        # Query at T1 (before claim was extracted at T2)
        view_t1 = await get_research_for_fixture(session, fid, as_of=t1)
        assert len(view_t1.documents) == 1
        assert len(view_t1.claims) == 0  # Claim excluded!

        # Query at T3 (after claim was extracted at T2)
        view_t3 = await get_research_for_fixture(session, fid, as_of=t3)
        assert len(view_t3.documents) == 1
        assert len(view_t3.claims) == 1  # Claim included!
        assert view_t3.claims[0].claim_text == "Late extracted claim at T2"


@pytest.mark.asyncio
async def test_research_api_mode_invalid_returns_422(
    m5_session_factory: Any,
    service_client: TestClient,
    m5_settings: Settings,
) -> None:
    seeded = await _seed_fixture(m5_session_factory)
    fid = seeded["fixture_id"]
    resp = service_client.get(
        f"/v1/fixtures/{fid}/research",
        params={"mode": "invalid_mode"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_research_api_returns_disabled_when_capability_disabled(
    m5_session_factory: Any,
    service_client: TestClient,
    m5_settings: Settings,
) -> None:
    seeded = await _seed_fixture(m5_session_factory)
    fid = seeded["fixture_id"]

    # We can override app.state.settings in FastAPI test client if needed,
    # or just use service_client with settings overridden.
    # Actually, the easiest is to patch the app dependency or just set app_env to disable it.
    app = service_client.app
    old_settings = getattr(app.state, "settings", None)
    try:
        disabled_settings = Settings(
            _env_file=None,
            app_env="mock",
            search_provider="",
            research_enabled=False,
            database_url=m5_settings.database_url,
            redis_url=m5_settings.redis_url,
        )
        app.state.settings = disabled_settings
        resp = service_client.get(f"/v1/fixtures/{fid}/research")
        assert resp.status_code == 200
        assert resp.json()["status"] == ResearchState.DISABLED.value
    finally:
        app.state.settings = old_settings


@pytest.mark.asyncio
async def test_partial_provider_failure_persists_provider_error(
    m5_session_factory: Any,
    redis_client: Redis,
    m5_settings: Settings,
    service_client: TestClient,
) -> None:
    from sports_intelligence.collectors.framework import resolve
    from sports_intelligence.providers.errors import ProviderServerError
    from sports_intelligence.providers.search.base import SearchProvider, SearchResponse

    t0 = datetime(2026, 9, 29, 10, 0, 0, tzinfo=UTC)
    t1 = t0 + timedelta(seconds=5)
    t2 = t0 + timedelta(seconds=10)
    t3 = t0 + timedelta(seconds=15)
    clock_time = t0

    def clock():
        return clock_time

    class MockSearchPartialIntegration(SearchProvider):
        name = "mock"

        def __init__(self):
            self.calls = 0

        async def search(self, query: str, **kwargs) -> SearchResponse:
            nonlocal clock_time
            self.calls += 1
            if self.calls == 1:
                clock_time = t1
                return SearchResponse(
                    query=query,
                    results=[
                        SearchResultItem(
                            url="http://mock",
                            domain="mock",
                            title="mock",
                            published_at=None,
                            retrieved_at=t1,
                            content="mock",
                            score=1.0,
                            provider_metadata={},
                        )
                    ],
                    retrieved_at=t1,
                    cost_estimate=1,
                    raw_payload={},
                )
            clock_time = t3
            raise ProviderServerError("Failed on second call at T3")

    seeded = await _seed_fixture(m5_session_factory)
    fid = seeded["fixture_id"]
    provider = MockSearchPartialIntegration()
    ctx = _ctx(
        factory=m5_session_factory, redis=redis_client, settings=m5_settings, provider=provider
    )

    collector = resolve("research")
    orig_clock = getattr(collector, "_clock", None)
    collector._clock = clock
    try:
        await run_collector(
            ctx,
            "research",
            inputs={"fixture_id": str(fid), "phase": ForecastPhase.MORNING.value},
        )
    finally:
        if orig_clock is not None:
            collector._clock = orig_clock

    async with m5_session_factory() as session:
        run = (
            await session.execute(select(ResearchRun).where(ResearchRun.fixture_id == fid))
        ).scalar_one()
        assert run.status == ResearchState.PROVIDER_ERROR.value
        assert run.documents_count == 1
        assert run.captured_at == t3
        assert "details" in run.details_jsonb or "partial_failure" in run.details_jsonb

        doc = (
            await session.execute(select(ResearchDocument).where(ResearchDocument.run_id == run.id))
        ).scalar_one()
        assert doc.retrieved_at == t1

    # Historical point-in-time check: as_of between T1 and T3
    # must NOT reveal the later PROVIDER_ERROR run
    resp_t2 = service_client.get(
        f"/v1/fixtures/{fid}/research",
        params={"as_of": t2.isoformat()},
    )
    assert resp_t2.status_code == 200
    data_t2 = resp_t2.json()
    assert data_t2["status"] == ResearchState.NO_USEFUL_RESULTS.value
    assert data_t2["documents_count"] == 0

    # Historical query at T3 reveals the run and its document
    resp_t3 = service_client.get(
        f"/v1/fixtures/{fid}/research",
        params={"as_of": t3.isoformat()},
    )
    assert resp_t3.status_code == 200
    data_t3 = resp_t3.json()
    assert data_t3["status"] == ResearchState.PROVIDER_ERROR.value
    assert data_t3["documents_count"] == 1


@pytest.mark.asyncio
async def test_fixture_status_research_disabled_when_capability_disabled(
    service_client: TestClient,
    m5_session_factory: Any,
    m5_settings: Settings,
) -> None:
    """M5.3 §5: GET /v1/fixtures/{id}/status reports research freshness as 'disabled'
    when research capability is disabled and no run exists."""
    seeded = await _seed_fixture(m5_session_factory)
    fid = seeded["fixture_id"]

    # 1. With capability disabled
    disabled_settings = Settings(
        _env_file=None,
        app_env="mock",
        search_provider="",
        research_enabled=False,
        database_url=m5_settings.database_url,
        redis_url=m5_settings.redis_url,
    )
    service_client.app.state.settings = disabled_settings

    res = service_client.get(f"/v1/fixtures/{fid}/status")
    assert res.status_code == 200
    body = res.json()
    assert "research" in body["freshness"]
    assert body["freshness"]["research"]["state"] == "disabled"
    assert body["freshness"]["research"]["captured_at"] is None

    # 2. Reset back to enabled: status becomes 'unknown' when no run exists
    service_client.app.state.settings = m5_settings
    res2 = service_client.get(f"/v1/fixtures/{fid}/status")
    assert res2.status_code == 200
    body2 = res2.json()
    assert body2["freshness"]["research"]["state"] == "unknown"


@pytest.mark.asyncio
async def test_provider_error_scanner_retry_job_lifecycle(
    m5_session_factory: Any,
    m5_settings: Settings,
) -> None:
    """M5.3 §1: Full lifecycle of PROVIDER_ERROR retry job identity:
    - first error persists ResearchRun(PROVIDER_ERROR) and initial Job SUCCEEDED;
    - scan before error retry due (15m) -> NO new job;
    - scan after retry due -> NEW deterministic opportunity (error_due:<epoch>) / enqueued;
    - duplicate scan inside same retry opportunity -> NO duplicate;
    - second provider error -> opens a later error retry generation;
    - successful retry -> normal 6h research TTL resumes.
    """
    from unittest.mock import patch as _patch

    from sports_intelligence.collectors.pre_match_scan import PreMatchDecision
    from sports_intelligence.core.job_status import JobStatus
    from sports_intelligence.core.phases import FreshnessCategory
    from sports_intelligence.db.models import Job
    from sports_intelligence.workers.tasks.collect import collect_task
    from sports_intelligence.workers.tasks.pre_match import _dispatch_decision

    t0 = datetime(2026, 9, 29, 8, 0, 0, tzinfo=UTC)
    kickoff = t0 + timedelta(hours=6)
    seeded = await _seed_fixture(m5_session_factory, kickoff_at=kickoff)
    fid = seeded["fixture_id"]

    decision = PreMatchDecision(
        fixture_id=str(fid),
        league_id=str(seeded["league_id"]),
        home_team_id=str(seeded["home_team_id"]),
        away_team_id=str(seeded["away_team_id"]),
        season_id=str(seeded.get("season_id", uuid.uuid4())),
        kickoff_at=kickoff,
        phase=ForecastPhase.MORNING,
        categories_to_collect=(FreshnessCategory.RESEARCH,),
    )

    settings = Settings(
        _env_file=None,
        app_env="mock",
        search_provider="mock",
        research_enabled=True,
        research_provider_error_retry_seconds=900,  # 15 min
        database_url=m5_settings.database_url,
        redis_url=m5_settings.redis_url,
    )

    enqueued_jobs: list[str] = []

    def _fake_apply_async(*, args, **_kwargs):
        enqueued_jobs.append(args[0])

    with (
        _patch.object(collect_task, "apply_async", _fake_apply_async),
        _patch("sports_intelligence.workers.tasks.pre_match.get_settings", return_value=settings),
    ):
        # 1. First scan when no snapshot exists creates initial job with due:missing
        res1 = await _dispatch_decision(m5_session_factory, decision, now=t0)
        assert res1["jobs_created"] == 1
        assert res1["jobs_enqueued"] == 1

        async with m5_session_factory() as session:
            job_rows = (
                (await session.execute(select(Job).where(Job.job_type == "collect:research")))
                .scalars()
                .all()
            )
            assert len(job_rows) == 1
            first_job = job_rows[0]
            assert "due:missing" in first_job.idempotency_key

            # Simulate the collector executed, failed with PROVIDER_ERROR at t0, and job SUCCEEDED
            first_job.status = JobStatus.SUCCEEDED.value
            run1 = ResearchRun(
                id=uuid.uuid4(),
                fixture_id=fid,
                phase=ForecastPhase.MORNING.value,
                status=ResearchState.PROVIDER_ERROR.value,
                provider="mock",
                queries_count=1,
                documents_count=0,
                claims_count=0,
                conflicts_count=0,
                captured_at=t0,
                details_jsonb={"error": "provider down"},
                created_at=t0,
            )
            session.add(run1)
            await session.commit()

        # 2. Scan before error retry due (at t0 + 5m, error_ttl is 15m) -> NO new job
        res2 = await _dispatch_decision(m5_session_factory, decision, now=t0 + timedelta(minutes=5))
        assert res2["jobs_created"] == 0
        assert res2["jobs_enqueued"] == 0
        assert res2["by_category"].get("research", {}).get("created", 0) == 0
        # 3. Scan after error retry due (at t0 + 16m >= 15m) ->
        # NEW deterministic opportunity / enqueue
        res3 = await _dispatch_decision(
            m5_session_factory, decision, now=t0 + timedelta(minutes=16)
        )
        assert res3["jobs_created"] == 1
        assert res3["jobs_enqueued"] == 1
        assert res3["by_category"]["research"]["enqueued"] == 1

        expected_due_1 = int((t0 + timedelta(seconds=900)).timestamp())
        async with m5_session_factory() as session:
            job_rows = (
                (
                    await session.execute(
                        select(Job)
                        .where(Job.job_type == "collect:research")
                        .order_by(Job.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            assert len(job_rows) == 2
            second_job = job_rows[0]
            assert f"error_due:{expected_due_1}" in second_job.idempotency_key

        # 4. Duplicate scan inside same retry opportunity (at t0 + 17m) -> NO duplicate
        res4 = await _dispatch_decision(
            m5_session_factory, decision, now=t0 + timedelta(minutes=17)
        )
        assert res4["jobs_created"] == 0
        assert res4["jobs_enqueued"] == 0
        assert res4["by_category"]["research"]["reused"] == 1

        # 5. Second provider error at t1 (t0 + 18m) opens another retry opportunity
        t1 = t0 + timedelta(minutes=18)
        async with m5_session_factory() as session:
            # Second job completes with SUCCEEDED status (as normal Celery completion)
            j2 = await session.get(Job, second_job.id)
            if j2:
                j2.status = JobStatus.SUCCEEDED.value
            run2 = ResearchRun(
                id=uuid.uuid4(),
                fixture_id=fid,
                phase=ForecastPhase.MORNING.value,
                status=ResearchState.PROVIDER_ERROR.value,
                provider="mock",
                queries_count=1,
                documents_count=0,
                claims_count=0,
                conflicts_count=0,
                captured_at=t1,
                details_jsonb={"error": "provider down again"},
                created_at=t1,
            )
            session.add(run2)
            await session.commit()

        # Before second retry due (at t1 + 5m) -> NO new job
        res5 = await _dispatch_decision(m5_session_factory, decision, now=t1 + timedelta(minutes=5))
        assert res5["jobs_created"] == 0
        assert res5["jobs_enqueued"] == 0

        # After second retry due (at t1 + 16m) -> NEW opportunity
        res6 = await _dispatch_decision(
            m5_session_factory, decision, now=t1 + timedelta(minutes=16)
        )
        assert res6["jobs_created"] == 1
        assert res6["jobs_enqueued"] == 1
        expected_due_2 = int((t1 + timedelta(seconds=900)).timestamp())
        async with m5_session_factory() as session:
            job_rows = (
                (
                    await session.execute(
                        select(Job)
                        .where(Job.job_type == "collect:research")
                        .order_by(Job.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            assert len(job_rows) == 3
            assert f"error_due:{expected_due_2}" in job_rows[0].idempotency_key
            j3 = job_rows[0]
            j3.status = JobStatus.SUCCEEDED.value

            # 6. Successful retry at t2 (t1 + 18m) -> normal 6h TTL resumes
            t2 = t1 + timedelta(minutes=18)
            run3 = ResearchRun(
                id=uuid.uuid4(),
                fixture_id=fid,
                phase=ForecastPhase.MORNING.value,
                status=ResearchState.AVAILABLE.value,
                provider="mock",
                queries_count=1,
                documents_count=1,
                claims_count=1,
                conflicts_count=0,
                captured_at=t2,
                details_jsonb={},
                created_at=t2,
            )
            session.add(run3)
            await session.commit()

        # Scan at t2 + 10m -> snapshot is fresh under normal 6h TTL -> NO job
        res7 = await _dispatch_decision(
            m5_session_factory, decision, now=t2 + timedelta(minutes=10)
        )
        assert res7["jobs_created"] == 0
        assert res7["jobs_enqueued"] == 0
