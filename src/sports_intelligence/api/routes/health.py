from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter, Request, Response
from sqlalchemy import text

from sports_intelligence.core.logging import get_logger
from sports_intelligence.db.session import create_engine
from sports_intelligence.schemas.health import ComponentChecks, HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", service="sports-intelligence")


@router.get("/ready", response_model=ReadinessResponse)
async def ready(request: Request, response: Response) -> ReadinessResponse:
    settings = request.app.state.settings
    database_ok = await _check_database(settings.database_url)
    redis_ok = await _check_redis(settings.redis_url)
    is_ready = database_ok and redis_ok
    response.status_code = 200 if is_ready else 503
    return ReadinessResponse(
        status="ready" if is_ready else "not_ready",
        checks=ComponentChecks(
            database="ok" if database_ok else "unavailable",
            redis="ok" if redis_ok else "unavailable",
        ),
    )


async def _check_database(database_url: str) -> bool:
    engine = create_engine(database_url)
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.warning("database readiness check failed", exc_info=True)
        return False
    finally:
        await engine.dispose()


async def _check_redis(redis_url: str) -> bool:
    client = aioredis.Redis.from_url(redis_url, socket_connect_timeout=2)
    try:
        return bool(await client.ping())
    except Exception:
        logger.warning("redis readiness check failed", exc_info=True)
        return False
    finally:
        await client.aclose()
