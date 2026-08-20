from __future__ import annotations

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from sports_intelligence.core.logging import get_logger

logger = get_logger(__name__)


async def close_resources(redis_client: Redis, engine: AsyncEngine) -> None:
    try:
        await redis_client.aclose()
    except Exception:
        logger.warning("redis cleanup failed during shutdown", exc_info=True)
    try:
        await engine.dispose()
    except Exception:
        logger.warning("database engine cleanup failed during shutdown", exc_info=True)
