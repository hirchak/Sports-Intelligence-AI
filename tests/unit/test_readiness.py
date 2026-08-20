from __future__ import annotations

from sports_intelligence.api.readiness import check_readiness
from sports_intelligence.db.session import create_engine

UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://test:test@127.0.0.1:1/sports_test"


class FakeRedisAvailable:
    async def ping(self) -> bool:
        return True


class FakeRedisUnavailable:
    async def ping(self) -> bool:
        raise ConnectionError("redis unavailable")


async def test_readiness_reports_both_components_unavailable() -> None:
    checks, ready = await check_readiness(
        create_engine(UNREACHABLE_DATABASE_URL), FakeRedisUnavailable()
    )
    assert ready is False
    assert checks.database == "unavailable"
    assert checks.redis == "unavailable"


async def test_readiness_isolates_component_status() -> None:
    checks, ready = await check_readiness(
        create_engine(UNREACHABLE_DATABASE_URL), FakeRedisAvailable()
    )
    assert ready is False
    assert checks.database == "unavailable"
    assert checks.redis == "ok"
