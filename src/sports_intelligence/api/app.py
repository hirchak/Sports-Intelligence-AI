from __future__ import annotations

from fastapi import FastAPI

from sports_intelligence.api.routes import health
from sports_intelligence.core.config import Settings, get_settings
from sports_intelligence.core.logging import setup_logging


def create_app(settings: Settings) -> FastAPI:
    setup_logging(settings.log_level)
    application = FastAPI(title="Sports Intelligence AI", version="0.1.0")
    application.state.settings = settings
    application.include_router(health.router)
    return application


app = create_app(get_settings())
