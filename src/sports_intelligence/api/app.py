from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from sqlalchemy import text

from sports_intelligence.api.observability import RequestObservability
from sports_intelligence.api.resources import close_resources
from sports_intelligence.api.routes import (
    context,
    evaluation,
    experiments,
    fixtures,
    health,
    jobs,
    predictions,
    research,
    status,
)
from sports_intelligence.core.config import Settings, get_settings
from sports_intelligence.core.logging import get_logger, setup_logging
from sports_intelligence.core.redaction import register_secrets
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

    try:
        yield
    finally:
        await close_resources(redis_client, engine)
        logger.info("application shutdown complete")


def create_app(settings: Settings) -> FastAPI:
    register_secrets(settings.model_dump())
    setup_logging(settings.log_level)
    application = FastAPI(
        title="Sports Intelligence AI",
        version="1.0.0",
        lifespan=lifespan,
        debug=False,
        docs_url=None if settings.production_like else "/docs",
        redoc_url=None if settings.production_like else "/redoc",
        openapi_url=None if settings.production_like else "/openapi.json",
    )
    application.add_middleware(RequestObservability)
    application.state.settings = settings
    application.include_router(health.router)
    application.include_router(fixtures.router)
    application.include_router(jobs.router)
    application.include_router(status.router)
    application.include_router(research.router)
    application.include_router(context.router)
    application.include_router(predictions.router)
    application.include_router(evaluation.router)
    application.include_router(experiments.router)
    return application


app = create_app(get_settings())
