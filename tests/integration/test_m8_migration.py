"""Populated accepted M7→M8 migration; no accepted migration files edited."""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command

from m7_fakes import make_context
from sports_intelligence.db.models import Fixture, League, MatchContextRecord, PredictionRun, Team
from sports_intelligence.db.session import create_engine, create_session_factory
from sports_intelligence.predictions.service import request_prediction
from sports_intelligence.workers.tasks.llm import run_prediction_job

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="test DB required"),
]


async def seed(url, settings):
    engine = create_engine(url)
    factory = create_session_factory(engine)
    try:
        async with factory() as s:
            data = make_context().model_dump()
            league = League(slug="m8-migration-" + uuid.uuid4().hex[:8], name="Synthetic M7")
            home, away = Team(name="Home"), Team(name="Away")
            s.add_all([league, home, away])
            await s.flush()
            fixture = Fixture(
                league_id=league.id,
                home_team_id=home.id,
                away_team_id=away.id,
                kickoff_at=datetime.now(UTC) + timedelta(hours=6),
                status="NS",
            )
            s.add(fixture)
            await s.flush()
            import hashlib

            from sports_intelligence.context.models import MatchContextV1

            data["fixture_id"] = data["fixture_identity"]["fixture_id"] = str(fixture.id)
            data["fixture_identity"].update(
                league_id=str(league.id), home_team_id=str(home.id), away_team_id=str(away.id)
            )
            ctx = MatchContextV1.model_validate(data)
            rec = MatchContextRecord(
                fixture_id=fixture.id,
                forecast_phase="MORNING",
                as_of=datetime.fromisoformat(data["as_of"]),
                schema_version="match_context_v1",
                context_jsonb=data,
                context_hash=hashlib.sha256(ctx.canonical_json().encode()).hexdigest(),
            )
            s.add(rec)
            await s.commit()
            run, _ = await request_prediction(s, record=rec, settings=settings)
            await s.commit()
        await run_prediction_job(
            str(run.job_id), str(run.id), settings=settings, session_factory=factory
        )
        async with factory() as s:
            r = await s.get(PredictionRun, run.id)
            return run.id, r.context_hash, r.output_jsonb, r.policy_jsonb
    finally:
        await engine.dispose()


async def read(url, run_id):
    engine = create_engine(url)
    try:
        factory = create_session_factory(engine)
        async with factory() as s:
            r = await s.get(PredictionRun, run_id)
            return r.id, r.context_hash, r.output_jsonb, r.policy_jsonb
    finally:
        await engine.dispose()


def test_populated_m7_to_m8_roundtrip_no_prediction_changes(alembic_config, service_settings):
    url = alembic_config.get_main_option("sqlalchemy.url")
    command.downgrade(alembic_config, "0012")
    old = asyncio.run(seed(url, service_settings))
    command.upgrade(alembic_config, "head")
    assert asyncio.run(read(url, old[0])) == old
    command.downgrade(alembic_config, "-1")
    assert asyncio.run(read(url, old[0])) == old
    command.upgrade(alembic_config, "head")
    assert asyncio.run(read(url, old[0])) == old
    command.check(alembic_config)
