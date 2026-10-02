"""Populated accepted M8→M9 integrity; dedicated test database only."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime

import pytest
from alembic import command
from sqlalchemy import select
from test_m8_migration import seed

from sports_intelligence.db.models import (
    EvaluationMetric,
    EvaluationRun,
    Fixture,
    MatchContextRecord,
    PredictionRun,
)
from sports_intelligence.db.session import create_engine, create_session_factory
from sports_intelligence.evaluation.config import EvaluationConfig, EvaluationFilters
from sports_intelligence.evaluation.results import persist_result, settle_result
from sports_intelligence.evaluation.service import request_evaluation
from sports_intelligence.evaluation.settlement import ResultObservation, ResultStatus
from sports_intelligence.workers.tasks.evaluation import run_evaluation_job

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="test DB required"),
]


async def populated_m8(url, settings):
    original = await seed(url, settings)
    engine = create_engine(url)
    factory = create_session_factory(engine)
    try:
        async with factory() as s:
            run = await s.get(PredictionRun, original[0])
            rec = await s.get(MatchContextRecord, run.match_context_id)
            fixture = await s.get(Fixture, run.fixture_id)
            fixture.kickoff_at = datetime.fromisoformat(
                rec.context_jsonb["fixture_identity"]["kickoff_at"]
            )
            result, _ = await persist_result(
                s,
                fixture.id,
                "mock",
                ResultObservation(
                    provider_fixture_id=43,
                    provider_status="FT",
                    status=ResultStatus.FINAL,
                    regulation_home=1,
                    regulation_away=0,
                    observed_at=datetime.now(UTC),
                ),
            )
            assert await settle_result(s, result.id) == 12
            await s.commit()
            evaluation, _ = await request_evaluation(
                s,
                config=EvaluationConfig(),
                filters=EvaluationFilters(league=fixture.league_id),
                cutoff=datetime.now(UTC),
            )
            await s.commit()
        await run_evaluation_job(
            str(evaluation.job_id), str(evaluation.id), settings=settings, factory=factory
        )
        return original[0], evaluation.id
    finally:
        await engine.dispose()


async def snapshot(url, ids):
    engine = create_engine(url)
    try:
        async with create_session_factory(engine)() as s:
            run = await s.get(PredictionRun, ids[0])
            evaluation = await s.get(EvaluationRun, ids[1])
            metrics = (
                await s.scalars(
                    select(EvaluationMetric)
                    .where(EvaluationMetric.evaluation_run_id == ids[1])
                    .order_by(EvaluationMetric.id)
                )
            ).all()
            return (
                run.context_hash,
                run.output_jsonb,
                run.policy_jsonb,
                evaluation.source_manifest_jsonb,
                [(str(m.id), m.metric_name, m.metric_value, m.sample_size) for m in metrics],
            )
    finally:
        await engine.dispose()


def test_populated_accepted_m8_to_m9_roundtrip(alembic_config, service_settings):
    url = alembic_config.get_main_option("sqlalchemy.url")
    command.downgrade(alembic_config, "0013")
    ids = asyncio.run(populated_m8(url, service_settings))
    before = asyncio.run(snapshot(url, ids))
    assert before[-1]
    command.upgrade(alembic_config, "head")
    assert asyncio.run(snapshot(url, ids)) == before
    command.downgrade(alembic_config, "-1")
    assert asyncio.run(snapshot(url, ids)) == before
    command.upgrade(alembic_config, "head")
    assert asyncio.run(snapshot(url, ids)) == before
    command.check(alembic_config)
