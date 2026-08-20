from __future__ import annotations

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from sports_intelligence.core.logging import get_logger
from sports_intelligence.schemas.health import ComponentChecks

logger = get_logger(__name__)


async def check_database(engine: AsyncEngine) -> bool:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return True
    except Exception:
        logger.warning("database readiness check failed", exc_info=True)
        return False


async def check_redis(redis_client: Redis) -> bool:
    try:
        return bool(await redis_client.ping())
    except Exception:
        logger.warning("redis readiness check failed", exc_info=True)
        return False


async def check_readiness(engine: AsyncEngine, redis_client: Redis) -> tuple[ComponentChecks, bool]:
    database_ok = await check_database(engine)
    redis_ok = await check_redis(redis_client)
    checks = ComponentChecks(
        database="ok" if database_ok else "unavailable",
        redis="ok" if redis_ok else "unavailable",
    )
    return checks, database_ok and redis_ok
