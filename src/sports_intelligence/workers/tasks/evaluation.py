from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

import redis.asyncio as aioredis
from sqlalchemy import select

from sports_intelligence.collectors.locks import CoalesceLockManager
from sports_intelligence.collectors.quota import QuotaManager
from sports_intelligence.core.config import Settings, get_settings
from sports_intelligence.db.models import EvaluationRun, Fixture, Job
from sports_intelligence.db.session import create_engine, create_session_factory
from sports_intelligence.evaluation.config import EvaluationFilters
from sports_intelligence.evaluation.results import collect_date, digest, settle_pending
from sports_intelligence.evaluation.service import (
    calculate_evaluation,
    configured_metrics,
    enqueue_evaluation,
    request_evaluation,
)
from sports_intelligence.pipelines.discover_fixtures import create_or_get_job
from sports_intelligence.providers.base import SportsDataProvider
from sports_intelligence.providers.sports.factory import build_sports_provider
from sports_intelligence.workers.celery_app import celery_app
from sports_intelligence.workers.utils import record_job_attempt


@celery_app.task(name="evaluation.evaluate", queue="evaluation")  # type: ignore[untyped-decorator]
def evaluate_task(job_id: str, evaluation_id: str) -> dict[str, object]:
    return asyncio.run(run_evaluation_job(job_id, evaluation_id))


async def run_evaluation_job(
    job_id: str, evaluation_id: str, *, settings: Settings | None = None, factory: Any = None
) -> dict[str, object]:
    settings = settings or get_settings()
    engine = None
    if factory is None:
        engine = create_engine(settings.database_url)
        factory = create_session_factory(engine)
    started = datetime.now(UTC)
    try:
        async with factory() as session, session.begin():
            run = await session.scalar(
                select(EvaluationRun)
                .where(EvaluationRun.id == uuid.UUID(evaluation_id))
                .with_for_update()
            )
            if run is None or str(run.job_id) != job_id:
                raise ValueError("invalid evaluation job identity")
            if run.status != "QUEUED":
                return {"status": "reused", "evaluation_id": evaluation_id}
            job = await session.get(Job, run.job_id)
            job.status = "RUNNING"
            await calculate_evaluation(session, run)
            job.status = "SUCCEEDED"
        await record_job_attempt(
            factory,
            job_id=uuid.UUID(job_id),
            started_at=started,
            finished_at=datetime.now(UTC),
            outcome="SUCCEEDED",
        )
        return {
            "status": "SUCCEEDED",
            "evaluation_id": evaluation_id,
            "sample_size": run.sample_size,
        }
    except Exception as exc:
        async with factory() as session, session.begin():
            run = await session.get(EvaluationRun, uuid.UUID(evaluation_id))
            if run is not None and str(run.job_id) == job_id and run.status != "SUCCEEDED":
                run.status = "FAILED"
                run.error_class = type(exc).__name__
                job = await session.get(Job, run.job_id)
                if job:
                    job.status = "FAILED"
        await record_job_attempt(
            factory,
            job_id=uuid.UUID(job_id),
            started_at=started,
            finished_at=datetime.now(UTC),
            outcome="FAILED",
            error=exc,
        )
        raise
    finally:
        if engine:
            await engine.dispose()


@celery_app.task(name="evaluation.result_scan", queue="control")  # type: ignore[untyped-decorator]
def result_scan_task() -> dict[str, object]:
    return asyncio.run(schedule_result_scan())


async def schedule_result_scan(
    *, settings: Settings | None = None, factory: Any = None, now: datetime | None = None
) -> dict[str, object]:
    settings = settings or get_settings()
    if not settings.result_scan_enabled:
        return {"status": "disabled"}
    now = now or datetime.now(UTC)
    engine = None
    if factory is None:
        engine = create_engine(settings.database_url)
        factory = create_session_factory(engine)
    queued = 0
    try:
        async with factory() as session:
            dates = list(
                (
                    await session.scalars(
                        select(Fixture.kickoff_at).where(
                            Fixture.kickoff_at
                            <= now
                            - timedelta(
                                minutes=settings.result_expected_finish_minutes
                                + settings.result_grace_minutes
                            ),
                            Fixture.kickoff_at
                            >= now - timedelta(days=settings.result_lookback_days),
                        )
                    )
                ).all()
            )
        for day in sorted({value.date() for value in dates}):
            queued += await enqueue_result_date(factory, settings, day, now=now)
        # Local catch-up works even if no provider calls are needed today.
        await settle_pending(factory)
        await refresh_evaluations(factory, settings, now=datetime.now(UTC))
        return {"status": "scheduled", "queued": queued}
    finally:
        if engine:
            await engine.dispose()


async def enqueue_result_date(
    factory: Any, settings: Settings, day: date, *, now: datetime, force: bool = False
) -> bool:
    # Freeze execution identity; a new schedule slot permits safe failure recovery.
    policy = digest(
        {
            "provider": settings.sports_provider,
            "finish": settings.result_expected_finish_minutes,
            "grace": settings.result_grace_minutes,
            "version": "result_v1",
        }
    )
    slot = int(now.timestamp()) // settings.result_scan_interval_seconds
    key = f"m8:results:{day}:{slot}:{policy}:{force}"
    async with factory() as session:
        job, created = await create_or_get_job(session, "results", key, now)
        await session.commit()
        if not created:
            return False
        try:
            result_date_task.apply_async(
                kwargs={
                    "job_id": str(job.id),
                    "day_iso": day.isoformat(),
                    "provider_name": settings.sports_provider,
                    "force": force,
                },
                queue="sports_io",
                task_id=str(job.id),
            )
        except Exception:
            job.status = "FAILED"
            await session.commit()
            raise RuntimeError("result enqueue failed") from None
    return True


@celery_app.task(name="evaluation.collect_results", queue="sports_io")  # type: ignore[untyped-decorator]
def result_date_task(
    job_id: str, day_iso: str, provider_name: str, force: bool = False
) -> dict[str, object]:
    return asyncio.run(run_result_job(job_id, day_iso, provider_name, force=force))


async def run_result_job(
    job_id: str,
    day_iso: str,
    provider_name: str,
    *,
    force: bool = False,
    settings: Settings | None = None,
    factory: Any = None,
    provider: SportsDataProvider | None = None,
    redis: Any = None,
) -> dict[str, object]:
    settings = settings or get_settings()
    engine = None
    owned_provider, owned_redis = provider is None, redis is None
    if factory is None:
        engine = create_engine(settings.database_url)
        factory = create_session_factory(engine)
    started = datetime.now(UTC)
    try:
        if provider_name != settings.sports_provider:
            raise ValueError("result provider configuration changed since enqueue")
        async with factory() as session, session.begin():
            job = await session.scalar(
                select(Job).where(Job.id == uuid.UUID(job_id)).with_for_update()
            )
            if job is None or job.job_type != "results":
                raise ValueError("invalid result job")
            if job.status != "PENDING":
                return {"status": "reused"}
            job.status = "RUNNING"
        provider = provider or build_sports_provider(settings)
        redis = redis or aioredis.Redis.from_url(settings.redis_url)
        summary = await collect_date(
            factory=factory,
            provider=provider,
            quota=QuotaManager(settings, factory, redis),
            locks=CoalesceLockManager(redis, settings),
            settings=settings,
            day=date.fromisoformat(day_iso),
            force=force,
        )
        summary["settled"] += await settle_pending(factory)
        await refresh_evaluations(factory, settings, now=datetime.now(UTC))
        async with factory() as session, session.begin():
            job = await session.get(Job, uuid.UUID(job_id))
            job.status = "SUCCEEDED"
        await record_job_attempt(
            factory,
            job_id=uuid.UUID(job_id),
            started_at=started,
            finished_at=datetime.now(UTC),
            outcome="SUCCEEDED",
        )
        return {"status": "SUCCEEDED", **summary}
    except Exception as exc:
        async with factory() as session, session.begin():
            job = await session.get(Job, uuid.UUID(job_id))
            if job:
                job.status = "FAILED"
        await record_job_attempt(
            factory,
            job_id=uuid.UUID(job_id),
            started_at=started,
            finished_at=datetime.now(UTC),
            outcome="FAILED",
            error=exc,
        )
        raise
    finally:
        if owned_provider and provider:
            await provider.aclose()
        if owned_redis and redis:
            await redis.aclose()
        if engine:
            await engine.dispose()


async def refresh_evaluations(factory: Any, settings: Settings, *, now: datetime) -> list[str]:
    ids = []
    # Hourly shared cutoff coalesces refreshes from concurrent date workers.
    cutoff = now
    for days in (7, settings.evaluation_default_days, None):
        filters = EvaluationFilters(
            start=cutoff - timedelta(days=days) if days else None, end=cutoff
        )
        async with factory() as session:
            run, created = await request_evaluation(
                session, config=configured_metrics(settings), filters=filters, cutoff=cutoff
            )
            await enqueue_evaluation(session, run, created)
            ids.append(str(run.id))
    return ids
