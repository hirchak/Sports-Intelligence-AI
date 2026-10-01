"""M7 migration against populated accepted M6 schema, without changing old revisions."""

from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command

from m7_fakes import make_context
from sports_intelligence.context.models import MatchContextV1
from sports_intelligence.db.models import Fixture, League, MatchContextRecord, Team
from sports_intelligence.db.session import create_engine, create_session_factory

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("TEST_DATABASE_URL"),
        reason="test database required",
    ),
]


async def seed_m6(url):
    engine = create_engine(url)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            context = make_context()
            as_of = datetime.fromisoformat(context.as_of)
            league = League(
                slug="m7-migration-" + uuid4().hex[:8], name="Synthetic M6", enabled=True
            )
            home, away = Team(name="Synthetic home"), Team(name="Synthetic away")
            session.add_all([league, home, away])
            await session.flush()
            fixture = Fixture(
                league_id=league.id,
                home_team_id=home.id,
                away_team_id=away.id,
                kickoff_at=as_of + timedelta(hours=6),
                status="NS",
            )
            session.add(fixture)
            await session.flush()
            data = context.model_dump()
            data["fixture_id"] = data["fixture_identity"]["fixture_id"] = str(fixture.id)
            data["fixture_identity"].update(
                league_id=str(league.id), home_team_id=str(home.id), away_team_id=str(away.id)
            )
            context = MatchContextV1.model_validate(data)
            record = MatchContextRecord(
                fixture_id=fixture.id,
                forecast_phase="MORNING",
                as_of=as_of,
                schema_version="match_context_v1",
                context_jsonb=context.model_dump(),
                context_hash=hashlib.sha256(context.canonical_json().encode()).hexdigest(),
            )
            session.add(record)
            await session.commit()
            return record.id, record.context_hash, record.context_jsonb
    finally:
        await engine.dispose()


async def get_record(url, record_id):
    engine = create_engine(url)
    factory = create_session_factory(engine)
    try:
        async with factory() as session:
            record = await session.get(MatchContextRecord, record_id)
            return record.id, record.context_hash, record.context_jsonb
    finally:
        await engine.dispose()


def test_populated_m6_to_m7_cycle_preserves_context_hash_and_content(alembic_config):
    url = alembic_config.get_main_option("sqlalchemy.url")
    command.downgrade(alembic_config, "0011")
    old = asyncio.run(seed_m6(url))
    command.upgrade(alembic_config, "head")
    assert asyncio.run(get_record(url, old[0])) == old
    command.downgrade(alembic_config, "-1")
    assert asyncio.run(get_record(url, old[0])) == old
    command.upgrade(alembic_config, "head")
    assert asyncio.run(get_record(url, old[0])) == old
    command.check(alembic_config)
