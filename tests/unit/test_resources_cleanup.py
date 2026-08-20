from __future__ import annotations

from sports_intelligence.api.resources import close_resources


class FailingRedis:
    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True
        raise ConnectionError("redis close failed")


class TrackingEngine:
    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


class FailingEngine:
    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True
        raise RuntimeError("engine dispose failed")


async def test_close_resources_still_closes_engine_when_redis_cleanup_fails() -> None:
    redis_client = FailingRedis()
    engine = TrackingEngine()

    await close_resources(redis_client, engine)

    assert redis_client.closed is True
    assert engine.disposed is True


async def test_close_resources_does_not_raise_when_both_cleanups_fail() -> None:
    await close_resources(FailingRedis(), FailingEngine())
