from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from redis import exceptions as redis_exceptions

from sports_intelligence.api import app as app_module
from sports_intelligence.api.app import create_app, lifespan
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


class TrackingRedisClient:
    def __init__(self) -> None:
        self.closed = False

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        self.closed = True


class FakeConnection:
    async def execute(self, statement: object) -> None:
        return None

    async def __aenter__(self) -> FakeConnection:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None


class TrackingEngine:
    def __init__(self) -> None:
        self.disposed = False

    def connect(self) -> FakeConnection:
        return FakeConnection()

    async def dispose(self) -> None:
        self.disposed = True


async def test_lifespan_cleanup_runs_on_exceptional_exit(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracking_redis = TrackingRedisClient()
    tracking_engine = TrackingEngine()
    monkeypatch.setattr(app_module, "create_engine", lambda url: tracking_engine)
    monkeypatch.setattr(
        app_module.aioredis.Redis, "from_url", lambda *args, **kwargs: tracking_redis
    )

    application = FastAPI(lifespan=lifespan)
    application.state.settings = settings

    with pytest.raises(RuntimeError, match="simulated failure"):
        async with application.router.lifespan_context(application):
            raise RuntimeError("simulated failure")

    assert tracking_redis.closed is True
    assert tracking_engine.disposed is True
