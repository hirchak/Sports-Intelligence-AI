from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from sports_intelligence.core.config import Settings
from sports_intelligence.db.models import (
    Experiment,
    ExperimentArm,
    ExperimentCase,
    ExperimentPrediction,
    ExperimentRun,
    Job,
)
from sports_intelligence.experiments.contracts import (
    ExperimentDefinition,
    FrozenArm,
    RunRequest,
    transition,
)
from sports_intelligence.experiments.planner import plan_replay
from sports_intelligence.pipelines.discover_fixtures import create_or_get_job
from sports_intelligence.predictions.config import load_llm_config
from sports_intelligence.predictions.identity import fingerprint, load_prompt
from sports_intelligence.predictions.router import ModelRouter


async def create_experiment(
    session: AsyncSession,
    definition: ExperimentDefinition,
    settings: Settings,
) -> tuple[Experiment, bool]:
    config = load_llm_config(settings)
    frozen = {}
    for name in ("control", "treatment"):
        request = getattr(definition, name)
        if request.route not in {
            "prediction_primary",
            "prediction_challenger",
            *config.manual_override_routes,
        }:
            raise ValueError("experiment_route_not_allowed")
        decision = ModelRouter(config).select(request.route)
        path = (
            settings.prediction_prompt_path
            if request.prompt == "default"
            else settings.experiment_candidate_prompt_path
        )
        prompt = load_prompt(path)
        arm = FrozenArm(
            request=request,
            models=(decision.selected, *decision.fallbacks),
            fallback_errors=config.routes[request.route].fallback_errors,
            prompt_name=prompt.name,
            prompt_version=prompt.version,
            prompt_hash=prompt.hash,
            prompt_content=prompt.content,
            prompt_source=prompt.source_identity,
            policy=config.policy,
            route_hash=decision.fingerprint,
        )
        frozen[name] = arm
    data = definition.model_dump(mode="json")
    digest = fingerprint({"definition": data, "arms": {n: a.hash for n, a in frozen.items()}})
    inserted = await session.scalar(
        pg_insert(Experiment)
        .values(
            definition_hash=digest,
            definition_jsonb=data,
            name=definition.name,
            created_by=definition.created_by,
            status="READY",
        )
        .on_conflict_do_nothing(index_elements=["definition_hash"])
        .returning(Experiment.id)
    )
    experiment = await session.scalar(
        select(Experiment).where(Experiment.definition_hash == digest)
    )
    assert experiment is not None
    if inserted:
        session.add_all(
            [
                ExperimentArm(
                    experiment_id=experiment.id,
                    name=n,
                    identity_hash=a.hash,
                    frozen_jsonb=a.model_dump(mode="json"),
                )
                for n, a in frozen.items()
            ]
        )
        await session.flush()
    return experiment, inserted is not None


async def request_run(
    session: AsyncSession,
    experiment: Experiment,
    request: RunRequest,
    settings: Settings,
) -> tuple[ExperimentRun, bool]:
    # Serializes queue requests, planning and identity creation for this immutable definition.
    locked = await session.scalar(
        select(Experiment).where(Experiment.id == experiment.id).with_for_update()
    )
    assert locked is not None
    experiment = locked
    prior = await session.scalar(
        select(ExperimentRun)
        .where(
            ExperimentRun.experiment_id == experiment.id,
            ExperimentRun.rerun_key == (str(request.rerun_key) if request.rerun_key else None),
        )
        .order_by(ExperimentRun.created_at)
        .limit(1)
    )
    if prior:
        return prior, False
    arms = list(
        (
            await session.scalars(
                select(ExperimentArm).where(ExperimentArm.experiment_id == experiment.id)
            )
        ).all()
    )
    live = any(
        m["provider"] != "mock"
        for a in arms
        if a.frozen_jsonb["request"]["source"] == "replay"
        for m in a.frozen_jsonb["models"]
    )
    if live and (
        not request.live_opt_in
        or not settings.experiment_live_enabled
        or settings.app_env != "live_local"
    ):
        raise ValueError("live_experiment_not_authorized")
    definition = ExperimentDefinition.model_validate(experiment.definition_jsonb)
    plan = await plan_replay(session, definition)
    mh = fingerprint(plan["manifest"])
    identity = fingerprint(
        {
            "definition": experiment.definition_hash,
            "manifest": mh,
            "rerun": str(request.rerun_key) if request.rerun_key else None,
        }
    )
    job, _ = await create_or_get_job(session, "experiment", "m9:run:" + identity, datetime.now(UTC))
    run = ExperimentRun(
        experiment_id=experiment.id,
        job_id=job.id,
        identity_hash=identity,
        manifest_hash=mh,
        manifest_jsonb=plan["manifest"],
        counts_jsonb=plan["counts"],
        rerun_key=str(request.rerun_key) if request.rerun_key else None,
        live_opt_in=request.live_opt_in,
        source_cutoff=datetime.fromisoformat(plan["source_cutoff"]),
        status="QUEUED",
        audit_jsonb=[{"from": "READY", "to": "QUEUED", "actor": definition.created_by}],
    )
    session.add(run)
    await session.flush()
    for i, item in enumerate(plan["manifest"]):
        case = ExperimentCase(
            run_id=run.id,
            ordinal=i,
            fixture_id=UUID(item["fixture_id"]) if item["fixture_exists"] else None,
            control_context_id=UUID(item["control"]["context_id"]) if item["control"] else None,
            treatment_context_id=UUID(item["treatment"]["context_id"])
            if item["treatment"]
            else None,
            result_id=UUID(item["result_id"]) if item["result_id"] else None,
            status=item["status"],
            reason=item["reason"],
            lineage_jsonb=item,
        )
        session.add(case)
        await session.flush()
        if case.status == "ELIGIBLE":
            session.add_all(
                [ExperimentPrediction(case_id=case.id, arm_id=a.id, status="QUEUED") for a in arms]
            )
    from sports_intelligence.db.models import ImprovementProposal
    from sports_intelligence.experiments.analyst import human_transition
    from sports_intelligence.experiments.contracts import HumanAction

    proposals = (
        await session.scalars(
            select(ImprovementProposal).where(
                ImprovementProposal.experiment_id == experiment.id,
                ImprovementProposal.status == "APPROVED_FOR_EXPERIMENT",
            )
        )
    ).all()
    for proposal in proposals:
        await human_transition(
            session,
            proposal,
            "EXPERIMENT_RUNNING",
            HumanAction(actor=definition.created_by, reason="Explicit experiment queue request"),
        )
    experiment.status = "QUEUED"
    await session.flush()
    return run, True


async def enqueue_run(session: AsyncSession, run: ExperimentRun, created: bool) -> None:
    await session.commit()
    if not created:
        return
    from sports_intelligence.workers.tasks.experiments import replay_batch_task

    try:
        replay_batch_task.apply_async(args=[str(run.id)], queue="llm")
    except Exception:
        run.status, run.error_code = "FAILED", "enqueue_failed"
        job = await session.get(Job, run.job_id)
        if job:
            job.status = "FAILED"
        await session.commit()
        raise RuntimeError("experiment_enqueue_failed") from None


async def change_run_state(
    session: AsyncSession, run: ExperimentRun, target: str, actor: str
) -> None:
    transition(run.status, target)
    run.audit_jsonb = [
        *run.audit_jsonb,
        {"from": run.status, "to": target, "actor": actor, "at": datetime.now(UTC).isoformat()},
    ]
    run.status = target
    experiment = await session.get(Experiment, run.experiment_id)
    assert experiment is not None
    experiment.status = target
    job = await session.get(Job, run.job_id)
    if job:
        job.status = (
            "SUCCEEDED"
            if target in ("SUCCEEDED", "INSUFFICIENT_DATA")
            else "PENDING"
            if target == "QUEUED"
            else "FAILED"
            if target == "CANCELLED"
            else target
        )
    if target == "RUNNING":
        run.started_at = datetime.now(UTC)
    if target in ("SUCCEEDED", "INSUFFICIENT_DATA", "FAILED", "CANCELLED"):
        run.completed_at = datetime.now(UTC)


async def experiment_detail(session: AsyncSession, experiment: Experiment) -> dict[str, Any]:
    from sports_intelligence.db.models import ExperimentComparison

    runs = list(
        (
            await session.scalars(
                select(ExperimentRun)
                .where(ExperimentRun.experiment_id == experiment.id)
                .order_by(ExperimentRun.created_at.desc())
                .limit(20)
            )
        ).all()
    )
    comparisons = {
        c.run_id: c
        for c in (
            await session.scalars(
                select(ExperimentComparison).where(
                    ExperimentComparison.run_id.in_([r.id for r in runs])
                )
            )
        ).all()
    }
    return {
        "id": str(experiment.id),
        "name": experiment.name,
        "status": experiment.status,
        "definition": experiment.definition_jsonb,
        "definition_hash": experiment.definition_hash,
        "created_at": experiment.created_at,
        "runs": [
            {
                "id": str(r.id),
                "status": r.status,
                "counts": r.counts_jsonb,
                "manifest_hash": r.manifest_hash,
                "identity_hash": r.identity_hash,
                "error_code": r.error_code,
                "audit": r.audit_jsonb,
                "comparison": comparisons[r.id].summary_jsonb if r.id in comparisons else None,
            }
            for r in runs
        ],
    }
