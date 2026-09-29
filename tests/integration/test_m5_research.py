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
        for c in conflicted:
            assert c.conflicting_claim_id is not None
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

    # Query without as_of: returns latest state
    resp_all = service_client.get(f"/v1/fixtures/{fid}/research")
    assert resp_all.status_code == 200
    data_all = resp_all.json()
    assert data_all["documents_count"] == 2
    assert data_all["claims_count"] == 2


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
        assert run.status == ResearchState.NO_USEFUL_RESULTS.value
        assert run.documents_count == 0
        assert run.claims_count == 0
