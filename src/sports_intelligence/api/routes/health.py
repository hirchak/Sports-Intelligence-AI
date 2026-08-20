from __future__ import annotations

from fastapi import APIRouter, Request, Response

from sports_intelligence.api.readiness import check_readiness
from sports_intelligence.schemas.health import HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="sports-intelligence")


@router.get("/ready", response_model=ReadinessResponse)
async def ready(request: Request, response: Response) -> ReadinessResponse:
    state = request.app.state
    checks, is_ready = await check_readiness(state.engine, state.redis_client)
    response.status_code = 200 if is_ready else 503
    return ReadinessResponse(
        status="ready" if is_ready else "not_ready",
        checks=checks,
    )
