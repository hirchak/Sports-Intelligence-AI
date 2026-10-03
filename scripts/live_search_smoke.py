"""One real Tavily query on an explicitly recorded test fixture; no sports/Telegram/LLM calls."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import date
from pathlib import Path

from backup_restore import require_local_test_database
from redis.asyncio import Redis
from sqlalchemy import func, select

import sports_intelligence.collectors.research_collector  # noqa: F401
from sports_intelligence.collectors.framework import CollectorContext, run_collector
from sports_intelligence.collectors.freshness import FreshnessPolicy
from sports_intelligence.collectors.locks import CoalesceLockManager
from sports_intelligence.collectors.quota import QuotaManager
from sports_intelligence.core.config import Settings
from sports_intelligence.core.league_config import LeagueConfig, LeagueConfigEntry
from sports_intelligence.core.logging import setup_logging
from sports_intelligence.core.redaction import register_secrets
from sports_intelligence.db.models import ExternalApiRequest, Fixture, ResearchDocument, ResearchRun
from sports_intelligence.db.session import create_engine, create_session_factory
from sports_intelligence.pipelines.discover_fixtures import FixtureDiscoveryService
from sports_intelligence.providers.errors import ProviderAuthError
from sports_intelligence.providers.search.tavily import TavilySearchProvider
from sports_intelligence.providers.sports.mock import MockSportsDataProvider


async def main() -> None:
    original = Settings()
    register_secrets(original.model_dump())
    setup_logging("ERROR")
    url = os.environ["M10_DATABASE_URL"]
    require_local_test_database(url)
    if not original.search_api_key:
        print(json.dumps({"status": "NOT_VERIFIED", "reason": "credential absent"}))
        return
    settings = original.model_copy(
        update={
            "database_url": url,
            "redis_url": os.environ["M10_REDIS_URL"],
            "research_max_queries_per_fixture": 1,
            "research_max_results_per_query": 1,
        }
    )
    engine = create_engine(url)
    factory = create_session_factory(engine)
    redis = Redis.from_url(settings.redis_url)
    search = TavilySearchProvider(original.search_api_key)
    try:
        packet = json.loads(
            Path(
                "src/sports_intelligence/providers/sports/mock_data/fixtures_2026-08-21.json"
            ).read_text()
        )
        packet["response"] = packet["response"][:1]
        fixture_provider = MockSportsDataProvider(responses={"2026-08-21": packet})
        quota = QuotaManager(settings, factory, redis=redis)
        await FixtureDiscoveryService(
            fixture_provider,
            factory,
            LeagueConfig(
                leagues=[
                    LeagueConfigEntry(
                        slug="m10-search-recorded-fixture",
                        name="Recorded test fixture",
                        enabled=True,
                        provider_ids={"mock": 39},
                    )
                ]
            ),
            quota=quota,
        ).discover(date(2026, 8, 21))
        async with factory() as session:
            fixture = await session.scalar(
                select(Fixture).order_by(Fixture.created_at.desc()).limit(1)
            )
        original_search = search.search

        async def once(query: str, *, max_results: int = 1):
            try:
                return await original_search(query, max_results=max_results)
            except Exception:
                raise ProviderAuthError("bounded_smoke_no_retry") from None

        search.search = once
        ctx = CollectorContext(
            provider=search,
            quota=quota,
            locks=CoalesceLockManager(redis, settings),
            freshness=FreshnessPolicy(settings),
            session_factory=factory,
            settings=settings,
            redis=redis,
        )
        await run_collector(ctx, "research", inputs={"fixture_id": fixture.id})
        async with factory() as session:
            row = await session.scalar(
                select(ResearchRun).where(ResearchRun.fixture_id == fixture.id)
            )
            before = await session.scalar(select(func.count()).select_from(ExternalApiRequest))
            documents = (
                await session.scalars(
                    select(ResearchDocument).where(ResearchDocument.fixture_id == fixture.id)
                )
            ).all()
        await run_collector(ctx, "research", inputs={"fixture_id": fixture.id})
        async with factory() as session:
            after = await session.scalar(select(func.count()).select_from(ExternalApiRequest))
        print(
            json.dumps(
                {
                    "status": "PASS" if documents and before == after else "NOT_VERIFIED",
                    "fixture_input": "explicit recorded MOCK fixture; real search output only",
                    "research_status": row.status,
                    "documents": len(documents),
                    "claims": row.claims_count,
                    "fresh_repeat_ledger_delta": after - before,
                    "source_urls_and_hashes_persisted": all(
                        d.content_hash and d.url for d in documents
                    ),
                    "maximum_external_attempts": 1,
                    "forecast_quality_claim": False,
                },
                sort_keys=True,
            )
        )
    finally:
        await search.aclose()
        await redis.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
