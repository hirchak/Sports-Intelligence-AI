from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from redis import exceptions as redis_exceptions

from sports_intelligence.api.app import create_app
from sports_intelligence.core.config import Settings


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


def test_ready_returns_503_without_database_and_redis(client: TestClient) -> None:
    response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"] == "unavailable"
    assert body["checks"]["redis"] == "unavailable"


def test_lifespan_populates_shared_resources(client: TestClient) -> None:
    state = client.app.state
    assert state.settings is not None
    assert state.engine is not None
    assert state.session_factory is not None
    assert state.redis_client is not None


async def test_redis_client_is_closed_after_shutdown(settings: Settings) -> None:
    application = create_app(settings)
    with TestClient(application):
        redis_client = application.state.redis_client
    with pytest.raises((redis_exceptions.ConnectionError, RuntimeError)):
        await redis_client.ping()
