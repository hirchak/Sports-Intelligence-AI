"""Explicit, bounded LOCAL smoke using credentials already stored in the operator env.

At most two sports calls, one search query (one attempt) and one Telegram test message.
Real LLM smoke requires an already-configured route/key; this script never selects one.
Run only when specifically authorized. Never changes credentials or local env files.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, date, datetime
from typing import Any

from aiogram import Bot
from backup_restore import require_local_test_database
from redis.asyncio import Redis
from sqlalchemy import func, select

import sports_intelligence.collectors.research_collector  # noqa: F401
import sports_intelligence.collectors.sports_collectors  # noqa: F401
from sports_intelligence.collectors.framework import CollectorContext, run_collector
from sports_intelligence.collectors.freshness import FreshnessPolicy
from sports_intelligence.collectors.locks import CoalesceLockManager
from sports_intelligence.collectors.quota import QuotaManager
from sports_intelligence.core.config import Settings
from sports_intelligence.core.league_config import LeagueConfig, LeagueConfigEntry
from sports_intelligence.core.logging import setup_logging
from sports_intelligence.core.redaction import register_secrets
from sports_intelligence.db.models import ExternalApiRequest, Fixture, RawProviderPayload
from sports_intelligence.db.session import create_engine, create_session_factory
from sports_intelligence.pipelines.discover_fixtures import FixtureDiscoveryService
from sports_intelligence.providers.search.factory import build_search_provider
from sports_intelligence.providers.sports.api_football import ApiFootballProvider


async def main() -> None:
    original = Settings()
    register_secrets(original.model_dump())
    setup_logging("ERROR")
    database_url = os.environ["M10_DATABASE_URL"]
    require_local_test_database(database_url)
    settings = original.model_copy(
        update={
            "app_env": "live_local",
            "database_url": database_url,
            "redis_url": os.environ["M10_REDIS_URL"],
            "sports_provider": "api_football",
            "search_provider": "tavily",
            "research_max_queries_per_fixture": 1,
            "research_max_results_per_query": 1,
        }
    )
    engine = create_engine(database_url)
    factory = create_session_factory(engine)
    redis = Redis.from_url(settings.redis_url)
    quota = QuotaManager(settings, factory, redis=redis)
    report: dict[str, Any] = {
        "sports": {"status": "NOT_VERIFIED"},
        "odds": {"status": "NOT_VERIFIED", "reason": "credential absent"},
        "search": {"status": "NOT_VERIFIED"},
        "telegram": {"status": "NOT_VERIFIED"},
        "real_llm": {"status": "NOT_VERIFIED", "reason": "no configured real runtime route/key"},
    }
    fixture = None
    try:
        if original.sports_api_key:
            provider = ApiFootballProvider(original.sports_api_key, max_attempts=1)
            try:
                config = LeagueConfig(
                    leagues=[
                        LeagueConfigEntry(
                            slug="premier-league",
                            name="Premier League",
                            enabled=True,
                            provider_ids={"api_football": 39},
                        )
                    ]
                )
                summary = await FixtureDiscoveryService(
                    provider, factory, config, quota=quota
                ).discover(date(2026, 8, 21))
                async with factory() as session:
                    fixture = await session.scalar(
                        select(Fixture).order_by(Fixture.created_at.desc()).limit(1)
                    )
                if fixture:
                    ctx = CollectorContext(
                        provider=provider,
                        quota=quota,
                        locks=CoalesceLockManager(redis, settings),
                        freshness=FreshnessPolicy(settings),
                        session_factory=factory,
                        settings=settings,
                        redis=redis,
                    )
                    inputs = {"league_id": fixture.league_id, "season_id": fixture.season_id}
                    await run_collector(ctx, "standings", inputs=inputs)
                    async with factory() as session:
                        before = await session.scalar(
                            select(func.count()).select_from(ExternalApiRequest)
                        )
                    await run_collector(ctx, "standings", inputs=inputs)
                    async with factory() as session:
                        after = await session.scalar(
                            select(func.count()).select_from(ExternalApiRequest)
                        )
                    assert before == after
                    report["sports"] = {
                        "status": "PASS",
                        "date": "2026-08-21",
                        "normalized_fixtures": summary.fixtures_created,
                        "fresh_repeat_external_calls": 0,
                        "max_physical_calls": 2,
                    }
                else:
                    report["sports"] = {
                        "status": "NOT_VERIFIED",
                        "reason": "no eligible normalized fixture in bounded response",
                    }
            except Exception as exc:
                report["sports"] = {"status": "NOT_VERIFIED", "reason": type(exc).__name__}
            finally:
                await provider.aclose()
        if original.search_api_key and fixture:
            provider = build_search_provider(settings)
            try:
                # At most one physical attempt, even when a real provider is unavailable.
                async def once(query: str, *, max_results: int = 1):
                    try:
                        return await original_search(query, max_results=max_results)
                    except Exception:
                        from sports_intelligence.providers.errors import ProviderAuthError

                        raise ProviderAuthError("bounded_smoke_no_retry") from None

                original_search = provider.search
                provider.search = once
                ctx = CollectorContext(
                    provider=provider,
                    quota=quota,
                    locks=CoalesceLockManager(redis, settings),
                    freshness=FreshnessPolicy(settings),
                    session_factory=factory,
                    settings=settings,
                    redis=redis,
                )
                await run_collector(ctx, "research", inputs={"fixture_id": fixture.id})
                async with factory() as session:
                    from sports_intelligence.db.models import ResearchRun

                    row = await session.scalar(
                        select(ResearchRun).where(ResearchRun.fixture_id == fixture.id)
                    )
                await run_collector(ctx, "research", inputs={"fixture_id": fixture.id})
                report["search"] = {
                    "status": "PASS" if row.documents_count else "NOT_VERIFIED",
                    "documents": row.documents_count,
                    "claims": row.claims_count,
                    "research_status": row.status,
                    "max_physical_calls": 1,
                }
            except Exception as exc:
                report["search"] = {"status": "NOT_VERIFIED", "reason": type(exc).__name__}
            finally:
                if provider:
                    await provider.aclose()
        if original.telegram_bot_token and original.telegram_allowed_user_ids:
            bot = Bot(original.telegram_bot_token)
            try:
                await bot.get_me()
                message = await bot.send_message(
                    original.telegram_allowed_user_ids[0],
                    "M10 LOCAL smoke: автентифікований Telegram transport перевірено. "
                    "Тестове повідомлення, без прогнозів і деплою.",
                )
                report["telegram"] = {
                    "status": "PASS",
                    "messages_sent": 1,
                    "api_acknowledged": bool(message.message_id),
                    "limitations": (
                        "transport acknowledgement only; "
                        "human receipt and live command flow not asserted"
                    ),
                }
            except Exception as exc:
                report["telegram"] = {"status": "NOT_VERIFIED", "reason": type(exc).__name__}
            finally:
                await bot.session.close()
        async with factory() as session:
            report["raw_payloads"] = await session.scalar(
                select(func.count()).select_from(RawProviderPayload)
            )
            report["request_ledger_rows"] = await session.scalar(
                select(func.count()).select_from(ExternalApiRequest)
            )
        report["timestamp"] = datetime.now(UTC).isoformat()
        print(json.dumps(report, sort_keys=True))
    finally:
        await redis.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
