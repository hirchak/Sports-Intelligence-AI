from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from sqlalchemy import text

from sports_intelligence.api.routes import health
from sports_intelligence.core.config import Settings, get_settings
from sports_intelligence.core.logging import get_logger, setup_logging
from sports_intelligence.db.session import create_engine, create_session_factory

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings: Settings = application.state.settings
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    redis_client = aioredis.Redis.from_url(settings.redis_url, socket_connect_timeout=2)

    application.state.engine = engine
    application.state.session_factory = session_factory
    application.state.redis_client = redis_client

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        logger.info("startup validation: database reachable")
    except Exception:
        logger.warning("startup validation: database unreachable", exc_info=True)

    try:
        await redis_client.ping()
        logger.info("startup validation: redis reachable")
    except Exception:
        logger.warning("startup validation: redis unreachable", exc_info=True)

    yield

    await redis_client.aclose()
    await engine.dispose()
    logger.info("application shutdown complete")


def create_app(settings: Settings) -> FastAPI:
    setup_logging(settings.log_level)
    application = FastAPI(title="Sports Intelligence AI", version="0.2.0", lifespan=lifespan)
    application.state.settings = settings
    application.include_router(health.router)
    return application


app = create_app(get_settings())
