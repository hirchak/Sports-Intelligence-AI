"""Keyless complete v1 path, reproducibility, Redis loss and optional native restore."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy import delete, func, select
from test_m9_experiments import test_real_m2_m8_pipeline_extends_to_m9_keyless_e2e

from sports_intelligence.context.models import MatchContextV1
from sports_intelligence.db.models import (
    Base,
    EvaluationRun,
    ExperimentComparison,
    FixtureResult,
    ImprovementProposal,
    MatchContextRecord,
    ModelConfig,
    PredictionRun,
    PromptVersion,
)
from sports_intelligence.db.session import create_engine, create_session_factory
from sports_intelligence.workers.tasks.llm import run_prediction_job

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("TEST_DATABASE_URL"), reason="local test services required"
    ),
]


@pytest.fixture
async def factory(service_settings):
    engine = create_engine(service_settings.database_url)
    sf = create_session_factory(engine)

    async def clean():
        async with sf() as session, session.begin():
            for table in reversed(Base.metadata.sorted_tables):
                if table.name.startswith(("experiment", "improvement")):
                    await session.execute(delete(table))
            # Delete dependent prediction truth before older collector fixtures remove odds.
            await session.execute(delete(EvaluationRun))
            await session.execute(delete(FixtureResult))
            await session.execute(delete(PredictionRun))

    await clean()
    try:
        yield sf
    finally:
        # Runtime acceptance explicitly retains only this disposable test population.
        if not os.environ.get("M10_KEEP_RUNTIME_DATA"):
            await clean()
        await engine.dispose()


# Scenario import, not a duplicate collected test.
scenario = test_real_m2_m8_pipeline_extends_to_m9_keyless_e2e
del test_real_m2_m8_pipeline_extends_to_m9_keyless_e2e


async def test_complete_v1_no_network_reproducible_redis_loss_and_restore(
    factory, service_settings, tmp_path, monkeypatch
):
    async def refuse_network(*args, **kwargs):
        raise AssertionError("external HTTP forbidden in keyless acceptance")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", refuse_network)
    await scenario(factory, service_settings, tmp_path, monkeypatch, include_research=True)
    async with factory() as session:
        run = await session.scalar(select(PredictionRun).where(PredictionRun.status == "SUCCEEDED"))
        context = await session.get(MatchContextRecord, run.match_context_id)
        parsed = MatchContextV1.model_validate(context.context_jsonb)
        assert hashlib.sha256(parsed.canonical_json().encode()).hexdigest() == context.context_hash
        assert run.context_hash == context.context_hash and run.as_of == context.as_of
        assert context.feature_snapshot_id and context.data_quality_report_id
        assert parsed.source_manifest.sources and parsed.market_snapshot.prices
        prompt = await session.get(PromptVersion, run.prompt_version_id)
        model = await session.get(ModelConfig, run.model_config_id)
        assert prompt.content_hash == hashlib.sha256(prompt.content.encode()).hexdigest()
        assert model.provider == "mock" and model.config_hash
        assert await session.scalar(select(func.count()).select_from(FixtureResult))
        assert await session.scalar(select(func.count()).select_from(ExperimentComparison))
        assert await session.scalar(select(func.count()).select_from(ImprovementProposal))
        original = (run.id, run.output_jsonb, context.context_hash, context.context_jsonb)
    redis = Redis.from_url(service_settings.redis_url)
    try:
        await (
            redis.flushdb()
        )  # Isolated Redis15 only; canonical truth must survive total cache loss.
    finally:
        await redis.aclose()
    await run_prediction_job(
        str(run.job_id), str(run.id), settings=service_settings, session_factory=factory
    )
    async with factory() as session:
        after_run = await session.get(PredictionRun, run.id)
        after_context = await session.get(MatchContextRecord, context.id)
        assert original == (
            after_run.id,
            after_run.output_jsonb,
            after_context.context_hash,
            after_context.context_jsonb,
        )
        assert await session.scalar(select(func.count()).select_from(PredictionRun)) == 1
    report = {
        "mock_e2e": "PASS",
        "external_http_calls": 0,
        "prediction_run_id": str(run.id),
        "match_context_id": str(context.id),
        "context_hash": context.context_hash,
        "redis_loss_completed_prediction": "PASS",
    }
    if os.environ.get("M10_BACKUP_PROJECT"):
        result = subprocess.run(
            [
                sys.executable,
                "scripts/backup_restore.py",
                "--project",
                os.environ["M10_BACKUP_PROJECT"],
                "--database",
                os.environ.get("M10_BACKUP_DATABASE", "sports_intel_test"),
                "--env-file",
                os.environ.get("APP_ENV_FILE", ".env"),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        report["backup_restore"] = json.loads(result.stdout)
    if os.environ.get("M10_REPORT_PATH"):
        Path(os.environ["M10_REPORT_PATH"]).write_text(json.dumps(report, indent=2, sort_keys=True))


async def test_accelerated_three_day_discovery_planning_deduplicates(service_settings, monkeypatch):
    from datetime import UTC, datetime, timedelta

    from sports_intelligence.db.models import Job
    from sports_intelligence.db.session import create_engine, create_session_factory
    from sports_intelligence.workers.tasks import scheduling

    settings = service_settings.model_copy(
        update={"leagues_config_path": "config/leagues.mock.yaml"}
    )
    monkeypatch.setattr(scheduling, "get_settings", lambda: settings)
    calls = []

    async def enqueue(*args, **kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(scheduling, "_enqueue", enqueue)
    start = datetime(2031, 3, 25, 8, tzinfo=UTC)
    unique = set()
    engine = create_engine(settings.database_url)
    sf = create_session_factory(engine)
    async with sf() as session, session.begin():
        await session.execute(
            delete(Job).where(Job.idempotency_key.like("discover:scheduled:%:mock:2031-03-%"))
        )
    await engine.dispose()
    for offset in range(3):
        at = start + timedelta(days=offset)

        class Clock(datetime):
            @classmethod
            def now(cls, tz=None, current=at):
                return current

        monkeypatch.setattr(scheduling, "datetime", Clock)
        for slot in ("morning", "refresh"):
            first = await scheduling._run_schedule(slot)
            duplicate = await scheduling._run_schedule(slot)
            assert first["job_id"] == duplicate["job_id"]
            assert not duplicate["created"]
            unique.add(first["job_id"])
    assert len(unique) == len(calls) == 6
