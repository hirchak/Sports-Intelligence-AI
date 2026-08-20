from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from sports_intelligence.api.app import create_app
from sports_intelligence.core.config import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="mock",
        database_url="postgresql+asyncpg://test:test@127.0.0.1:1/sports_test",
        redis_url="redis://127.0.0.1:1/0",
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client
