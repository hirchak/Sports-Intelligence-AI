"""Pre-match scanner Beat task (M4.1 §12).

CHEAP by design: reads upcoming fixtures from PostgreSQL, builds a
deterministic plan, and ENQUEUES collector jobs (`sports.collect`) with
proper Job rows + attempt recording. No external collectors run inline;
no provider calls happen inside this task.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sports_intelligence.collectors.pre_match_scan import (
    PreMatchDecision,
    plan_for_date,
)
from sports_intelligence.core.config import get_settings
from sports_intelligence.core.job_status import JobStatus
from sports_intelligence.core.logging import get_logger
from sports_intelligence.core.time import local_today
from sports_intelligence.db.session import create_engine, create_session_factory
from sports_intelligence.pipelines.discover_fixtures import (
    create_or_get_job,
    update_job_status,
)
from sports_intelligence.workers.celery_app import celery_app
from sports_intelligence.workers.utils import record_job_attempt

logger = get_logger(__name__)

_ENDPOINT_FAMILY = "pre_match_scan"


@celery_app.task(name="sports.pre_match_scan", queue="control")  # type: ignore[untyped-decorator]
def pre_match_scan_task() -> dict[str, object]:
    return asyncio.run(_run())


async def _run() -> dict[str, object]:
    settings = get_settings()
    started_at = datetime.now(UTC)
    today = local_today(started_at, settings.app_timezone)
    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)
    try:
        decisions = await plan_for_date(factory, settings, day=today, now=started_at)
    except Exception:
        logger.exception("pre-match scan planning failed")
        await engine.dispose()
        return {"enqueued": 0, "decisions": 0, "error": "planning_failed"}

    # Own Job row for the scan itself (idempotent per day+minute bucket).
    scan_key = f"{_ENDPOINT_FAMILY}:{today.isoformat()}:{started_at:%H%M}"
    try:
        async with factory() as session:
            scan_job, scan_created = await create_or_get_job(
                session,
                job_type=_ENDPOINT_FAMILY,
                idempotency_key=scan_key,
                scheduled_for=started_at,
            )
            await session.commit()
            scan_job_id = str(scan_job.id)
    except Exception:
        logger.warning("could not create pre-match scan job row", exc_info=True)
        scan_job_id = None

    counters: dict[str, int] = {}
    enqueued_total = 0
    for decision in decisions:
        try:
            jobs = await _dispatch_decision(factory, decision)
            for category, count in jobs.items():
                counters[category] = counters.get(category, 0) + count
                enqueued_total += count
        except Exception:
            logger.exception(
                "failed to dispatch collector jobs for decision",
                extra={"fixture_id": decision.fixture_id},
            )

    if scan_job_id is not None:
        try:
            async with factory() as session:
                await update_job_status(session, scan_job_id, JobStatus.SUCCEEDED)
                await session.commit()
            await record_job_attempt(
                factory,
                job_id=uuid.UUID(scan_job_id),
                started_at=started_at,
                finished_at=datetime.now(UTC),
                outcome=JobStatus.SUCCEEDED.value,
                error=None,
            )
        except Exception:
            logger.warning("could not record pre-match scan attempt", exc_info=True)

    try:
        await engine.dispose()
    except Exception:  # noqa: BLE001
        logger.warning("engine cleanup failed during pre-match scan", exc_info=True)

    return {
        "enqueued": enqueued_total,
        "decisions": len(decisions),
        "by_category": counters,
        "scan_job_id": scan_job_id,
    }


async def _dispatch_decision(
    factory: Any,
    decision: PreMatchDecision,
) -> dict[str, int]:
    """Create-or-get a Job per (collector, lock key, phase) and enqueue
    `sports.collect` with the full immutable inputs."""
    from redis.asyncio import Redis

    from sports_intelligence.collectors.framework import CollectorContext, resolve
    from sports_intelligence.collectors.freshness import FreshnessPolicy
    from sports_intelligence.collectors.locks import CoalesceLockManager
    from sports_intelligence.collectors.pre_match_scan import execute_plan
    from sports_intelligence.collectors.quota import QuotaManager

    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    quota = QuotaManager(settings, factory, redis=redis)
    locks = CoalesceLockManager(redis, settings)
    ctx = CollectorContext(
        provider=None,  # type: ignore[arg-type]  # dispatch-only ctx: no fetch here
        quota=quota,
        locks=locks,
        freshness=FreshnessPolicy(settings),
        session_factory=factory,
        settings=settings,
        redis=redis,
        phase=decision.phase,
    )
    counters: dict[str, int] = {}

    async def _enqueue(name: str, **inputs: object) -> None:
        nonlocal counters

        try:
            collector = resolve(name)
        except KeyError:
            logger.warning("unknown collector %r skipped by scanner", name)
            return
        lock_key = collector.lock_key(**{k: v for k, v in inputs.items() if k != "phase"})
        phase_value = str(inputs.get("phase", decision.phase.value))
        job_key = f"collect:{name}:{hashlib.sha1(lock_key.encode()).hexdigest()[:20]}:{phase_value}"
        try:
            async with factory() as session:
                job, created = await create_or_get_job(
                    session,
                    job_type=f"collect:{name}",
                    idempotency_key=job_key,
                    scheduled_for=datetime.now(UTC),
                )
                await session.commit()
                job_id = str(job.id)
        except Exception:
            logger.exception("could not create collector job row", extra={"name": name})
            return

        if created:
            try:
                from sports_intelligence.workers.tasks.collect import collect_task

                payload = {k: v for k, v in inputs.items() if k != "phase"}
                collect_task.apply_async(args=[job_id, name, json.dumps(payload), phase_value])
            except Exception:
                logger.error("collector job enqueue failed; marking job FAILED", exc_info=True)
                async with factory() as session:
                    await update_job_status(session, job_id, JobStatus.FAILED)
                    await session.commit()
                raise
        counters[name] = counters.get(name, 0) + 1

    await execute_plan(settings, ctx, decisions=[decision], enqueue_collector=_enqueue)
    try:
        await redis.aclose()
    except Exception:  # noqa: BLE001
        logger.warning("redis cleanup failed during pre-match scan", exc_info=True)
    return counters
