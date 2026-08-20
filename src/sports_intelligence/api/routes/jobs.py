from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from sports_intelligence.api.dependencies import get_session
from sports_intelligence.core.time import utc_now
from sports_intelligence.pipelines.discover_fixtures import create_or_get_job
from sports_intelligence.schemas.fixtures import DiscoverJobRequest, DiscoverJobResponse
from sports_intelligence.workers.tasks import sports as sports_tasks

router = APIRouter(prefix="/v1/jobs", tags=["jobs"])

SessionDependency = Annotated[AsyncSession, Depends(get_session)]


@router.post("/discover", response_model=DiscoverJobResponse)
async def create_discovery_job(
    payload: DiscoverJobRequest,
    request: Request,
    session: SessionDependency,
) -> DiscoverJobResponse:
    settings = request.app.state.settings
    fixture_date = payload.date or utc_now().date()
    idempotency_key = f"discover:{settings.sports_provider}:{fixture_date.isoformat()}"

    job, created = await create_or_get_job(
        session,
        job_type="discover_fixtures",
        idempotency_key=idempotency_key,
        scheduled_for=utc_now(),
    )
    await session.commit()

    if created:
        sports_tasks.discover_fixtures_task.apply_async(
            args=[str(job.id), fixture_date.isoformat()], queue="sports_io"
        )

    return DiscoverJobResponse(
        job_id=job.id,
        idempotency_key=idempotency_key,
        status=job.status,
        already_queued=not created,
    )
