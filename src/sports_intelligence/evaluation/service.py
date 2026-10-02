from __future__ import annotations

import math
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from sports_intelligence.context.models import MarketPriceItem
from sports_intelligence.core.config import Settings
from sports_intelligence.db.models import (
    CalibrationBucket,
    CandidateSettlement,
    EvaluationMetric,
    EvaluationRun,
    Job,
    MarketPrediction,
    MatchContextRecord,
    ModelConfig,
    OddsPrice,
    OddsSnapshotSet,
    PredictionRun,
    PredictionSettlement,
    ProbabilityBaseline,
    PromptVersion,
    RankedCandidate,
)
from sports_intelligence.evaluation.config import EvaluationConfig, EvaluationFilters
from sports_intelligence.evaluation.metrics import (
    calibration,
    multiclass_brier_sum,
    probability_metrics,
)
from sports_intelligence.evaluation.results import digest, latest_results_query
from sports_intelligence.evaluation.settlement import Outcome
from sports_intelligence.predictions.baselines import canonical_selection
from sports_intelligence.predictions.contracts import Selection

FACETS = (
    "league",
    "market",
    "selection",
    "odds_bucket",
    "model_config_id",
    "provider",
    "model",
    "prompt",
    "phase",
    "data_quality",
    "confidence",
    "baseline_version",
)
RUN_FACETS = ("league", "model_config_id", "provider", "model", "prompt", "phase", "data_quality")


def configured_metrics(settings: Settings) -> EvaluationConfig:
    return EvaluationConfig(
        epsilon=settings.evaluation_epsilon,
        calibration_boundaries=tuple(settings.evaluation_calibration_boundaries),
    )


async def request_evaluation(
    session: AsyncSession, *, config: EvaluationConfig, filters: EvaluationFilters, cutoff: datetime
) -> tuple[EvaluationRun, bool]:
    if cutoff.tzinfo is None or cutoff > datetime.now(UTC):
        raise ValueError("invalid evaluation cutoff")
    cutoff = cutoff.astimezone(UTC)
    cj, fj = config.model_dump(mode="json"), filters.model_dump(mode="json", exclude_none=True)
    identity = digest({"config": cj, "filters": fj, "cutoff": cutoff.isoformat()})
    # Atomic job uniqueness serializes initial run creation by identity.
    job_id = await session.scalar(
        pg_insert(Job)
        .values(
            id=uuid.uuid4(),
            job_type="evaluate",
            status="PENDING",
            idempotency_key=f"m8:evaluate:{identity}",
            scheduled_for=datetime.now(UTC),
            priority=0,
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
        .returning(Job.id)
    )
    if job_id is None:
        run = await session.scalar(select(EvaluationRun).where(EvaluationRun.identity == identity))
        if run is None:
            raise RuntimeError("evaluation identity missing run")
        return run, False
    run = EvaluationRun(
        job_id=job_id,
        identity=identity,
        source_cutoff=cutoff,
        config_jsonb=cj,
        filters_jsonb=fj,
        source_manifest_jsonb={},
        status="QUEUED",
        sample_size=0,
    )
    session.add(run)
    await session.flush()
    return run, True


async def enqueue_evaluation(session: AsyncSession, run: EvaluationRun, created: bool) -> None:
    from sports_intelligence.workers.tasks.evaluation import evaluate_task

    await session.commit()
    if not created:
        return
    try:
        evaluate_task.apply_async(
            kwargs={"job_id": str(run.job_id), "evaluation_id": str(run.id)},
            queue="evaluation",
            task_id=str(run.job_id),
        )
    except Exception:
        run.status = "FAILED"
        run.error_class = "EnqueueFailure"
        job = await session.get(Job, run.job_id)
        if job:
            job.status = "FAILED"
        await session.commit()
        raise RuntimeError("evaluation enqueue failed") from None


def odds_bucket(odds: float | None, config: EvaluationConfig) -> str:
    if odds is None:
        return "missing"
    if not math.isfinite(odds) or odds <= 1:
        raise ValueError("invalid captured odds in evaluation")
    values = config.odds_boundaries
    for lower, upper in zip(values, values[1:], strict=False):
        if odds < upper:
            return f"[{lower:g},{upper:g})"
    return f"[{values[-1]:g},inf)"


def keys(dimensions: dict[str, str], facets: tuple[str, ...] = FACETS) -> list[dict[str, str]]:
    base = {k: dimensions[k] for k in ("role", "variant", "baseline")}
    return [base] + [{**base, name: dimensions[name]} for name in facets if name in dimensions]


def matches(
    dimensions: dict[str, str], filters: EvaluationFilters, names: tuple[str, ...] = FACETS
) -> bool:
    fj = filters.model_dump(mode="json", exclude_none=True)
    for name in (*names, "role", "variant", "baseline"):
        if name in fj and dimensions.get(name) != str(fj[name]):
            return False
    return True


@dataclass
class Aggregate:
    dimensions: dict[str, str]
    samples: list[tuple[float, int]] = field(default_factory=list)
    classes: dict[tuple[str, str], dict[str, tuple[float, int]]] = field(default_factory=dict)
    evaluated_runs: set[uuid.UUID] = field(default_factory=set)
    candidates: list[tuple[Outcome, float, float | None, float | None, float | None]] = field(
        default_factory=list
    )
    statuses: dict[str, set[uuid.UUID]] = field(default_factory=lambda: defaultdict(set))
    displayed_runs: set[uuid.UUID] = field(default_factory=set)
    latency: list[float] = field(default_factory=list)
    input_tokens: list[float] = field(default_factory=list)
    output_tokens: list[float] = field(default_factory=list)
    missing_baseline: int = 0
    coverage_available: bool = False


def aggregate_values(
    group: Aggregate, config: EvaluationConfig
) -> dict[str, tuple[float | None, int]]:
    n = len(group.samples)
    values = {
        name: (value, n) for name, value in probability_metrics(group.samples, config).items()
    }
    values["evaluated_predictions"] = (float(len(group.evaluated_runs)), len(group.evaluated_runs))
    cls = [v for v in group.classes.values() if set(v) == {"HOME", "DRAW", "AWAY"}]
    values["multiclass_1x2_brier_sum"] = (
        math.fsum(
            multiclass_brier_sum(
                [v[s][0] for s in ("HOME", "DRAW", "AWAY")],
                next(i for i, s in enumerate(("HOME", "DRAW", "AWAY")) if v[s][1]),
            )
            for v in cls
        )
        / len(cls)
        if cls
        else None,
        len(cls),
    )
    values["multiclass_1x2_log_loss"] = (
        math.fsum(
            -math.log(
                min(1 - config.epsilon, max(config.epsilon, next(p for p, y in v.values() if y)))
            )
            for v in cls
        )
        / len(cls)
        if cls
        else None,
        len(cls),
    )
    candidates = group.candidates
    decisive = [r for r in candidates if r[0] in (Outcome.WIN, Outcome.LOSS)]
    staked = [r for r in candidates if r[0] in (Outcome.WIN, Outcome.LOSS, Outcome.PUSH)]
    values["displayed_candidates"] = (float(len(candidates)), len(candidates))
    values["candidate_hit_rate"] = (
        sum(r[0] == Outcome.WIN for r in decisive) / len(decisive) if decisive else None,
        len(decisive),
    )
    values["research_roi_fixed_unit"] = (
        math.fsum(r[2] for r in staked if r[2] is not None) / len(staked) if staked else None,
        len(staked),
    )
    for name, items in (
        ("average_captured_odds", [r[1] for r in candidates]),
        ("mean_captured_expected_value", [r[3] for r in candidates if r[3] is not None]),
        ("closing_line_price_proxy", [r[4] for r in candidates if r[4] is not None]),
        ("mean_latency_ms", group.latency),
        ("mean_input_tokens", group.input_tokens),
        ("mean_output_tokens", group.output_tokens),
    ):
        if not all(math.isfinite(x) for x in items):
            raise ValueError("nonfinite metric input")
        values[name] = (math.fsum(items) / len(items) if items else None, len(items))
    valid = len(group.statuses["SUCCEEDED"])
    abstain = len(group.statuses["ABSTAINED"])
    total = valid + abstain
    for status, name in (
        ("SUCCEEDED", "valid_prediction_runs"),
        ("ABSTAINED", "abstained_prediction_runs"),
        ("FAILED", "failed_prediction_runs"),
        ("IN_FLIGHT", "in_flight_prediction_runs"),
    ):
        values[name] = (float(len(group.statuses[status])), len(group.statuses[status]))
    values["forecast_coverage"] = (valid / total if total else None, total)
    values["abstention_rate"] = (abstain / total if total else None, total)
    values["candidate_display_coverage"] = (
        len(group.displayed_runs) / valid if valid else None,
        valid,
    )
    if not group.coverage_available and not any(group.statuses.values()):
        for name in (
            "valid_prediction_runs",
            "abstained_prediction_runs",
            "failed_prediction_runs",
            "in_flight_prediction_runs",
            "forecast_coverage",
            "abstention_rate",
            "candidate_display_coverage",
        ):
            values.pop(name, None)
    values["missing_baseline_probabilities"] = (
        float(group.missing_baseline),
        group.missing_baseline,
    )
    return values


async def calculate_evaluation(session: AsyncSession, evaluation: EvaluationRun) -> None:
    """Worker-only measurement. Stream M7 runs in bounded pages; no writes to M7 tables."""
    config = EvaluationConfig.model_validate(evaluation.config_jsonb)
    filters = EvaluationFilters.model_validate(evaluation.filters_jsonb)
    cutoff = evaluation.source_cutoff
    closing_rows = (
        await session.execute(
            select(OddsSnapshotSet, OddsPrice)
            .join(OddsPrice, OddsPrice.snapshot_set_id == OddsSnapshotSet.id)
            .where(
                OddsSnapshotSet.id.in_(config.closing_snapshot_ids),
                OddsSnapshotSet.captured_at <= cutoff,
            )
            .order_by(OddsSnapshotSet.captured_at.desc(), OddsSnapshotSet.id, OddsPrice.id)
        )
    ).all()
    manifest_closing = sorted({str(snapshot.id) for snapshot, _ in closing_rows})
    groups: dict[str, Aggregate] = {}
    manifest: dict[str, Any] = {
        "prediction_runs": [],
        "fixture_results": set(),
        "settlements": set(),
        "baselines": set(),
        "market_predictions": set(),
        "ranked_candidates": set(),
        "closing_snapshots": manifest_closing,
    }
    query = (
        select(PredictionRun, MatchContextRecord, PromptVersion)
        .join(MatchContextRecord, MatchContextRecord.id == PredictionRun.match_context_id)
        .join(PromptVersion, PromptVersion.id == PredictionRun.prompt_version_id)
        .where(PredictionRun.created_at <= cutoff, PredictionRun.as_of <= cutoff)
    )
    if filters.start:
        query = query.where(PredictionRun.as_of >= filters.start)
    if filters.end:
        query = query.where(PredictionRun.as_of < filters.end)
    offset = 0
    while True:
        page = (
            await session.execute(query.order_by(PredictionRun.id).limit(200).offset(offset))
        ).all()
        if not page:
            break
        run_map = {run.id: (run, context, prompt) for run, context, prompt in page}
        ids = list(run_map)
        configs = {
            m.id: m
            for m in (
                await session.scalars(
                    select(ModelConfig).where(
                        ModelConfig.id.in_(
                            {r.model_config_id or r.requested_model_config_id for r, _, _ in page}
                        )
                    )
                )
            ).all()
        }
        baseline_map = {
            (b.prediction_run_id, b.name): b
            for b in (
                await session.scalars(
                    select(ProbabilityBaseline).where(
                        ProbabilityBaseline.prediction_run_id.in_(ids)
                    )
                )
            ).all()
        }
        settlements = (
            await session.execute(
                select(MarketPrediction, PredictionSettlement, RankedCandidate, CandidateSettlement)
                .select_from(MarketPrediction)
                .outerjoin(
                    PredictionSettlement,
                    (PredictionSettlement.market_prediction_id == MarketPrediction.id)
                    & PredictionSettlement.fixture_result_id.in_(latest_results_query(cutoff))
                    & (PredictionSettlement.settlement_version == config.settlement_version)
                    & (PredictionSettlement.settled_at <= cutoff),
                )
                .outerjoin(
                    RankedCandidate, RankedCandidate.market_prediction_id == MarketPrediction.id
                )
                .outerjoin(
                    CandidateSettlement,
                    (CandidateSettlement.ranked_candidate_id == RankedCandidate.id)
                    & (CandidateSettlement.prediction_settlement_id == PredictionSettlement.id),
                )
                .where(
                    MarketPrediction.prediction_run_id.in_(ids),
                )
            )
        ).all()
        by_run: dict[uuid.UUID, list[Any]] = defaultdict(list)
        for row in settlements:
            by_run[row[0].prediction_run_id].append(row)
        for rid, (run, context, prompt) in run_map.items():
            data = context.context_jsonb
            rd = {
                "role": run.role,
                "variant": run.variant,
                "league": str(data["fixture_identity"]["league_id"]),
                "model_config_id": str(run.model_config_id or run.requested_model_config_id),
                "provider": run.actual_provider or configs[run.requested_model_config_id].provider,
                "model": run.actual_model or configs[run.requested_model_config_id].model_id,
                "prompt": prompt.semantic_version,
                "phase": run.forecast_phase,
                "data_quality": str(data["data_quality"]["quality_band"]),
            }
            # Segment missing actual identity by frozen requested config.
            if not matches({**rd, "baseline": filters.baseline or "llm"}, filters, RUN_FACETS):
                continue
            manifest["prediction_runs"].append(str(rid))
            status = run.status if run.completed_at and run.completed_at <= cutoff else "IN_FLIGHT"
            for source in ("llm", "market", "statistical"):
                base = baseline_map.get((rid, source))
                dimensions = {
                    **rd,
                    "baseline": source,
                    "baseline_version": base.version
                    if base
                    else ("m7_v1" if source == "llm" else "missing"),
                }
                if not matches(dimensions, filters, RUN_FACETS):
                    continue
                if base:
                    manifest["baselines"].add(str(base.id))
                run_keys = keys(dimensions, RUN_FACETS)
                has_sample_filter = any(
                    getattr(filters, k) is not None
                    for k in ("market", "selection", "odds_bucket", "confidence")
                )
                if not has_sample_filter:
                    for dims in run_keys:
                        group = groups.setdefault(digest(dims), Aggregate(dims))
                        group.coverage_available = True
                        group.statuses[status].add(rid)
                        if source == "llm" and status != "IN_FLIGHT":
                            for value, target in (
                                (run.latency_ms, group.latency),
                                (run.input_tokens, group.input_tokens),
                                (run.output_tokens, group.output_tokens),
                            ):
                                if value is not None:
                                    target.append(float(value))
                if status != "SUCCEEDED":
                    continue
                for prediction, settlement, candidate, candidate_result in by_run[rid]:
                    outcome = Outcome(settlement.outcome) if settlement else Outcome.UNSETTLED
                    manifest["market_predictions"].add(str(prediction.id))
                    if candidate:
                        manifest["ranked_candidates"].add(str(candidate.id))
                    if settlement:
                        manifest["fixture_results"].add(str(settlement.fixture_result_id))
                        manifest["settlements"].add(str(settlement.id))
                    dims = {
                        **dimensions,
                        "market": prediction.market,
                        "selection": prediction.selection,
                        "confidence": prediction.confidence,
                        "odds_bucket": odds_bucket(
                            candidate.captured_odds if candidate else None, config
                        ),
                    }
                    if not matches(dims, filters):
                        continue
                    p = (
                        prediction.model_probability
                        if source == "llm"
                        else (base.probabilities_jsonb.get(prediction.selection) if base else None)
                    )
                    for key_dims in keys(dims):
                        group = groups.setdefault(digest(key_dims), Aggregate(key_dims))
                        if outcome in (Outcome.WIN, Outcome.LOSS):
                            if p is None:
                                group.missing_baseline += 1
                            else:
                                y = int(outcome == Outcome.WIN)
                                # Validated by metrics; bad rows fail the auditable evaluation job.
                                group.samples.append((p, y))
                                group.evaluated_runs.add(rid)
                                if prediction.selection in (
                                    Selection.HOME,
                                    Selection.DRAW,
                                    Selection.AWAY,
                                ):
                                    group.classes.setdefault((str(rid), source), {})[
                                        prediction.selection
                                    ] = (p, y)
                        if source == "llm" and candidate and candidate.displayed:
                            if candidate.captured_odds is None or (
                                settlement and candidate_result is None
                            ):
                                raise ValueError("displayed candidate lacks settlement evidence")
                            group.displayed_runs.add(rid)
                            closing_proxy = None
                            kickoff = datetime.fromisoformat(data["fixture_identity"]["kickoff_at"])
                            for snapshot, price in closing_rows:
                                if (
                                    snapshot.fixture_id == run.fixture_id
                                    and snapshot.captured_at <= kickoff
                                    and candidate.odds_captured_at is not None
                                    and snapshot.captured_at > candidate.odds_captured_at
                                    and price.bookmaker == candidate.bookmaker
                                    and canonical_selection(
                                        MarketPriceItem(
                                            market=price.market,
                                            selection=price.selection,
                                            decimal_odds=float(price.decimal_odds),
                                            implied_probability=float(price.implied_probability),
                                            bookmaker=price.bookmaker,
                                            line=float(price.line)
                                            if price.line is not None
                                            else None,
                                        )
                                    )
                                    == prediction.selection
                                ):
                                    closing_odds = float(price.decimal_odds)
                                    odds_bucket(closing_odds, config)
                                    closing_proxy = candidate.captured_odds / closing_odds - 1
                                    break
                            group.candidates.append(
                                (
                                    outcome,
                                    candidate.captured_odds,
                                    candidate_result.net_return if candidate_result else None,
                                    candidate.expected_value,
                                    closing_proxy,
                                )
                            )
        offset += len(page)
    for dk, group in groups.items():
        for name, (value, n) in aggregate_values(group, config).items():
            if value is not None and not math.isfinite(value):
                raise ValueError("nonfinite aggregate")
            session.add(
                EvaluationMetric(
                    evaluation_run_id=evaluation.id,
                    dimension_key=dk,
                    dimensions_jsonb=group.dimensions,
                    metric_name=name,
                    metric_value=value,
                    sample_size=n,
                )
            )
        for i, b in enumerate(calibration(group.samples, config)):
            session.add(
                CalibrationBucket(
                    evaluation_run_id=evaluation.id,
                    dimension_key=dk,
                    bucket_index=i,
                    lower=b.lower,
                    upper=b.upper,
                    sample_size=b.sample_size,
                    mean_probability=b.mean_probability,
                    event_frequency=b.event_frequency,
                    calibration_gap=b.gap,
                )
            )
    manifest = {k: sorted(v) for k, v in manifest.items()}
    evaluation.source_manifest_jsonb = manifest
    evaluation.sample_size = sum(
        len(g.samples)
        for g in groups.values()
        if len(g.dimensions) == 3 and g.dimensions["baseline"] == "llm"
    )
    evaluation.status = "SUCCEEDED"
    evaluation.completed_at = datetime.now(UTC)
    await session.flush()
