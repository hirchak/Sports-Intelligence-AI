from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sports_intelligence.api.dependencies import get_session
from sports_intelligence.db.models import Fixture, MatchContextRecord, PredictionRun
from sports_intelligence.predictions.contracts import Role, Variant
from sports_intelligence.predictions.service import (
    enqueue_prediction,
    read_prediction,
    request_prediction,
)
from sports_intelligence.schemas.predictions import (
    AnalyzeRequest,
    AnalyzeResponse,
    PredictionDetail,
    PredictionSummary,
)

router = APIRouter(prefix="/v1", tags=["predictions"])
SessionDependency = Annotated[AsyncSession, Depends(get_session)]


@router.post("/fixtures/{fixture_id}/analyze", response_model=AnalyzeResponse, status_code=202)
async def analyze_fixture(
    fixture_id: UUID,
    payload: AnalyzeRequest,
    request: Request,
    session: SessionDependency,
) -> AnalyzeResponse:
    if await session.get(Fixture, fixture_id) is None:
        raise HTTPException(404, "fixture_not_found")
    query = select(MatchContextRecord).where(
        MatchContextRecord.fixture_id == fixture_id,
        MatchContextRecord.forecast_phase == payload.phase,
    )
    if payload.context_id:
        query = query.where(MatchContextRecord.id == payload.context_id)
    if payload.as_of:
        query = query.where(MatchContextRecord.as_of <= payload.as_of)
    record = await session.scalar(
        query.order_by(
            MatchContextRecord.as_of.desc(),
            MatchContextRecord.created_at.desc(),
            MatchContextRecord.id.asc(),
        ).limit(1)
    )
    if record is None:
        raise HTTPException(409, "match_context_not_ready_for_requested_phase")
    try:
        run, created = await request_prediction(
            session,
            record=record,
            settings=request.app.state.settings,
            role=payload.role,
            variant=payload.variant,
            route_override=payload.route_override,
            rerun_key=str(payload.rerun_key) if payload.rerun_key else None,
        )
    except (ValueError, OSError):
        await session.rollback()
        raise HTTPException(422, "invalid_prediction_configuration_or_context") from None
    try:
        await enqueue_prediction(session, run, created)
    except RuntimeError:
        raise HTTPException(502, "prediction_enqueue_failed") from None
    return AnalyzeResponse(
        run_id=run.id,
        job_id=run.job_id,
        status=run.status,
        already_queued=not created,
        requested_identity=run.requested_identity,
    )


@router.get("/predictions", response_model=list[PredictionSummary])
async def list_predictions(
    session: SessionDependency,
    fixture_id: UUID | None = None,
    role: Role = Role.PRIMARY,
    variant: Variant | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
) -> list[PredictionRun]:
    query = select(PredictionRun).where(PredictionRun.role == role.value)
    if fixture_id:
        query = query.where(PredictionRun.fixture_id == fixture_id)
    if variant:
        query = query.where(PredictionRun.variant == variant.value)
    return list(
        (
            await session.scalars(
                query.order_by(
                    PredictionRun.created_at.desc(),
                    PredictionRun.id.asc(),
                )
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )


@router.get("/predictions/{run_id}", response_model=PredictionDetail)
async def prediction_detail(run_id: UUID, session: SessionDependency) -> dict[str, object]:
    value = await read_prediction(session, run_id)
    if value is None:
        raise HTTPException(404, "prediction_not_found")
    return value
