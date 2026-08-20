from __future__ import annotations

import urllib.parse

from sqlalchemy import inspect
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from sports_intelligence.db.session import create_engine


def database_name_from_url(url: str) -> str:
    return urllib.parse.urlparse(url).path.strip("/")


def require_test_database(url: str) -> None:
    name = database_name_from_url(url)
    if not name.endswith("_test"):
        raise RuntimeError(
            "integration tests must run against a dedicated test database "
            "(name must end with '_test'); "
            f"TEST_DATABASE_URL points at {name!r}"
        )


def sync_table_names(connection: Connection) -> set[str]:
    return set(inspect(connection).get_table_names())


async def fetch_table_names(database_url: str) -> set[str]:
    engine: AsyncEngine = create_engine(database_url)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(sync_table_names)
    finally:
        await engine.dispose()
