from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sports_intelligence.api.dependencies import get_session
from sports_intelligence.db.models import (
    Experiment,
    ExperimentComparison,
    ImprovementProposal,
    ImprovementProposalEvent,
)
from sports_intelligence.experiments.analyst import (
    approve_experiment,
    human_transition,
    proposal_detail,
    request_analysis,
)
from sports_intelligence.experiments.contracts import (
    ApproveRequest,
    ExperimentDefinition,
    HumanAction,
    RecordedDecision,
    RunRequest,
)
from sports_intelligence.experiments.planner import plan_replay
from sports_intelligence.experiments.service import (
    create_experiment,
    enqueue_run,
    experiment_detail,
    request_run,
)
from sports_intelligence.workers.tasks.experiments import enqueue_analysis

router = APIRouter(prefix="/v1", tags=["experiments"])
Session = Annotated[AsyncSession, Depends(get_session)]


async def find_experiment(session: AsyncSession, identity: UUID) -> Experiment:
    row = await session.get(Experiment, identity)
    if row is None:
        raise HTTPException(404, "experiment_not_found")
    return row


async def find_proposal(session: AsyncSession, identity: UUID) -> ImprovementProposal:
    row = await session.get(ImprovementProposal, identity)
    if row is None:
        raise HTTPException(404, "proposal_not_found")
    return row


@router.get("/experiments")
async def list_experiments(
    session: Session,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
) -> list[dict[str, Any]]:
    rows = (
        await session.scalars(
            select(Experiment)
            .order_by(Experiment.created_at.desc(), Experiment.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [
        {
            "id": str(e.id),
            "name": e.name,
            "status": e.status,
            "hypothesis": e.definition_jsonb["hypothesis"],
        }
        for e in rows
    ]


@router.post("/experiments", status_code=201)
async def new_experiment(
    payload: ExperimentDefinition, request: Request, session: Session
) -> dict[str, Any]:
    try:
        experiment, created = await create_experiment(session, payload, request.app.state.settings)
        await session.commit()
        return {
            "id": str(experiment.id),
            "created": created,
            "definition_hash": experiment.definition_hash,
        }
    except (ValueError, OSError):
        raise HTTPException(422, "invalid_experiment_configuration") from None


@router.get("/experiments/{experiment_id}")
async def detail(experiment_id: UUID, session: Session) -> dict[str, Any]:
    return await experiment_detail(session, await find_experiment(session, experiment_id))


@router.post("/experiments/{experiment_id}/plan")
async def plan(experiment_id: UUID, session: Session) -> dict[str, Any]:
    experiment = await find_experiment(session, experiment_id)
    try:
        return await plan_replay(
            session, ExperimentDefinition.model_validate(experiment.definition_jsonb)
        )
    except ValueError:
        raise HTTPException(422, "invalid_replay_plan") from None


@router.post("/experiments/{experiment_id}/run", status_code=202)
async def execute(
    experiment_id: UUID, payload: RunRequest, request: Request, session: Session
) -> dict[str, Any]:
    experiment = await find_experiment(session, experiment_id)
    try:
        run, created = await request_run(session, experiment, payload, request.app.state.settings)
        await enqueue_run(session, run, created)
    except ValueError:
        raise HTTPException(422, "invalid_or_unauthorized_experiment_run") from None
    except RuntimeError:
        raise HTTPException(502, "experiment_enqueue_failed") from None
    return {
        "run_id": str(run.id),
        "job_id": str(run.job_id),
        "status": run.status,
        "already_queued": not created,
        "counts": run.counts_jsonb,
    }


@router.post("/experiments/runs/{run_id}/analyze", status_code=202)
async def analyze(
    run_id: UUID, payload: RunRequest, request: Request, session: Session
) -> dict[str, Any]:
    comparison = await session.scalar(
        select(ExperimentComparison).where(ExperimentComparison.run_id == run_id)
    )
    if comparison is None:
        raise HTTPException(409, "experiment_comparison_unavailable")
    try:
        job, created = await request_analysis(
            session, comparison, request.app.state.settings, live_opt_in=payload.live_opt_in
        )
        await enqueue_analysis(session, job, created)
    except ValueError:
        raise HTTPException(422, "invalid_or_unauthorized_analysis") from None
    except RuntimeError:
        raise HTTPException(502, "analysis_enqueue_failed") from None
    return {"job_id": str(job.id), "status": job.status, "already_queued": not created}


@router.get("/improvements")
async def improvements(
    session: Session,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
) -> list[dict[str, Any]]:
    rows = (
        await session.scalars(
            select(ImprovementProposal)
            .order_by(ImprovementProposal.created_at.desc(), ImprovementProposal.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [
        {
            "id": str(p.id),
            "title": p.content_jsonb["title"],
            "status": p.status,
            "sample_size": p.sample_size,
            "risk_level": p.content_jsonb["risk_level"],
        }
        for p in rows
    ]


@router.get("/improvements/{proposal_id}")
async def improvement(proposal_id: UUID, session: Session) -> dict[str, Any]:
    proposal = await find_proposal(session, proposal_id)
    value = proposal_detail(proposal)
    events = (
        await session.scalars(
            select(ImprovementProposalEvent)
            .where(ImprovementProposalEvent.proposal_id == proposal_id)
            .order_by(ImprovementProposalEvent.created_at, ImprovementProposalEvent.id)
        )
    ).all()
    value["human_actions"] = [
        {
            "from": e.from_status,
            "to": e.to_status,
            "actor": e.actor,
            "reason": e.reason,
            "at": e.created_at,
        }
        for e in events
    ]
    return value


@router.post("/improvements/{proposal_id}/approve-experiment")
async def approve(
    proposal_id: UUID, payload: ApproveRequest, request: Request, session: Session
) -> dict[str, Any]:
    proposal = await find_proposal(session, proposal_id)
    try:
        proposal = await approve_experiment(session, proposal, payload, request.app.state.settings)
        await session.commit()
    except (ValueError, OSError):
        raise HTTPException(409, "invalid_proposal_transition_or_experiment") from None
    return proposal_detail(proposal)


@router.post("/improvements/{proposal_id}/reject")
async def reject(proposal_id: UUID, payload: HumanAction, session: Session) -> dict[str, Any]:
    proposal = await find_proposal(session, proposal_id)
    try:
        proposal = await human_transition(session, proposal, "REJECTED", payload)
        await session.commit()
    except ValueError:
        raise HTTPException(409, "invalid_proposal_transition") from None
    return proposal_detail(proposal)


@router.post("/improvements/{proposal_id}/record-decision")
async def record_decision(
    proposal_id: UUID, payload: RecordedDecision, session: Session
) -> dict[str, Any]:
    proposal = await find_proposal(session, proposal_id)
    try:
        proposal = await human_transition(session, proposal, payload.status, payload)
        await session.commit()
    except ValueError:
        raise HTTPException(409, "invalid_human_audit_transition") from None
    return {**proposal_detail(proposal), "production_applied": False}
