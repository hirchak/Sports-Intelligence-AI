from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sports_intelligence.core.config import Settings
from sports_intelligence.db.models import (
    Experiment,
    ExperimentArm,
    ExperimentCall,
    ExperimentCase,
    ExperimentPrediction,
    ExperimentRun,
    ExternalApiRequest,
    LLMCallAttempt,
    MatchContextRecord,
)
from sports_intelligence.evaluation.results import digest
from sports_intelligence.experiments.contracts import ExperimentDefinition, FrozenArm
from sports_intelligence.experiments.planner import verify_frozen
from sports_intelligence.experiments.service import change_run_state
from sports_intelligence.predictions.baselines import market_baseline, poisson_baseline
from sports_intelligence.predictions.config import ModelSpec
from sports_intelligence.predictions.contracts import probability_table
from sports_intelligence.predictions.engine import PredictionEngine
from sports_intelligence.predictions.identity import content_hash, fingerprint
from sports_intelligence.predictions.service import read_prediction
from sports_intelligence.providers.llm.base import LLMError, LLMProvider, LLMResult
from sports_intelligence.providers.llm.factory import build_llm_provider
from sports_intelligence.ranking.engine import rank_candidates


class ExperimentObserver:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        prediction: ExperimentPrediction,
        run: ExperimentRun,
        definition: ExperimentDefinition,
        arm: FrozenArm,
    ) -> None:
        self.factory, self.prediction, self.run, self.definition, self.arm = (
            factory,
            prediction,
            run,
            definition,
            arm,
        )

    async def reserve(self, config: ModelSpec, purpose: str) -> str:
        async with self.factory() as session, session.begin():
            await session.execute(text("SELECT pg_advisory_xact_lock(707001)"))
            run = await session.scalar(
                select(ExperimentRun).where(ExperimentRun.id == self.run.id).with_for_update()
            )
            if run is None or run.status != "RUNNING":
                raise LLMError("experiment_not_running")
            total = await session.scalar(
                select(func.count())
                .select_from(ExperimentCall)
                .where(ExperimentCall.run_id == run.id)
            )
            arm_total = await session.scalar(
                select(func.count())
                .select_from(ExperimentCall)
                .where(
                    ExperimentCall.run_id == run.id, ExperimentCall.arm_id == self.prediction.arm_id
                )
            )
            if (total or 0) >= self.definition.max_llm_calls or (
                arm_total or 0
            ) >= self.definition.max_calls_per_arm:
                raise LLMError("experiment_budget_exhausted")
            day = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            daily_m7 = await session.scalar(
                select(func.count())
                .select_from(LLMCallAttempt)
                .where(LLMCallAttempt.started_at >= day)
            )
            daily_m9 = await session.scalar(
                select(func.count())
                .select_from(ExperimentCall)
                .where(ExperimentCall.started_at >= day)
            )
            if (daily_m7 or 0) + (daily_m9 or 0) >= self.arm.policy.max_calls_per_day:
                raise LLMError("daily_budget_exceeded")
            call = ExperimentCall(
                run_id=run.id,
                arm_id=self.prediction.arm_id,
                prediction_id=self.prediction.id,
                provider=config.provider,
                model=config.model,
                purpose=purpose,
            )
            session.add(call)
            await session.flush()
            return str(call.id)

    async def finish(self, attempt: str, result: LLMResult | None, error: LLMError | None) -> None:
        async with self.factory() as session, session.begin():
            call = await session.get(ExperimentCall, UUID(attempt))
            assert call is not None
            call.finished_at = datetime.now(UTC)
            call.error_code = error.code if error else result.error_code if result else None
            if result:
                call.result_jsonb = {
                    k: v for k, v in asdict(result).items() if k != "parsed_output"
                }
            if call.provider != "mock":
                ledger = ExternalApiRequest(
                    provider=call.provider,
                    endpoint_category="experiment_prediction",
                    started_at=call.started_at,
                    duration_ms=int((call.finished_at - call.started_at).total_seconds() * 1000),
                    status_code=error.status_code
                    if error
                    else result.status_code
                    if result
                    else None,
                    cache_hit=False,
                    priority="P3",
                    degradation_mode="NORMAL",
                    error_class=call.error_code,
                    estimated_cost=1,
                    actual_cost=1,
                )  # Provider request units, never monetary cost.
                session.add(ledger)
                await session.flush()
                call.external_request_id = ledger.id


async def execute_prediction(
    factory: async_sessionmaker[AsyncSession],
    prediction_id: UUID,
    settings: Settings,
    provider_factory: Callable[[ModelSpec], LLMProvider] | None = None,
) -> bool:
    async with factory() as session:
        claimed = await session.scalar(
            update(ExperimentPrediction)
            .where(
                ExperimentPrediction.id == prediction_id,
                ExperimentPrediction.status == "QUEUED",
            )
            .values(status="RUNNING", started_at=datetime.now(UTC))
            .returning(ExperimentPrediction.id)
        )
        if claimed is None:
            return False
        await session.commit()
        prediction = await session.get(ExperimentPrediction, claimed)
        assert prediction is not None
        case = await session.get(ExperimentCase, prediction.case_id)
        arm_row = await session.get(ExperimentArm, prediction.arm_id)
        assert case is not None and arm_row is not None
        run = await session.get(ExperimentRun, case.run_id)
        assert run is not None
        experiment = await session.get(Experiment, run.experiment_id)
        assert experiment is not None
        definition = ExperimentDefinition.model_validate(experiment.definition_jsonb)
        arm = FrozenArm.model_validate(arm_row.frozen_jsonb)
        if (
            fingerprint(run.manifest_jsonb) != run.manifest_hash
            or arm.hash != arm_row.identity_hash
            or content_hash(arm.prompt_content) != arm.prompt_hash
        ):
            raise ValueError("experiment_identity_mismatch")
        if (
            arm.request.source == "replay"
            and any(m.provider != "mock" for m in arm.models)
            and (
                not run.live_opt_in
                or not settings.experiment_live_enabled
                or settings.app_env != "live_local"
            )
        ):
            raise ValueError("live_experiment_not_authorized")
        cid = case.control_context_id if arm_row.name == "control" else case.treatment_context_id
        record = await session.get(MatchContextRecord, cid)
        if record is None:
            raise ValueError("missing_frozen_context")
        context = await verify_frozen(session, record)
        expected = case.lineage_jsonb[arm_row.name]
        if (
            str(record.id) != expected["context_id"]
            or record.context_hash != expected["context_hash"]
            or record.as_of.isoformat() != expected["as_of"]
        ):
            raise ValueError("manifest_context_mismatch")
    if arm.request.source != "replay":
        async with factory() as session, session.begin():
            historical = await read_prediction(session, UUID(expected["historical_prediction_id"]))
            if historical is None or digest(historical) != expected["historical_prediction_hash"]:
                raise ValueError("historical_prediction_integrity_mismatch")
            stored = await session.get(ExperimentPrediction, prediction.id)
            assert stored is not None
            stored.status = historical["status"]
            stored.reason = historical["error_code"] or historical["abstain_reason"]
            stored.completed_at = datetime.now(UTC)
            stored.output_jsonb = historical["output"]
            stored.probabilities_jsonb = {
                p["selection"]: p["model_probability"] for p in historical["probabilities"]
            }
            stored.candidates_jsonb = [
                {
                    "selection": c["selection"],
                    "displayed": c["displayed"],
                    "captured_odds": c["captured_odds"],
                    "expected_value": c["expected_value"],
                }
                for c in historical["candidates"]
            ]
            stored.baselines_jsonb = historical["baselines"]
            stored.actual_identity_jsonb = {
                "source": arm.request.source,
                "historical_prediction_id": expected["historical_prediction_id"],
                "historical_prediction_hash": expected["historical_prediction_hash"],
                "provider": historical["actual_provider"],
                "model": historical["actual_model"],
                "prompt_hash": historical["prompt_hash"],
                "prompt_version": historical["prompt_version"],
                "actual_config": historical["runtime_model_config"],
                "context_hash": record.context_hash,
                "feature_version": context.deterministic_features.schema_version,
                "telemetry": {
                    k: historical[k] for k in ("latency_ms", "input_tokens", "output_tokens")
                },
            }
            stored.audit_jsonb = ["reused_immutable_historical_forecast"]
        return True
    engine = PredictionEngine(
        provider_factory
        or (
            lambda spec: build_llm_provider(
                settings, spec, timeout_seconds=arm.policy.timeout_seconds
            )
        ),
        arm.policy,
        observer=ExperimentObserver(factory, prediction, run, definition, arm),
    )
    outcome = await engine.predict(
        context=context,
        context_hash=record.context_hash,
        prompt=arm.prompt_content,
        configs=arm.models,
        variant=arm.request.variant,
        task_type="experiment_prediction",
        request_id=str(prediction.id),
        fallback_errors=arm.fallback_errors,
    )
    async with factory() as session, session.begin():
        stored = await session.get(ExperimentPrediction, prediction.id)
        assert stored is not None
        stored.status, stored.reason, stored.completed_at = (
            outcome.status,
            outcome.reason,
            datetime.now(UTC),
        )
        stored.audit_jsonb = list(outcome.audit)
        if outcome.output:
            stored.output_jsonb = outcome.output.model_dump(mode="json")
            if outcome.output.probabilities and outcome.status == "SUCCEEDED":
                ps = probability_table(outcome.output.probabilities)
                stored.probabilities_jsonb = {s.value: p for s, p in ps.items()}
                stored.candidates_jsonb = [
                    {**asdict(c), "selection": c.selection.value}
                    for c in rank_candidates(context, ps, arm.policy.ranking)
                ]
        stored.baselines_jsonb = [
            asdict(b) for b in (market_baseline(context), poisson_baseline(context))
        ]
        stored.actual_identity_jsonb = {
            "arm_hash": arm.hash,
            "prompt_hash": arm.prompt_hash,
            "prompt_version": arm.prompt_version,
            "context_id": str(record.id),
            "context_hash": record.context_hash,
            "feature_version": context.deterministic_features.schema_version,
            "provider": outcome.result.provider if outcome.result else None,
            "model": outcome.result.model if outcome.result else None,
            "actual_config": (
                {
                    **outcome.config.model_dump(mode="json"),
                    "model": outcome.result.model if outcome.result else outcome.config.model,
                }
                if outcome.config
                else None
            ),
        }
    return True


async def run_batch(
    factory: async_sessionmaker[AsyncSession],
    run_id: UUID,
    settings: Settings,
    provider_factory: Callable[[ModelSpec], LLMProvider] | None = None,
) -> dict[str, Any]:
    # A persisted claim on each output protects against duplicate worker deliveries.
    # Advisory session lock keeps batches sequential without a long DB transaction.
    bind = cast(AsyncEngine, factory.kw["bind"])
    async with bind.connect() as lock_session:
        lock_key = int(run_id.hex[:15], 16)
        acquired = await lock_session.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key}
        )
        await lock_session.commit()
        if not acquired:
            return {"status": "reused", "run_id": str(run_id)}
        try:
            async with factory() as session:
                run = await session.get(ExperimentRun, run_id)
                if run is None:
                    raise ValueError("experiment_run_not_found")
                if run.status not in ("QUEUED", "RUNNING"):
                    return {"status": run.status, "run_id": str(run_id)}
                if run.status == "QUEUED":
                    await change_run_state(session, run, "RUNNING", "replay_worker")
                    await session.commit()
                experiment = await session.get(Experiment, run.experiment_id)
                assert experiment is not None
                definition = ExperimentDefinition.model_validate(experiment.definition_jsonb)
                predictions = list(
                    (
                        await session.scalars(
                            select(ExperimentPrediction.id)
                            .join(ExperimentCase)
                            .where(
                                ExperimentCase.run_id == run.id,
                                ExperimentPrediction.status == "QUEUED",
                            )
                            .order_by(ExperimentCase.ordinal, ExperimentPrediction.arm_id)
                            .limit(definition.batch_size * 2)
                        )
                    ).all()
                )
            for pid in predictions:
                try:
                    await execute_prediction(factory, pid, settings, provider_factory)
                except Exception as exc:
                    async with factory() as session, session.begin():
                        p = await session.get(ExperimentPrediction, pid)
                        assert p is not None
                        p.status, p.reason = "FAILED", "replay_integrity_or_execution_failure"
                        p.audit_jsonb = [type(exc).__name__]
                        p.completed_at = datetime.now(UTC)
            async with factory() as session:
                statuses = list(
                    (
                        await session.scalars(
                            select(ExperimentPrediction.status)
                            .join(ExperimentCase)
                            .where(ExperimentCase.run_id == run_id)
                        )
                    ).all()
                )
                if "RUNNING" in statuses:
                    run = await session.get(ExperimentRun, run_id)
                    assert run is not None
                    run.error_code = "interrupted_case_requires_inspection"
                    await change_run_state(session, run, "FAILED", "replay_worker")
                    await session.commit()
                    return {"status": "NEEDS_INSPECTION", "run_id": str(run_id)}
                return {
                    "status": "MORE" if "QUEUED" in statuses else "EVALUATION_READY",
                    "run_id": str(run_id),
                }
        finally:
            await lock_session.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
            await lock_session.commit()
