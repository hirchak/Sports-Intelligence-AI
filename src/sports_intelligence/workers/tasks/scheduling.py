"""Beat-facing scheduler tasks (M4.1 §1).

Celery Beat must never enqueue `sports.discover_fixtures` directly:
that worker requires the full immutable execution tuple
(job_id, fixture_date, expected_league_config_version, discovery_timezone).

`sports.schedule_discovery(slot)` is the scheduler-facing wrapper:

- resolves today in APP_TIMEZONE;
- loads the LeagueConfig and captures its version;
- captures provider + timezone;
- creates-or-gets a proper Job row with a slot-distinct idempotency key
  (morning ≠ refresh — the 13:00 run is NEVER suppressed by the
  successful 09:00 run);
- enqueues the existing discovery worker with the full argument tuple;
- preserves M2 config-version safety end-to-end;
- marks the job FAILED when enqueueing fails.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from sports_intelligence.core.config import get_settings
from sports_intelligence.core.job_status import JobStatus
from sports_intelligence.core.league_config import load_league_config
from sports_intelligence.core.logging import get_logger
from sports_intelligence.core.time import local_today
from sports_intelligence.db.session import create_engine, create_session_factory
from sports_intelligence.pipelines.discover_fixtures import (
    create_or_get_job,
    transition_job_status_if,
    update_job_status,
)
from sports_intelligence.workers.celery_app import celery_app

logger = get_logger(__name__)

SCHEDULE_SLOTS = ("morning", "refresh")


@celery_app.task(name="sports.schedule_discovery", queue="control")  # type: ignore[untyped-decorator]
def schedule_discovery_task(slot: str) -> dict[str, object]:
    if slot not in SCHEDULE_SLOTS:
        raise ValueError(f"unknown schedule slot {slot!r}; expected one of {SCHEDULE_SLOTS}")
    return asyncio.run(_run_schedule(slot))


async def _run_schedule(slot: str) -> dict[str, object]:
    if slot not in SCHEDULE_SLOTS:
        raise ValueError(f"unknown schedule slot {slot!r}; expected one of {SCHEDULE_SLOTS}")
    settings = get_settings()
    now_utc = datetime.now(UTC)
    day_local = local_today(now_utc, settings.app_timezone)
    date_iso = day_local.isoformat()

    engine = create_engine(settings.database_url)
    factory = create_session_factory(engine)
    try:
        league_config = load_league_config(settings.leagues_config_path)
        config_version = league_config.version

        # Slot-distinct identity: morning and refresh are separate
        # idempotent scheduled runs on the same day.
        idempotency_key = (
            f"discover:scheduled:{slot}:{settings.sports_provider}:"
            f"{date_iso}:v{config_version}:{settings.app_timezone}"
        )
        async with factory() as session:
            job, created = await create_or_get_job(
                session,
                job_type="discover_fixtures",
                idempotency_key=idempotency_key,
                scheduled_for=now_utc,
            )
            await session.commit()
            job_id = str(job.id)

        # M4.3 §7: a stranded FAILED scheduled job is re-enqueued under
        # the SAME uuid via CAS (FAILED → PENDING); RUNNING/SUCCEEDED
        # are never downgraded.
        enqueue_needed = created
        if not created:
            async with factory() as session:
                requeued = await transition_job_status_if(
                    session, job_id, JobStatus.FAILED, JobStatus.PENDING
                )
                await session.commit()
            enqueue_needed = requeued

        if enqueue_needed:
            try:
                from sports_intelligence.workers.tasks.sports import discover_fixtures_task

                await _enqueue(
                    discover_fixtures_task,
                    job_id=job_id,
                    fixture_date=date_iso,
                    expected_league_config_version=config_version,
                    discovery_timezone=settings.app_timezone,
                )
            except Exception:
                logger.error(
                    "scheduled discovery enqueue failed; marking job FAILED",
                    exc_info=True,
                    extra={"slot": slot, "job_id": job_id},
                )
                async with factory() as session:
                    await update_job_status(session, job_id, JobStatus.FAILED)
                    await session.commit()
                raise

        logger.info(
            "scheduled discovery dispatched",
            extra={
                "slot": slot,
                "job_id": job_id,
                "job_created": created,
                "fixture_date": date_iso,
                "config_version": config_version,
            },
        )
        return {
            "slot": slot,
            "job_id": job_id,
            "created": created,
            "fixture_date": date_iso,
            "config_version": config_version,
            "timezone": settings.app_timezone,
        }
    finally:
        try:
            await engine.dispose()
        except Exception:  # noqa: BLE001
            logger.warning("engine cleanup failed during scheduling", exc_info=True)


async def _enqueue(
    task: Any,
    *,
    job_id: str,
    fixture_date: str,
    expected_league_config_version: int,
    discovery_timezone: str,
) -> None:
    """Indirection point so tests can intercept broker dispatch."""
    task.apply_async(
        args=[
            job_id,
            fixture_date,
            expected_league_config_version,
            discovery_timezone,
        ]
    )


_ = uuid  # keep import surface stable for monkeypatching in tests
