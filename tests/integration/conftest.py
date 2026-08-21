from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi.testclient import TestClient

from helpers import require_test_database
from sports_intelligence.api.app import create_app
from sports_intelligence.core.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
TEST_REDIS_URL = os.environ.get("TEST_REDIS_URL", "")

requires_services = pytest.mark.skipif(
    not (TEST_DATABASE_URL and TEST_REDIS_URL),
    reason="TEST_DATABASE_URL and TEST_REDIS_URL are required",
)


@pytest.fixture(scope="session", autouse=True)
def migrated_test_database() -> Iterator[None]:
    if not (TEST_DATABASE_URL and TEST_REDIS_URL):
        yield
        return
    require_test_database(TEST_DATABASE_URL)
    config = AlembicConfig(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(config, "head")
    yield


@pytest.fixture
def service_settings() -> Settings:
    require_test_database(TEST_DATABASE_URL)
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


@pytest.fixture
def alembic_config() -> AlembicConfig:
    require_test_database(TEST_DATABASE_URL)
    config = AlembicConfig(str(REPO_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return config
