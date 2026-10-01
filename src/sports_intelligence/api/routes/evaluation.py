from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from sports_intelligence.api.dependencies import get_session
from sports_intelligence.db.models import (
    CalibrationBucket,
    EvaluationMetric,
    EvaluationRun,
    Fixture,
    FixtureResult,
    MarketPrediction,
    PredictionRun,
    PredictionSettlement,
)
from sports_intelligence.evaluation.config import EvaluationFilters
from sports_intelligence.evaluation.results import latest_results_query
from sports_intelligence.evaluation.service import (
    FACETS,
    configured_metrics,
    enqueue_evaluation,
    request_evaluation,
)
from sports_intelligence.predictions.contracts import Role, Variant
from sports_intelligence.schemas.evaluation import EvaluateRequest, ResultView

router = APIRouter(prefix="/v1", tags=["results-evaluation"])
SessionDependency = Annotated[AsyncSession, Depends(get_session)]


@router.get("/results", response_model=list[ResultView])
async def results(
    session: SessionDependency,
    start: datetime | None = None,
    end: datetime | None = None,
    league: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
) -> list[FixtureResult]:
    try:
        EvaluationFilters(start=start, end=end)
    except ValueError:
        raise HTTPException(422, "invalid_result_period") from None
    query = (
        select(FixtureResult)
        .join(Fixture, Fixture.id == FixtureResult.fixture_id)
        .where(FixtureResult.id.in_(latest_results_query()))
    )
    if start:
        query = query.where(Fixture.kickoff_at >= start)
    if end:
        query = query.where(Fixture.kickoff_at < end)
    if league:
        query = query.where(Fixture.league_id == league)
    return list(
        (
            await session.scalars(
                query.order_by(FixtureResult.observed_at.desc(), FixtureResult.id)
                .limit(limit)
                .offset(offset)
            )
        ).all()
    )


@router.get("/results/{fixture_id}")
async def result_detail(fixture_id: UUID, session: SessionDependency) -> dict[str, Any]:
    records = list(
        (
            await session.scalars(
                select(FixtureResult)
                .where(FixtureResult.fixture_id == fixture_id)
                .order_by(FixtureResult.version.desc())
                .limit(20)
            )
        ).all()
    )
    if not records:
        raise HTTPException(404, "result_not_available")
    return {
        "latest": ResultView.model_validate(records[0]),
        "history": [ResultView.model_validate(r) for r in records],
        "history_limit": 20,
        "settlement_version": "regulation_v1",
    }


@router.get("/results/{fixture_id}/settlements")
async def settled_predictions(
    fixture_id: UUID,
    session: SessionDependency,
    run_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
) -> list[dict[str, Any]]:
    query = (
        select(PredictionSettlement, MarketPrediction, PredictionRun)
        .join(MarketPrediction, MarketPrediction.id == PredictionSettlement.market_prediction_id)
        .join(PredictionRun, PredictionRun.id == MarketPrediction.prediction_run_id)
        .where(
            PredictionRun.fixture_id == fixture_id,
            PredictionSettlement.fixture_result_id.in_(latest_results_query()),
        )
    )
    if run_id:
        query = query.where(PredictionRun.id == run_id)
    rows = (
        await session.execute(
            query.order_by(PredictionRun.id, MarketPrediction.selection).limit(limit).offset(offset)
        )
    ).all()
    return [
        {
            "run_id": run.id,
            "market_prediction_id": p.id,
            "selection": p.selection,
            "probability": p.model_probability,
            "outcome": s.outcome,
            "result_id": s.fixture_result_id,
            "settlement_version": s.settlement_version,
            "role": run.role,
            "variant": run.variant,
        }
        for s, p, run in rows
    ]


@router.post("/jobs/evaluate", status_code=202)
async def evaluate(
    payload: EvaluateRequest, request: Request, session: SessionDependency
) -> dict[str, Any]:
    cutoff = payload.cutoff or datetime.now(UTC)
    fj = payload.filters.model_dump(exclude_none=True)
    if "start" not in fj and payload.period != "all":
        fj["start"] = cutoff - timedelta(days=int(payload.period[:-1]))
    fj.setdefault("end", cutoff)
    try:
        run, created = await request_evaluation(
            session,
            config=payload.config or configured_metrics(request.app.state.settings),
            filters=EvaluationFilters.model_validate(fj),
            cutoff=cutoff,
        )
    except ValueError:
        raise HTTPException(422, "invalid_evaluation_config_period_or_cutoff") from None
    try:
        await enqueue_evaluation(session, run, created)
    except RuntimeError:
        raise HTTPException(502, "evaluation_enqueue_failed") from None
    return {
        "evaluation_id": run.id,
        "job_id": run.job_id,
        "status": run.status,
        "already_queued": not created,
    }


@router.get("/evaluations/summary")
async def summary(
    session: SessionDependency,
    period: Literal["7d", "30d", "all"] = "30d",
    evaluation_id: UUID | None = None,
    group_by: Literal[
        "league",
        "market",
        "model",
        "odds_bucket",
        "selection",
        "prompt",
        "phase",
        "data_quality",
        "confidence",
        "model_config_id",
        "provider",
        "baseline_version",
    ]
    | None = None,
    role: Role = Role.PRIMARY,
    variant: Variant = Variant.WITH_ODDS,
    baseline: Literal["llm", "market", "statistical"] = "llm",
    league: UUID | None = None,
    market: str | None = None,
    model: str | None = None,
    model_config_id: UUID | None = None,
    provider: str | None = None,
    selection: str | None = None,
    confidence: str | None = None,
    prompt: str | None = None,
    phase: str | None = None,
    data_quality: str | None = None,
    odds_bucket: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0, le=100000)] = 0,
) -> dict[str, Any]:
    requested = {k: str(v) for k, v in locals().copy().items() if k in FACETS and v is not None}
    try:
        filters = EvaluationFilters(
            start=start, end=end, role=role, variant=variant, baseline=baseline, **requested
        )
    except ValueError:
        raise HTTPException(422, "invalid_evaluation_filters") from None
    q = select(EvaluationRun).where(EvaluationRun.status == "SUCCEEDED")
    if evaluation_id:
        q = q.where(EvaluationRun.id == evaluation_id)
    runs = list(
        (
            await session.scalars(
                q.order_by(EvaluationRun.source_cutoff.desc(), EvaluationRun.id).limit(100)
            )
        ).all()
    )
    chosen = None
    for run in runs:
        stored = EvaluationFilters.model_validate(run.filters_jsonb)
        if start or end:
            if stored.start != start or stored.end != end:
                continue
        elif (
            (stored.start is None) != (period == "all")
            or stored.start
            and stored.end
            and stored.end - stored.start != timedelta(days=int(period[:-1]))
        ):
            continue
        if any(
            getattr(stored, name) is not None and getattr(stored, name) != getattr(filters, name)
            for name in (*FACETS, "role", "variant", "baseline")
        ):
            continue
        chosen = run
        break
    if chosen is None:
        return {"status": "not_available", "groups": [], "sample_size": 0}
    effective = {"role": role.value, "variant": variant.value, "baseline": baseline, **requested}
    mq = select(EvaluationMetric).where(EvaluationMetric.evaluation_run_id == chosen.id)
    for name, value in effective.items():
        if chosen.filters_jsonb.get(name) != value:
            mq = mq.where(EvaluationMetric.dimensions_jsonb[name].as_string() == value)
    wanted_names = {"role", "variant", "baseline", *requested.keys()}
    wanted_names -= {
        name for name in requested if chosen.filters_jsonb.get(name) == requested[name]
    }
    if group_by:
        wanted_names.add(group_by)
        mq = mq.where(EvaluationMetric.dimensions_jsonb[group_by].as_string().is_not(None))
    remainder: Any = EvaluationMetric.dimensions_jsonb
    for name in sorted(wanted_names):
        remainder = remainder.op("-")(literal(name))
    mq = mq.where(remainder == {})
    # Select distinct dimension keys before reading metric/bucket rows; bounded API response.
    keys = list(
        (
            await session.scalars(
                mq.with_only_columns(EvaluationMetric.dimension_key)
                .distinct()
                .order_by(EvaluationMetric.dimension_key)
                .limit(limit + 1)
                .offset(offset)
            )
        ).all()
    )
    metrics = list(
        (
            await session.scalars(
                select(EvaluationMetric).where(
                    EvaluationMetric.evaluation_run_id == chosen.id,
                    EvaluationMetric.dimension_key.in_(keys[:limit]),
                )
            )
        ).all()
    )
    groups: dict[str, dict[str, Any]] = {}
    for m in metrics:
        dims = m.dimensions_jsonb
        if set(dims) != wanted_names:
            continue
        group = groups.setdefault(
            m.dimension_key,
            {"dimensions": dims, "metrics": {}, "calibration": [], "sample_size": 0},
        )
        group["metrics"][m.metric_name] = {"value": m.metric_value, "sample_size": m.sample_size}
        if m.metric_name == "binary_brier":
            group["sample_size"] = m.sample_size
    for b in (
        await session.scalars(
            select(CalibrationBucket)
            .where(
                CalibrationBucket.evaluation_run_id == chosen.id,
                CalibrationBucket.dimension_key.in_(groups),
            )
            .order_by(CalibrationBucket.bucket_index)
        )
    ).all():
        groups[b.dimension_key]["calibration"].append(
            {
                "lower": b.lower,
                "upper": b.upper,
                "sample_size": b.sample_size,
                "mean_probability": b.mean_probability,
                "event_frequency": b.event_frequency,
                "gap": b.calibration_gap,
            }
        )
    return {
        "status": chosen.status,
        "evaluation_id": chosen.id,
        "source_cutoff": chosen.source_cutoff,
        "config": chosen.config_jsonb,
        "filters": chosen.filters_jsonb,
        "sample_size": chosen.sample_size,
        "groups": list(groups.values()),
        "has_more": len(keys) > limit,
        "limitations": [
            "WITHOUT_ODDS also removes research text",
            "Research fixed-unit ROI; no significance or profitability claim",
            "Closing proxy unavailable unless a closing snapshot is supplied",
        ],
    }
