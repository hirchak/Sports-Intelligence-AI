"""Generic collector execution task (M4.1 §12).

The pre-match scanner is CHEAP: it only reads the DB and enqueues
collector jobs. Each `sports.collect` job runs one collector through the
framework (freshness → lock → quota → fetch → persist → ledger) and
records its own job/attempt state — never executed inline inside the
Beat task.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis

from sports_intelligence.collectors.framework import (
    CollectorContext,
    run_collector,
)
from sports_intelligence.collectors.freshness import FreshnessPolicy
from sports_intelligence.collectors.locks import CoalesceLockManager
from sports_intelligence.collectors.quota import QuotaManager
from sports_intelligence.core.config import get_settings
from sports_intelligence.core.job_status import JobStatus
from sports_intelligence.core.logging import get_logger
from sports_intelligence.core.phases import ForecastPhase
from sports_intelligence.db.session import create_engine, create_session_factory
from sports_intelligence.pipelines.discover_fixtures import update_job_status
from sports_intelligence.providers.odds.factory import build_odds_provider
from sports_intelligence.providers.sports.factory import build_sports_provider
from sports_intelligence.workers.celery_app import celery_app
from sports_intelligence.workers.utils import record_job_attempt

logger = get_logger(__name__)


@celery_app.task(name="sports.collect", queue="sports_io")  # type: ignore[untyped-decorator]
def collect_task(
    job_id: str,
    collector_name: str,
    inputs_json: str,
    phase: str = ForecastPhase.MORNING.value,
    estimated_cost: int = 1,
) -> dict[str, object]:
    return asyncio.run(
        _run_collect_job(
            job_id=job_id,
            collector_name=collector_name,
            inputs_json=inputs_json,
            phase=phase,
            estimated_cost=estimated_cost,
        )
    )


async def _run_collect_job(
    *,
    job_id: str,
    collector_name: str,
    inputs_json: str,
    phase: str,
    estimated_cost: int,
) -> dict[str, object]:
    settings = get_settings()
    started_at = datetime.now(UTC)
    inputs = json.loads(inputs_json)
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)
    redis: Redis | None = None
    sports_provider = None
    odds_provider = None
    try:
        try:
            job_uuid = uuid.UUID(job_id)
        except ValueError as exc:
            raise ValueError(f"collect job_id is not a UUID: {job_id!r}") from exc

        async with factory() as session:
            await update_job_status(session, job_id, JobStatus.RUNNING)
            await session.commit()

        redis = Redis.from_url(settings.redis_url)
        sports_provider = build_sports_provider(settings)
        odds_provider = build_odds_provider(settings)
        provider = odds_provider if collector_name == "odds" else sports_provider
        quota = QuotaManager(settings, factory, redis=redis)
        locks = CoalesceLockManager(redis, settings)
        ctx = CollectorContext(
            provider=provider,
            quota=quota,
            locks=locks,
            freshness=FreshnessPolicy(settings),
            session_factory=factory,
            settings=settings,
            redis=redis,
            phase=(
                ForecastPhase(phase)
                if phase in ForecastPhase._value2member_map_
                else ForecastPhase.MORNING
            ),
        )
        # M4.2 §8: odds cost is provider-estimated credits (markets ×
        # regions), reserved BEFORE the network call — never the generic
        # per-request count of 1.
        effective_cost = estimated_cost
        if collector_name == "odds" and hasattr(provider, "estimate_cost"):
            effective_cost = max(
                provider.estimate_cost(
                    markets=settings.odds_provider_markets,
                    regions=settings.odds_provider_regions,
                ),
                1,
            )
        ref = await run_collector(
            ctx,
            collector_name,
            inputs={k: v for k, v in inputs.items() if k != "phase"},
            estimated_cost=effective_cost,
        )

        async with factory() as session:
            await update_job_status(session, job_id, JobStatus.SUCCEEDED)
            await session.commit()
        await record_job_attempt(
            factory,
            job_id=job_uuid,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            outcome=JobStatus.SUCCEEDED.value,
            error=None,
        )
        return {
            "job_id": job_id,
            "collector": collector_name,
            "snapshot_id": str(ref.snapshot_id),
            "captured_at": ref.captured_at.isoformat(),
        }
    except Exception as exc:
        logger.exception(
            "collector job failed",
            extra={"job_id": job_id, "collector": collector_name},
        )
        try:
            async with factory() as session:
                await update_job_status(session, job_id, JobStatus.FAILED)
                await session.commit()
        except Exception:  # noqa: BLE001
            logger.warning("failed to mark collect job FAILED", exc_info=True)
        try:
            job_uuid = uuid.UUID(job_id)
        except ValueError:
            job_uuid = None
        if job_uuid is not None:
            await record_job_attempt(
                factory,
                job_id=job_uuid,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                outcome=JobStatus.FAILED.value,
                error=exc,
            )
        raise
    finally:
        cleanup_tasks = []
        if sports_provider is not None:
            cleanup_tasks.append(sports_provider.aclose())
        if odds_provider is not None:
            cleanup_tasks.append(odds_provider.aclose())
        for cleanup in cleanup_tasks:
            try:
                await cleanup
            except Exception:  # noqa: BLE001
                logger.warning("provider cleanup failed in collect job", exc_info=True)
        if redis is not None:
            try:
                await redis.aclose()
            except Exception:  # noqa: BLE001
                logger.warning("redis cleanup failed in collect job", exc_info=True)
        try:
            await engine.dispose()
        except Exception:  # noqa: BLE001
            logger.warning("engine cleanup failed in collect job", exc_info=True)
