from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker

from sports_intelligence.collectors.framework import (
    CollectorContext,
    resolve,
    run_collector,
)
from sports_intelligence.collectors.freshness import FreshnessPolicy
from sports_intelligence.collectors.locks import CoalesceLockManager
from sports_intelligence.collectors.pre_match_scan import execute_plan, plan_for_date
from sports_intelligence.collectors.quota import QuotaManager
from sports_intelligence.core.config import Settings, get_settings
from sports_intelligence.core.logging import get_logger
from sports_intelligence.core.time import local_today
from sports_intelligence.db.session import create_engine, create_session_factory
from sports_intelligence.providers.base import SportsDataProvider
from sports_intelligence.providers.odds.base import OddsProvider
from sports_intelligence.providers.odds.factory import build_odds_provider
from sports_intelligence.providers.sports.factory import build_sports_provider
from sports_intelligence.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="sports.pre_match_scan", queue="sports_io")  # type: ignore[untyped-decorator]
def pre_match_scan_task() -> dict[str, object]:
    """Daily pre-match scan that enqueues collectors for upcoming fixtures.

    Reads enabled fixtures from PostgreSQL, decides which categories
    require a refresh based on the freshness policy and the configured
    pre-kickoff windows, and dispatches collector jobs on `sports_io`.
    Each collector re-checks freshness under a Redis coalescing lock,
    so duplicate dispatches for the same key short-circuit without a
    provider call.
    """
    return asyncio.run(_run())


async def _run() -> dict[str, object]:
    settings = get_settings()
    today = local_today(datetime.now(UTC), settings.app_timezone)
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)
    try:
        decisions = await plan_for_date(factory, settings, day=today)
    except Exception:
        logger.exception("pre-match scan planning failed")
        await engine.dispose()
        return {"enqueued": 0, "decisions": 0, "error": "planning_failed"}
    quotas, locks, providers = _build_runtime(settings, factory)
    counters: dict[str, int] = {}
    for decision in decisions:
        ctx = CollectorContext(
            provider=providers["sports"],
            quota=quotas,
            locks=locks,
            freshness=FreshnessPolicy(settings),
            session_factory=factory,
            settings=settings,
            redis=None,
        )

        async def enqueue(name: str, **inputs: object) -> None:
            try:
                resolve(name)
            except KeyError:
                return
            ctx_for_collector = CollectorContext(
                provider=collect_provider_for(name, providers),
                quota=quotas,
                locks=locks,
                freshness=FreshnessPolicy(settings),
                session_factory=factory,
                settings=settings,
                redis=None,
            )
            try:
                await run_collector(ctx_for_collector, name, inputs=dict(inputs))
            except Exception:
                logger.warning("collector %s failed during scan", name, exc_info=True)

        counters_for_decision = await execute_plan(
            settings, ctx, decisions=[decision], enqueue_collector=enqueue
        )
        for category, count in counters_for_decision.items():
            counters[category] = counters.get(category, 0) + count
    await engine.dispose()
    return {
        "enqueued": sum(counters.values()),
        "decisions": len(decisions),
        "by_category": counters,
    }


def _build_runtime(
    settings: Settings, session_factory: async_sessionmaker[Any]
) -> tuple[QuotaManager, CoalesceLockManager, dict[str, SportsDataProvider | OddsProvider]]:
    redis = Redis.from_url(settings.redis_url)
    locks = CoalesceLockManager(redis, settings)
    quotas = QuotaManager(settings, session_factory)
    providers: dict[str, SportsDataProvider | OddsProvider] = {
        "sports": build_sports_provider(settings),
        "odds": build_odds_provider(settings),
    }
    return quotas, locks, providers


def collect_provider_for(name: str, providers: dict[str, Any]) -> Any:
    if name == "odds":
        return providers["odds"]
    return providers["sports"]
