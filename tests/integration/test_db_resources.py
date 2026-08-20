from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession

from sports_intelligence.api.app import create_app
from sports_intelligence.api.dependencies import get_session
from sports_intelligence.core.config import Settings
from sports_intelligence.db.session import create_engine

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "")

requires_services = pytest.mark.skipif(
    not (TEST_DATABASE_URL and TEST_REDIS_URL),
    reason="TEST_DATABASE_URL and TEST_REDIS_URL are required",
)


@pytest.fixture
def service_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="mock",
        database_url=TEST_DATABASE_URL,
        redis_url=TEST_REDIS_URL,
    )


@pytest.fixture
def service_client(service_settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(service_settings)) as test_client:
        yield test_client


def _alembic_config() -> AlembicConfig:
    config = AlembicConfig(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return config


def _sync_table_names(connection: Connection) -> set[str]:
    return set(inspect(connection).get_table_names())


async def _table_names() -> set[str]:
    engine = create_engine(TEST_DATABASE_URL)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(_sync_table_names)
    finally:
        await engine.dispose()


@requires_services
def test_ready_returns_200_with_real_services(service_client: TestClient) -> None:
    response = service_client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == {"database": "ok", "redis": "ok"}


@requires_services
def test_session_dependency_provides_working_session(service_client: TestClient) -> None:
    temporary_router = APIRouter()

    @temporary_router.get("/__test_db")
    async def test_db(session: Annotated[AsyncSession, Depends(get_session)]) -> dict[str, int]:
        result = await session.execute(text("SELECT 1"))
        return {"value": result.scalar_one()}

    service_client.app.include_router(temporary_router)
    response = service_client.get("/__test_db")
    assert response.status_code == 200
    assert response.json() == {"value": 1}


@requires_services
def test_migrations_apply_downgrade_and_reapply_on_fresh_database() -> None:
    config = _alembic_config()
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    command.upgrade(config, "head")

    tables = asyncio.run(_table_names())
    assert {"jobs", "job_attempts", "alembic_version"}.issubset(tables)

    command.downgrade(config, "base")
    tables_after_downgrade = asyncio.run(_table_names())
    assert "jobs" not in tables_after_downgrade
    assert "job_attempts" not in tables_after_downgrade

    command.upgrade(config, "head")
    tables_after_reapply = asyncio.run(_table_names())
    assert {"jobs", "job_attempts"}.issubset(tables_after_reapply)
