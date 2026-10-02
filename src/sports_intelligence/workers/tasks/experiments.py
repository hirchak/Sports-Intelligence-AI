from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from sports_intelligence.core.config import Settings, get_settings
from sports_intelligence.db.models import ExperimentComparison, ExperimentRun, Job
from sports_intelligence.db.session import create_engine, create_session_factory
from sports_intelligence.experiments.analyst import generate_proposal, request_analysis
from sports_intelligence.experiments.comparison import compare_run
from sports_intelligence.experiments.runner import run_batch
from sports_intelligence.experiments.service import change_run_state
from sports_intelligence.workers.celery_app import celery_app
from sports_intelligence.workers.utils import record_job_attempt


@celery_app.task(name="experiment.replay_batch", queue="llm")  # type: ignore[untyped-decorator]
def replay_batch_task(run_id: str) -> dict[str, Any]:
    async def execute() -> dict[str, Any]:
        settings = get_settings()
        engine = create_engine(settings.database_url)
        factory = create_session_factory(engine)
        started = datetime.now(UTC)
        failure = None
        try:
            result = await run_batch(factory, UUID(run_id), settings)
            if result["status"] == "MORE":
                replay_batch_task.apply_async(args=[run_id], queue="llm")
            elif result["status"] == "EVALUATION_READY":
                compare_experiment_task.apply_async(args=[run_id], queue="evaluation")
            if result["status"] != "reused":
                async with factory() as session:
                    run = await session.get(ExperimentRun, UUID(run_id))
                    assert run is not None
                    job_id = run.job_id
                await record_job_attempt(
                    factory,
                    job_id=job_id,
                    started_at=started,
                    finished_at=datetime.now(UTC),
                    outcome="FAILED" if result["status"] == "NEEDS_INSPECTION" else "SUCCEEDED",
                )
            return result
        except Exception as exc:
            failure = exc
            async with factory() as session:
                run = await session.get(ExperimentRun, UUID(run_id))
                if run and run.status in ("QUEUED", "RUNNING"):
                    run.error_code = "replay_dispatch_or_execution_failure"
                    await change_run_state(session, run, "FAILED", "replay_worker")
                    await session.commit()
                    await record_job_attempt(
                        factory,
                        job_id=run.job_id,
                        started_at=started,
                        finished_at=datetime.now(UTC),
                        outcome="FAILED",
                        error=failure,
                    )
            raise RuntimeError("replay_task_failed") from None
        finally:
            await engine.dispose()

    return asyncio.run(execute())


@celery_app.task(name="experiment.compare", queue="evaluation")  # type: ignore[untyped-decorator]
def compare_experiment_task(run_id: str) -> dict[str, Any]:
    async def execute() -> dict[str, Any]:
        engine = create_engine(get_settings().database_url)
        factory = create_session_factory(engine)
        started = datetime.now(UTC)
        try:
            async with factory() as session:
                existing = await session.scalar(
                    select(ExperimentComparison).where(ExperimentComparison.run_id == UUID(run_id))
                )
                comparison = await compare_run(session, UUID(run_id))
                run = await session.get(ExperimentRun, UUID(run_id))
                assert run is not None
                await session.commit()
                if existing is None:
                    await record_job_attempt(
                        factory,
                        job_id=run.job_id,
                        started_at=started,
                        finished_at=datetime.now(UTC),
                        outcome="SUCCEEDED",
                    )
                return {"comparison_id": str(comparison.id)}
        except Exception as exc:
            async with factory() as session:
                run = await session.get(ExperimentRun, UUID(run_id))
                if run and run.status == "RUNNING":
                    run.error_code = "comparison_execution_failure"
                    await change_run_state(session, run, "FAILED", "comparison_worker")
                    await session.commit()
                    await record_job_attempt(
                        factory,
                        job_id=run.job_id,
                        started_at=started,
                        finished_at=datetime.now(UTC),
                        outcome="FAILED",
                        error=exc,
                    )
            raise RuntimeError("comparison_task_failed") from None
        finally:
            await engine.dispose()

    return asyncio.run(execute())


@celery_app.task(name="experiment.improvement_analysis", queue="llm")  # type: ignore[untyped-decorator]
def improvement_analysis_task(job_id: str) -> dict[str, Any]:
    async def execute() -> dict[str, Any]:
        settings = get_settings()
        engine = create_engine(settings.database_url)
        factory = create_session_factory(engine)
        started = datetime.now(UTC)
        try:
            result = await generate_proposal(factory, UUID(job_id), settings)
            if result["status"] != "reused":
                await record_job_attempt(
                    factory,
                    job_id=UUID(job_id),
                    started_at=started,
                    finished_at=datetime.now(UTC),
                    outcome=result["status"],
                    error=RuntimeError(result.get("reason", "analysis_failed"))
                    if result["status"] == "FAILED"
                    else None,
                )
            return result
        finally:
            await engine.dispose()

    result = asyncio.run(execute())
    if result["status"] == "FAILED":
        raise RuntimeError("improvement_analysis_failed")
    return result


async def enqueue_analysis(session: Any, job: Job, created: bool) -> None:
    await session.commit()
    if created:
        try:
            improvement_analysis_task.apply_async(args=[str(job.id)], queue="llm")
        except Exception:
            job.status = "FAILED"
            await session.commit()
            raise RuntimeError("analysis_enqueue_failed") from None


async def schedule_analysis(settings: Settings) -> int:
    if not settings.improvement_schedule_enabled:
        return 0
    engine = create_engine(settings.database_url)
    queued = 0
    try:
        async with create_session_factory(engine)() as session:
            comparisons = list(
                (
                    await session.scalars(
                        select(ExperimentComparison)
                        .order_by(ExperimentComparison.created_at.desc(), ExperimentComparison.id)
                        .limit(10)
                    )
                ).all()
            )
            for comparison in comparisons:
                try:
                    # Scheduled analysis deliberately has no live opt-in.
                    job, created = await request_analysis(session, comparison, settings)
                    await enqueue_analysis(session, job, created)
                    queued += created
                except ValueError:
                    continue
        return queued
    finally:
        await engine.dispose()


@celery_app.task(name="experiment.improvement_scan", queue="control")  # type: ignore[untyped-decorator]
def improvement_scan_task() -> int:
    return asyncio.run(schedule_analysis(get_settings()))
