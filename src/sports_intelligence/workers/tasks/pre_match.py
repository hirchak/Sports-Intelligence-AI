"""Pre-match scanner Beat task (M4.1 §12 / M4.3 §1/§7/§9).

CHEAP by design: reads upcoming fixtures from PostgreSQL, builds a
deterministic plan, and ENQUEUES collector jobs (`sports.collect`) with
proper Job rows + attempt recording. No external collectors run inline;
no provider calls happen inside this task.

M4.3 additions:

- odds collector is SKIPPED when the odds capability is disabled
  (never a silent MOCK in non-mock environments);
- observability counters distinguish planned intents, jobs created,
  jobs reused and actual broker enqueues (reused jobs are never
  reported as newly enqueued);
- FAILED jobs in the SAME refresh opportunity are re-enqueued under the
  SAME job UUID using a CAS status transition (FAILED → PENDING only);
  RUNNING/SUCCEEDED are never downgraded;
- Redis cleanup is finally-safe even when enqueueing raises.
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
    transition_job_status_if,
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
        return {"planned": 0, "decisions": 0, "error": "planning_failed"}

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

    totals = {
        "planned": 0,
        "jobs_created": 0,
        "jobs_reused": 0,
        "jobs_enqueued": 0,
    }
    by_category: dict[str, dict[str, int]] = {}
    for decision in decisions:
        try:
            result = await _dispatch_decision(factory, decision, now=started_at)
            for key in totals:
                totals[key] += result.get(key, 0)
            for category, counts in result.get("by_category", {}).items():
                bucket = by_category.setdefault(
                    category, {"planned": 0, "created": 0, "reused": 0, "enqueued": 0}
                )
                for key, value in counts.items():
                    bucket[key] += value

            if (
                not result.get("has_in_flight_collectors", False)
                and result.get("jobs_enqueued", 0) == 0
            ):
                await _try_enqueue_context_build(factory, decision, as_of=started_at)
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
        "decisions": len(decisions),
        "scan_job_id": scan_job_id,
        **totals,
        "by_category": by_category,
    }


async def _dispatch_decision(
    factory: Any,
    decision: PreMatchDecision,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Create-or-get Jobs per (collector, lock key, phase, opportunity)
    and enqueue `sports.collect`. Returns observability counters:
    planned / jobs_created / jobs_reused / jobs_enqueued per category."""
    from redis.asyncio import Redis

    from sports_intelligence.collectors.framework import (
        CollectorContext,
        collector_refresh_due,
        resolve,
    )
    from sports_intelligence.collectors.freshness import FreshnessPolicy
    from sports_intelligence.collectors.locks import CoalesceLockManager
    from sports_intelligence.collectors.pre_match_scan import execute_plan
    from sports_intelligence.collectors.quota import QuotaManager
    from sports_intelligence.collectors.refresh import refresh_opportunity_suffix

    settings = get_settings()
    redis: Redis | None = None
    counters: dict[str, dict[str, int]] = {}
    try:
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

        has_in_flight_collectors = False

        async def _enqueue(name: str, **inputs: object) -> None:
            nonlocal has_in_flight_collectors
            bucket = counters.setdefault(
                name, {"planned": 0, "created": 0, "reused": 0, "enqueued": 0}
            )
            bucket["planned"] += 1

            try:
                collector = resolve(name)
            except KeyError:
                logger.warning("unknown collector %r skipped by scanner", name)
                return

            # M4.3 §1: odds disabled → the planner never enqueues odds.
            if name == "odds" and not settings.odds_capability_enabled:
                logger.info("odds collector skipped: odds capability disabled in this environment")
                return

            # M5: research disabled → scanner never enqueues research.
            if name == "research" and not settings.research_capability_enabled:
                logger.info(
                    "research collector skipped: research capability disabled in this environment"
                )
                return

            # M4.4 §2: standings and team_stats require exact season identity.
            if name in ("standings", "team_stats") and not inputs.get("season_id"):
                logger.warning(
                    "%s collector skipped: fixture %s has no season_id; refusing to guess season",
                    name,
                    decision.fixture_id,
                )
                return

            lock_key = collector.lock_key(**{k: v for k, v in inputs.items() if k != "phase"})
            phase_value = str(inputs.get("phase", decision.phase.value))

            ttl = FreshnessPolicy(settings).ttl_for(collector.category, decision.phase)
            # M4.4 §3: the refresh opportunity is the actual due
            # generation — captured + effective TTL (stable until a new
            # snapshot persists); no snapshot yet → `due:missing`.
            # A FRESH snapshot produces NO job at all.
            latest_captured_at: datetime | None = None
            latest_status: str | None = None
            if name != "lineups":
                try:
                    async with factory() as session:
                        if hasattr(collector, "latest_run_info"):
                            run_info = await collector.latest_run_info(
                                session,
                                fixture_id=inputs["fixture_id"],
                                error_retry_ttl_seconds=settings.research_provider_error_retry_seconds,
                            )
                            latest_captured_at = run_info.captured_at
                            latest_status = run_info.status
                        else:
                            latest_captured_at, _ = await collector.latest_snapshot(
                                session,
                                **{k: v for k, v in inputs.items() if k != "phase"},
                            )
                except Exception:  # noqa: BLE001 — best-effort DB read
                    logger.warning(
                        "could not read latest snapshot for opportunity identity",
                        extra={"name": name},
                    )
                    latest_captured_at = None
                    latest_status = None
                is_due = await collector_refresh_due(
                    collector, ctx, inputs, latest_captured_at, now or datetime.now(UTC)
                )
                if not is_due:
                    # Fresh snapshot: no collector job needed.
                    return
            opportunity = refresh_opportunity_suffix(
                collector_name=name,
                kickoff_at=decision.kickoff_at,
                now=now or datetime.now(UTC),
                windows_minutes=settings.lineup_window_t_minutes,
                ttl_seconds=int(ttl.total_seconds()),
                latest_captured_at=latest_captured_at,
                status=latest_status,
                error_retry_ttl_seconds=settings.research_provider_error_retry_seconds,
            )
            job_key = (
                f"collect:{name}:{hashlib.sha1(lock_key.encode()).hexdigest()[:20]}:"
                f"{phase_value}:{opportunity}"
            )
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

            enqueue_needed = created
            if not created:
                # M4.3 §7: a FAILED job in the SAME opportunity is
                # re-enqueued under the SAME uuid via CAS
                # (FAILED → PENDING); RUNNING/SUCCEEDED are untouched.
                async with factory() as session:
                    requeued = await transition_job_status_if(
                        session, job_id, JobStatus.FAILED, JobStatus.PENDING
                    )
                    await session.commit()
                if requeued:
                    enqueue_needed = True
                else:
                    bucket["reused"] += 1
                    status_val = (
                        job.status.value if hasattr(job.status, "value") else str(job.status)
                    )
                    if status_val in (JobStatus.PENDING.value, JobStatus.RUNNING.value):
                        has_in_flight_collectors = True
            else:
                bucket["created"] += 1

            if enqueue_needed:
                has_in_flight_collectors = True
                try:
                    from sports_intelligence.workers.tasks.collect import collect_task

                    payload = {k: v for k, v in inputs.items() if k != "phase"}
                    queue = "research_io" if name == "research" else "sports_io"
                    collect_task.apply_async(
                        args=[job_id, name, json.dumps(payload), phase_value],
                        queue=queue,
                    )
                    bucket["enqueued"] += 1
                except Exception:
                    logger.error("collector job enqueue failed; marking job FAILED", exc_info=True)
                    async with factory() as session:
                        await update_job_status(session, job_id, JobStatus.FAILED)
                        await session.commit()
                    raise

        await execute_plan(settings, ctx, decisions=[decision], enqueue_collector=_enqueue)
    finally:
        if redis is not None:
            try:
                await redis.aclose()
            except Exception:  # noqa: BLE001
                logger.warning("redis cleanup failed during pre-match scan", exc_info=True)

    return {
        "planned": sum(b["planned"] for b in counters.values()),
        "jobs_created": sum(b["created"] for b in counters.values()),
        "jobs_reused": sum(b["reused"] for b in counters.values()),
        "jobs_enqueued": sum(b["enqueued"] for b in counters.values()),
        "has_in_flight_collectors": has_in_flight_collectors,
        "by_category": counters,
    }


async def _try_enqueue_context_build(
    factory: Any,
    decision: PreMatchDecision,
    *,
    as_of: datetime,
) -> None:
    from sports_intelligence.collectors.freshness import FreshnessPolicy
    from sports_intelligence.context.builder import (
        ContextBuildPolicy,
        compute_build_config_fingerprint,
    )
    from sports_intelligence.context.provenance import build_source_manifest
    from sports_intelligence.context.selector import select_evidence
    from sports_intelligence.core.config import get_settings
    from sports_intelligence.quality.engine import build_quality_policy
    from sports_intelligence.workers.tasks.context import build_match_context_task

    try:
        settings = get_settings()
        fid = uuid.UUID(decision.fixture_id)
        async with factory() as session:
            evidence = await select_evidence(
                session,
                fixture_id=fid,
                forecast_phase=decision.phase,
                as_of=as_of,
                research_enabled=settings.research_capability_enabled,
            )
        manifest = build_source_manifest(evidence)
        quality_policy = build_quality_policy(settings)
        freshness_policy = FreshnessPolicy(settings)
        build_policy = ContextBuildPolicy(
            quality_policy=quality_policy,
            freshness_policy=freshness_policy,
            research_enabled=settings.research_capability_enabled,
        )
        build_config_fingerprint = compute_build_config_fingerprint(build_policy)
        freshness_generation = freshness_policy.compute_freshness_generation(evidence)
        job_key = (
            f"context_build:{decision.fixture_id}:{decision.phase.value}:"
            f"{manifest.source_fingerprint}:{build_config_fingerprint}:{freshness_generation}"
        )
        async with factory() as session:
            job, created = await create_or_get_job(
                session,
                job_type="context:build_match_context",
                idempotency_key=job_key,
                scheduled_for=as_of,
            )
            await session.commit()
            job_id = str(job.id)

        enqueue_needed = created
        if not created:
            async with factory() as session:
                requeued = await transition_job_status_if(
                    session, job_id, JobStatus.FAILED, JobStatus.PENDING
                )
                await session.commit()
            if requeued:
                enqueue_needed = True

        if enqueue_needed:
            build_match_context_task.apply_async(
                args=[job_id, decision.fixture_id, decision.phase.value, as_of.isoformat()],
                queue="evaluation",
            )
            logger.info(
                "enqueued deterministic context build",
                extra={"fixture_id": decision.fixture_id, "phase": decision.phase.value},
            )
    except Exception:
        logger.warning(
            "could not enqueue context build job",
            extra={"fixture_id": decision.fixture_id},
            exc_info=True,
        )
