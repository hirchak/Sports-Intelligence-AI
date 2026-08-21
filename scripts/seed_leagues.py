from __future__ import annotations

import asyncio

from sports_intelligence.core.config import get_settings
from sports_intelligence.core.league_config import load_league_config
from sports_intelligence.db.repositories.discovery import upsert_league_id
from sports_intelligence.db.session import create_engine, create_session_factory


async def main() -> None:
    settings = get_settings()
    league_config = load_league_config(settings.leagues_config_path)
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    try:
        async with session_factory() as session:
            for entry in league_config.leagues:
                await upsert_league_id(
                    session,
                    slug=entry.slug,
                    name=entry.name,
                    country=entry.country,
                    enabled=entry.enabled,
                )
            await session.commit()
        print(f"seeded {len(league_config.leagues)} leagues")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
