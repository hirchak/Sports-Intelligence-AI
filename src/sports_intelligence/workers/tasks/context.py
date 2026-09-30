from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from sports_intelligence.collectors.freshness import FreshnessPolicy
from sports_intelligence.context.builder import build_and_persist_match_context
from sports_intelligence.core.config import Settings, get_settings
from sports_intelligence.core.job_status import JobStatus
from sports_intelligence.core.logging import get_logger
from sports_intelligence.core.phases import ForecastPhase
from sports_intelligence.db.session import create_engine, create_session_factory
from sports_intelligence.pipelines.discover_fixtures import update_job_status
from sports_intelligence.quality.engine import build_quality_policy
from sports_intelligence.workers.celery_app import celery_app
from sports_intelligence.workers.utils import record_job_attempt

logger = get_logger(__name__)


@celery_app.task(name="context.build_match_context", queue="evaluation")  # type: ignore[untyped-decorator]
def build_match_context_task(
    job_id: str,
    fixture_id: str,
    phase: str,
    as_of_iso: str,
) -> dict[str, Any]:
    return asyncio.run(_run_build(job_id, fixture_id, phase, as_of_iso))


async def _run_build(
    job_id: str,
    fixture_id: str,
    phase: str,
    as_of_iso: str,
    *,
    settings: Settings | None = None,
    session_factory: Any | None = None,
) -> dict[str, Any]:
    resolved_settings = settings or get_settings()
    created_engine = None
    if session_factory is None:
        created_engine = create_engine(resolved_settings.database_url)
        factory = create_session_factory(created_engine)
    else:
        factory = session_factory
    started_at = datetime.now(UTC)
    fid = uuid.UUID(fixture_id)
    forecast_phase = ForecastPhase(phase)
    as_of = datetime.fromisoformat(as_of_iso)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=UTC)

    async with factory() as session:
        await update_job_status(session, job_id, JobStatus.RUNNING)
        await session.commit()

    try:
        quality_policy = build_quality_policy(resolved_settings)
        freshness_policy = FreshnessPolicy(resolved_settings)
        async with factory() as session:
            context_rec, quality_rec, feat_rec, _ = await build_and_persist_match_context(
                session,
                fixture_id=fid,
                forecast_phase=forecast_phase,
                as_of=as_of,
                policy=quality_policy,
                freshness_policy=freshness_policy,
                research_enabled=resolved_settings.research_capability_enabled,
            )

        async with factory() as session:
            await update_job_status(session, job_id, JobStatus.SUCCEEDED)
            await session.commit()

        await record_job_attempt(
            factory,
            job_id=uuid.UUID(job_id),
            started_at=started_at,
            finished_at=datetime.now(UTC),
            outcome=JobStatus.SUCCEEDED.value,
            error=None,
        )

        return {
            "status": "success",
            "context_id": str(context_rec.id),
            "context_hash": context_rec.context_hash,
            "quality_report_id": str(quality_rec.id),
            "feature_snapshot_id": str(feat_rec.id),
            "overall_score": quality_rec.overall_score,
            "quality_band": quality_rec.quality_band,
            "can_predict": quality_rec.can_predict,
        }
    except Exception as exc:
        logger.exception("build_match_context_task failed", extra={"fixture_id": fixture_id})
        async with factory() as session:
            await update_job_status(session, job_id, JobStatus.FAILED)
            await session.commit()

        await record_job_attempt(
            factory,
            job_id=uuid.UUID(job_id),
            started_at=started_at,
            finished_at=datetime.now(UTC),
            outcome=JobStatus.FAILED.value,
            error=exc,
        )
        raise
    finally:
        if created_engine is not None:
            await created_engine.dispose()
