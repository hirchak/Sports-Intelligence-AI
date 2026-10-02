from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sports_intelligence.core.config import Settings
from sports_intelligence.db.models import (
    ExperimentComparison,
    ExperimentRun,
    ExternalApiRequest,
    ImprovementAnalysis,
    ImprovementProposal,
    ImprovementProposalEvent,
    Job,
)
from sports_intelligence.experiments.contracts import (
    AnalystOutput,
    ApproveRequest,
    HumanAction,
    transition,
)
from sports_intelligence.experiments.service import create_experiment
from sports_intelligence.pipelines.discover_fixtures import create_or_get_job
from sports_intelligence.predictions.config import load_llm_config
from sports_intelligence.predictions.identity import content_hash, fingerprint
from sports_intelligence.predictions.router import ModelRouter
from sports_intelligence.providers.llm.factory import build_llm_provider


def analysis_packet(comparison: ExperimentComparison, run: ExperimentRun) -> dict[str, Any]:
    summary = comparison.summary_jsonb
    groups = {
        name: {"metrics": values["metrics"], "calibration": values["calibration"][:20]}
        for name, values in summary["groups"].items()
    }
    return {
        "experiment_id": str(run.experiment_id),
        "run_id": str(run.id),
        "comparison_id": str(comparison.id),
        "counts": summary["counts"],
        "sample_size": summary["counts"]["paired"],
        "interpretation": summary["interpretation"],
        "groups": groups,
        "paired_deltas": summary["paired_deltas"],
        "limitations": summary["limitations"],
        "evaluation": summary["evaluation"],
    }


async def request_analysis(
    session: AsyncSession,
    comparison: ExperimentComparison,
    settings: Settings,
    *,
    live_opt_in: bool = False,
) -> tuple[Job, bool]:
    from pathlib import Path

    config = load_llm_config(settings)
    decision = ModelRouter(config).select("improvement_analysis")
    if decision.selected.provider != "mock" and (
        not live_opt_in or not settings.improvement_live_enabled or settings.app_env != "live_local"
    ):
        raise ValueError("live_analyst_not_authorized")
    prompt = Path(settings.improvement_prompt_path).read_text()
    run = await session.get(ExperimentRun, comparison.run_id)
    assert run is not None
    packet = analysis_packet(comparison, run)
    if len(json.dumps(packet).encode()) > 50000:
        raise ValueError("analyst_packet_budget_exceeded")
    frozen = {
        "packet": packet,
        "model": decision.selected.model_dump(mode="json"),
        "route_hash": decision.fingerprint,
        "prompt": prompt,
        "prompt_hash": content_hash(prompt),
        "prompt_version": Path(settings.improvement_prompt_path).stem,
        "live_opt_in": live_opt_in,
    }
    digest = fingerprint(frozen)
    job, created = await create_or_get_job(
        session, "improvement_analysis", "m9:analyst:" + digest, datetime.now(UTC)
    )
    if created:
        # Separate immutable bounded analyst request; Job carries only identity/state.
        session.add(ImprovementAnalysis(job_id=job.id, frozen_jsonb=frozen))
    return job, created


async def generate_proposal(
    factory: async_sessionmaker[AsyncSession], job_id: UUID, settings: Settings
) -> dict[str, Any]:
    from sports_intelligence.predictions.config import ModelSpec

    started = datetime.now(UTC)
    async with factory() as session:
        claimed = await session.scalar(
            update(Job)
            .where(
                Job.id == job_id,
                Job.job_type == "improvement_analysis",
                Job.status == "PENDING",
            )
            .values(status="RUNNING")
            .returning(Job.id)
        )
        if claimed is None:
            job = await session.get(Job, job_id)
            if job is None:
                raise ValueError("analysis_job_not_found")
            prior = await session.scalar(
                select(ImprovementProposal).where(
                    ImprovementProposal.evidence_hash
                    == job.idempotency_key.removeprefix("m9:analyst:")
                )
            )
            return {"status": "reused", "proposal_id": str(prior.id) if prior else None}
        await session.commit()
    provider = None
    result = None
    config = None
    error_code = None
    called = False
    try:
        async with factory() as session, session.begin():
            job = await session.get(Job, job_id)
            analysis = await session.get(ImprovementAnalysis, job_id)
            assert job is not None and analysis is not None
            frozen = analysis.frozen_jsonb
            digest = fingerprint(frozen)
            if (
                job.idempotency_key != "m9:analyst:" + digest
                or content_hash(frozen["prompt"]) != frozen["prompt_hash"]
            ):
                raise ValueError("analyst_frozen_identity_mismatch")
            config = ModelSpec.model_validate(frozen["model"])
            if config.provider != "mock" and (
                not frozen["live_opt_in"]
                or not settings.improvement_live_enabled
                or settings.app_env != "live_local"
            ):
                raise ValueError("live_analyst_not_authorized")
            await session.execute(text("SELECT pg_advisory_xact_lock(707001)"))
            day = started.replace(hour=0, minute=0, second=0, microsecond=0)
            count = await session.scalar(
                select(func.count())
                .select_from(ImprovementAnalysis)
                .where(ImprovementAnalysis.started_at >= day)
            )
            if (count or 0) >= settings.improvement_max_calls_per_day:
                raise ValueError("analyst_daily_budget_exhausted")
            analysis.started_at = started
        provider = build_llm_provider(settings, config, timeout_seconds=30)
        called = True
        result = await asyncio.wait_for(
            provider.generate_structured(
                task_type="improvement_analysis",
                config=config,
                system_prompt=frozen["prompt"],
                payload={"analysis_packet": frozen["packet"]},
                output_schema=AnalystOutput,
                request_id=str(job_id),
            ),
            timeout=30,
        )
        if result.provider != config.provider or result.error_code or result.parsed_output is None:
            raise ValueError("invalid_analyst_provider_output")
        output = AnalystOutput.model_validate(result.parsed_output)
        async with factory() as session, session.begin():
            proposal = ImprovementProposal(
                evidence_hash=digest,
                comparison_id=UUID(frozen["packet"]["comparison_id"]),
                content_jsonb=output.model_dump(mode="json"),
                evidence_jsonb=frozen["packet"],
                sample_size=frozen["packet"]["sample_size"],
                status="PROPOSED",
                analyst_jsonb={
                    "requested_model": frozen["model"],
                    "actual_provider": result.provider,
                    "actual_model": result.model,
                    "actual_config": {**frozen["model"], "model": result.model},
                    "prompt_hash": frozen["prompt_hash"],
                    "prompt_version": frozen["prompt_version"],
                    "route_hash": frozen["route_hash"],
                    "result": {k: v for k, v in asdict(result).items() if k != "parsed_output"},
                },
            )
            session.add(proposal)
            await session.flush()
            job = await session.get(Job, job_id)
            assert job is not None
            job.status = "SUCCEEDED"
            return {"status": "SUCCEEDED", "proposal_id": str(proposal.id)}
    except Exception as exc:
        error_code = type(exc).__name__
        async with factory() as session, session.begin():
            job = await session.get(Job, job_id)
            assert job is not None
            job.status = "FAILED"
        return {"status": "FAILED", "reason": error_code}
    finally:
        if provider:
            await provider.aclose()
        async with factory() as session, session.begin():
            analysis = await session.get(ImprovementAnalysis, job_id)
            if analysis:
                analysis.finished_at = datetime.now(UTC)
                analysis.error_code = error_code
                if result:
                    analysis.result_jsonb = {
                        k: v for k, v in asdict(result).items() if k != "parsed_output"
                    }
            if called and config and config.provider != "mock":
                session.add(
                    ExternalApiRequest(
                        provider=config.provider,
                        endpoint_category="improvement_analysis",
                        started_at=started,
                        duration_ms=result.latency_ms if result else None,
                        status_code=result.status_code if result else None,
                        cache_hit=False,
                        priority="P3",
                        degradation_mode="NORMAL",
                        estimated_cost=1,
                        actual_cost=1,
                        error_class=error_code,
                    )
                )


async def human_transition(
    session: AsyncSession, proposal: ImprovementProposal, target: str, action: HumanAction
) -> ImprovementProposal:
    locked = await session.scalar(
        select(ImprovementProposal).where(ImprovementProposal.id == proposal.id).with_for_update()
    )
    assert locked is not None
    if locked.status == target:
        return locked  # Duplicate same action is idempotent, no duplicate events.
    transition(locked.status, target, proposal=True)
    session.add(
        ImprovementProposalEvent(
            proposal_id=locked.id,
            from_status=locked.status,
            to_status=target,
            actor=action.actor,
            reason=action.reason,
        )
    )
    locked.status = target
    return locked


async def approve_experiment(
    session: AsyncSession, proposal: ImprovementProposal, action: ApproveRequest, settings: Settings
) -> ImprovementProposal:
    locked = await session.scalar(
        select(ImprovementProposal).where(ImprovementProposal.id == proposal.id).with_for_update()
    )
    assert locked is not None
    if locked.status == "APPROVED_FOR_EXPERIMENT":
        return locked
    transition(locked.status, "APPROVED_FOR_EXPERIMENT", proposal=True)
    definition = action.experiment
    if definition is None:
        from sports_intelligence.db.models import Experiment
        from sports_intelligence.experiments.contracts import ExperimentDefinition

        parent = await session.get(Experiment, UUID(locked.evidence_jsonb["experiment_id"]))
        assert parent is not None
        data = dict(parent.definition_jsonb)
        data["name"] = "Proposal experiment: " + locked.content_jsonb["title"][:170]
        data["hypothesis"] = locked.content_jsonb["hypothesis"]
        data["created_by"] = action.actor
        data["treatment"] = {**data["treatment"], "prompt": "candidate"}
        definition = ExperimentDefinition.model_validate(data)
    experiment, _ = await create_experiment(session, definition, settings)
    locked.experiment_id = experiment.id
    return await human_transition(session, locked, "APPROVED_FOR_EXPERIMENT", action)


def proposal_detail(proposal: ImprovementProposal) -> dict[str, Any]:
    return {
        "id": str(proposal.id),
        **proposal.content_jsonb,
        "status": proposal.status,
        "sample_size": proposal.sample_size,
        "evidence_summary": proposal.evidence_jsonb,
        "evidence_references": {
            k: proposal.evidence_jsonb[k] for k in ("experiment_id", "run_id", "comparison_id")
        },
        "analyst": proposal.analyst_jsonb,
        "created_at": proposal.created_at,
        "experiment_id": str(proposal.experiment_id) if proposal.experiment_id else None,
    }
