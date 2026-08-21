from __future__ import annotations

import asyncio
import os
from typing import Annotated

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from helpers import fetch_table_names, require_test_database
from sports_intelligence.api.dependencies import get_session
from sports_intelligence.core.config import Settings

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "")

requires_services = pytest.mark.skipif(
    not (TEST_DATABASE_URL and TEST_REDIS_URL),
    reason="TEST_DATABASE_URL and TEST_REDIS_URL are required",
)

pytestmark = [pytest.mark.integration, requires_services]


def test_ready_returns_200_with_real_services(service_client: TestClient) -> None:
    response = service_client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == {"database": "ok", "redis": "ok"}


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


def test_migrations_apply_downgrade_and_reapply_on_fresh_database(
    alembic_config: AlembicConfig, service_settings: Settings
) -> None:
    require_test_database(TEST_DATABASE_URL)

    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    command.upgrade(alembic_config, "head")

    tables = asyncio.run(fetch_table_names(service_settings.database_url))
    assert {"jobs", "job_attempts", "alembic_version"}.issubset(tables)
    assert {"leagues", "fixtures", "provider_observations"}.issubset(tables)

    command.downgrade(alembic_config, "base")
    tables_after_downgrade = asyncio.run(fetch_table_names(service_settings.database_url))
    assert "jobs" not in tables_after_downgrade
    assert "fixtures" not in tables_after_downgrade

    command.upgrade(alembic_config, "head")
    tables_after_reapply = asyncio.run(fetch_table_names(service_settings.database_url))
    assert {"jobs", "job_attempts", "fixtures", "provider_observations"}.issubset(
        tables_after_reapply
    )


def test_no_schema_drift_at_head(alembic_config: AlembicConfig) -> None:
    require_test_database(TEST_DATABASE_URL)
    command.check(alembic_config)
