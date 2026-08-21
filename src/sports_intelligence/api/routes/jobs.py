from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from sports_intelligence.api.dependencies import get_session
from sports_intelligence.core.job_status import JobStatus
from sports_intelligence.core.league_config import load_league_config
from sports_intelligence.core.logging import get_logger
from sports_intelligence.core.time import local_today, utc_now
from sports_intelligence.pipelines.discover_fixtures import (
    create_or_get_job,
    transition_job_status_if,
    update_job_status,
)
from sports_intelligence.schemas.fixtures import DiscoverJobRequest, DiscoverJobResponse
from sports_intelligence.workers.tasks import sports as sports_tasks

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])

SessionDependency = Annotated[AsyncSession, Depends(get_session)]

logger = get_logger(__name__)


@router.post("/discover", response_model=DiscoverJobResponse)
async def create_discovery_job(
    payload: DiscoverJobRequest,
    request: Request,
    session: SessionDependency,
) -> DiscoverJobResponse:
    settings = request.app.state.settings
    league_config = load_league_config(settings.leagues_config_path)
    if payload.date is not None:
        fixture_date = payload.date
    else:
        fixture_date = local_today(utc_now(), settings.app_timezone)
    fixture_date_iso = fixture_date.isoformat()
    idempotency_key = (
        f"discover:{settings.sports_provider}:{fixture_date_iso}"
        f":v{league_config.version}:{settings.app_timezone}"
    )

    job, created = await create_or_get_job(
        session,
        job_type="discover_fixtures",
        idempotency_key=idempotency_key,
        scheduled_for=utc_now(),
    )
    await session.commit()

    if created:
        if not _try_enqueue(job.id, fixture_date_iso):
            await update_job_status(session, str(job.id), JobStatus.FAILED)
            await session.commit()
            raise HTTPException(
                status_code=502,
                detail=DiscoverJobResponse(
                    job_id=job.id,
                    idempotency_key=idempotency_key,
                    status=JobStatus.FAILED.value,
                    already_queued=False,
                ).model_dump(mode="json"),
            )
        return DiscoverJobResponse(
            job_id=job.id,
            idempotency_key=idempotency_key,
            status=JobStatus.PENDING.value,
            already_queued=False,
        )

    if job.status == JobStatus.FAILED.value:
        if not _try_enqueue(job.id, fixture_date_iso):
            raise HTTPException(
                status_code=502,
                detail=DiscoverJobResponse(
                    job_id=job.id,
                    idempotency_key=idempotency_key,
                    status=JobStatus.FAILED.value,
                    already_queued=False,
                ).model_dump(mode="json"),
            )
        await transition_job_status_if(session, str(job.id), JobStatus.FAILED, JobStatus.PENDING)
        await session.commit()
        await session.refresh(job)
        return DiscoverJobResponse(
            job_id=job.id,
            idempotency_key=idempotency_key,
            status=job.status,
            already_queued=False,
        )

    return DiscoverJobResponse(
        job_id=job.id,
        idempotency_key=idempotency_key,
        status=job.status,
        already_queued=True,
    )


def _try_enqueue(job_id: object, fixture_date: str) -> bool:
    try:
        sports_tasks.discover_fixtures_task.apply_async(
            args=[str(job_id), fixture_date], queue="sports_io"
        )
        return True
    except Exception:
        logger.exception("failed to enqueue discovery job", extra={"job_id": str(job_id)})
        return False
