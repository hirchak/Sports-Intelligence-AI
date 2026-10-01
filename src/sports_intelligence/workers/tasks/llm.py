from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sports_intelligence.core.config import Settings, get_settings
from sports_intelligence.core.job_status import JobStatus
from sports_intelligence.core.logging import get_logger
from sports_intelligence.db.models import (
    LLMCallAttempt,
    MarketPrediction,
    MatchContextRecord,
    ModelConfig,
    PredictionRun,
    ProbabilityBaseline,
    PromptVersion,
    RankedCandidate,
)
from sports_intelligence.db.session import create_engine, create_session_factory
from sports_intelligence.pipelines.discover_fixtures import update_job_status
from sports_intelligence.predictions.baselines import market_baseline, poisson_baseline
from sports_intelligence.predictions.config import ModelSpec, PredictionPolicy
from sports_intelligence.predictions.contracts import MARKETS, Variant, probability_table
from sports_intelligence.predictions.engine import EngineOutcome, PredictionEngine
from sports_intelligence.predictions.identity import content_hash, prediction_identity
from sports_intelligence.predictions.service import persist_model_config, verify_context
from sports_intelligence.predictions.telemetry import DatabaseAttemptObserver
from sports_intelligence.providers.llm.base import LLMProvider
from sports_intelligence.providers.llm.factory import build_llm_provider
from sports_intelligence.ranking.engine import rank_candidates
from sports_intelligence.workers.celery_app import celery_app
from sports_intelligence.workers.utils import record_job_attempt

logger = get_logger(__name__)


@celery_app.task(name="prediction.predict_match", queue="llm")  # type: ignore[untyped-decorator]
def predict_match_task(job_id: str, run_id: str) -> dict[str, Any]:
    result = asyncio.run(run_prediction_job(job_id, run_id))
    if result["status"] == "FAILED":
        raise RuntimeError("prediction_failed")
    return result


async def run_prediction_job(
    job_id: str,
    run_id: str,
    *,
    settings: Settings | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    provider_factory: Callable[[ModelSpec], LLMProvider] | None = None,
) -> dict[str, Any]:
    resolved = settings or get_settings()
    engine = None
    if session_factory is None:
        engine = create_engine(resolved.database_url)
        session_factory = create_session_factory(engine)
    started = datetime.now(UTC)
    error: Exception | None = None
    claimed = False
    try:
        async with session_factory() as session:
            claimed_id = await session.scalar(
                update(PredictionRun)
                .where(
                    PredictionRun.id == uuid.UUID(run_id),
                    PredictionRun.job_id == uuid.UUID(job_id),
                    PredictionRun.status == "QUEUED",
                )
                .values(status="RUNNING", started_at=started)
                .returning(PredictionRun.id)
            )
            if claimed_id is None:
                return {"status": "reused", "run_id": run_id}
            claimed = True
            await update_job_status(session, job_id, JobStatus.RUNNING)
            await session.commit()
            run = await session.get(PredictionRun, claimed_id)
            assert run is not None
            record = await session.get(MatchContextRecord, run.match_context_id)
            prompt = await session.get(PromptVersion, run.prompt_version_id)
            assert record is not None and prompt is not None
            context = verify_context(record)
            if (
                run.context_hash != record.context_hash
                or content_hash(prompt.content) != prompt.content_hash
            ):
                raise ValueError("frozen_prediction_identity_mismatch")
            policy = PredictionPolicy.model_validate(run.policy_jsonb)
            if policy.hash != run.policy_hash:
                raise ValueError("frozen_policy_identity_mismatch")
            configs = tuple(ModelSpec.model_validate(c) for c in run.route_jsonb["configs"])
            requested_config = await session.get(ModelConfig, run.requested_model_config_id)
            if (
                requested_config is None
                or not configs
                or configs[0].hash != requested_config.config_hash
                or ModelSpec.model_validate(requested_config.config_jsonb).hash
                != requested_config.config_hash
            ):
                raise ValueError("frozen_model_config_identity_mismatch")
            variant = Variant(run.variant)
        factory = provider_factory or (
            lambda spec: build_llm_provider(
                resolved,
                spec,
                timeout_seconds=policy.timeout_seconds,
            )
        )
        prediction_engine = PredictionEngine(
            factory,
            policy,
            observer=DatabaseAttemptObserver(session_factory, run, policy),
        )
        outcome = await prediction_engine.predict(
            context=context,
            context_hash=record.context_hash,
            prompt=prompt.content,
            configs=configs,
            variant=variant,
            task_type=run.task_type,
            request_id=str(run.id),
            fallback_errors=tuple(run.route_jsonb["fallback_errors"]),
        )
        async with session_factory() as session:
            stored = await session.get(PredictionRun, run.id)
            assert stored is not None
            stored.status, stored.completed_at = outcome.status, datetime.now(UTC)
            stored.audit_jsonb = [*stored.audit_jsonb, *outcome.audit]
            stored.abstain_reason = outcome.reason if outcome.status == "ABSTAINED" else None
            stored.error_code = outcome.reason if outcome.status == "FAILED" else None
            stored.latency_ms = int((stored.completed_at - started).total_seconds() * 1000)
            if outcome.output:
                stored.output_jsonb = outcome.output.model_dump(mode="json")
            await _persist_actual_identity(session, stored, prompt, outcome)
            attempts = (
                await session.scalars(
                    select(LLMCallAttempt).where(
                        LLMCallAttempt.prediction_run_id == stored.id,
                    )
                )
            ).all()
            for field_name in ("input_tokens", "output_tokens"):
                values = [
                    getattr(a, field_name) for a in attempts if getattr(a, field_name) is not None
                ]
                setattr(stored, field_name, sum(values) if values else None)
            for baseline in (poisson_baseline(context), market_baseline(context)):
                session.add(
                    ProbabilityBaseline(
                        prediction_run_id=stored.id,
                        match_context_id=record.id,
                        name=baseline.name,
                        version=baseline.version,
                        probabilities_jsonb=baseline.probabilities,
                        inputs_jsonb=baseline.inputs,
                        limitations_jsonb=list(baseline.limitations),
                        unavailable_reason=baseline.unavailable_reason,
                    )
                )
            if outcome.status == "SUCCEEDED":
                assert outcome.output is not None and outcome.output.probabilities is not None
                probabilities = probability_table(outcome.output.probabilities)
                if (
                    abs(
                        sum(
                            (
                                outcome.output.probabilities.home,
                                outcome.output.probabilities.draw,
                                outcome.output.probabilities.away,
                            )
                        )
                        - 1
                    )
                    > 0
                ):
                    stored.audit_jsonb = [*stored.audit_jsonb, "1x2_tolerance_normalization:1e-6"]
                odds_source = context.source_manifest.sources.get("odds")
                odds_id = (
                    uuid.UUID(odds_source.snapshot_id)
                    if odds_source and odds_source.snapshot_id
                    else None
                )
                captured = (
                    datetime.fromisoformat(context.market_snapshot.captured_at)
                    if context.market_snapshot.captured_at
                    else None
                )
                candidates = rank_candidates(context, probabilities, policy.ranking)
                for candidate in candidates:
                    selection = candidate.selection
                    mp = MarketPrediction(
                        prediction_run_id=stored.id,
                        market=MARKETS[selection],
                        selection=selection.value,
                        model_probability=probabilities[selection],
                        confidence=outcome.output.confidence.level,
                        evidence_for_jsonb=[e.model_dump() for e in outcome.output.evidence_for],
                        evidence_against_jsonb=[
                            e.model_dump() for e in outcome.output.evidence_against
                        ],
                        risk_flags_jsonb=outcome.output.risk_flags,
                    )
                    session.add(mp)
                    await session.flush()
                    session.add(
                        RankedCandidate(
                            prediction_run_id=stored.id,
                            market_prediction_id=mp.id,
                            odds_snapshot_set_id=odds_id,
                            odds_captured_at=captured,
                            bookmaker=candidate.bookmaker,
                            captured_odds=candidate.captured_odds,
                            market_no_vig_probability=candidate.market_probability,
                            edge=candidate.edge,
                            expected_value=candidate.expected_value,
                            rank=candidate.rank,
                            displayed=candidate.displayed,
                            filter_reasons_jsonb=list(candidate.filter_reasons),
                            policy_hash=policy.hash,
                        )
                    )
                stored.outcome = "CANDIDATES" if any(c.displayed for c in candidates) else "NO_BET"
            elif outcome.status == "ABSTAINED":
                stored.outcome = "ABSTAIN"
            else:
                error = RuntimeError(outcome.reason)
                stored.outcome = "PREDICTION_FAILED"
            job_status = JobStatus.FAILED if error else JobStatus.SUCCEEDED
            await update_job_status(session, job_id, job_status)
            await session.commit()
        return {"status": outcome.status, "run_id": run_id}
    except Exception as exc:
        error = exc
        if claimed:
            async with session_factory() as session:
                run = await session.get(PredictionRun, uuid.UUID(run_id))
                if run is not None and run.status == "RUNNING":
                    run.status, run.error_code = "FAILED", "prediction_execution_failure"
                    run.outcome, run.completed_at = "PREDICTION_FAILED", datetime.now(UTC)
                    run.audit_jsonb = [*run.audit_jsonb, "exception:" + type(exc).__name__]
                await update_job_status(session, job_id, JobStatus.FAILED)
                await session.commit()
        logger.warning(
            "prediction execution failed",
            extra={"run_id": run_id, "error_class": type(exc).__name__},
        )
        raise
    finally:
        try:
            if claimed:
                await record_job_attempt(
                    session_factory,
                    job_id=uuid.UUID(job_id),
                    started_at=started,
                    finished_at=datetime.now(UTC),
                    outcome=JobStatus.FAILED.value if error else JobStatus.SUCCEEDED.value,
                    error=error,
                )
        finally:
            if engine is not None:
                await engine.dispose()


async def _persist_actual_identity(
    session: AsyncSession,
    run: PredictionRun,
    prompt: PromptVersion,
    outcome: EngineOutcome,
) -> None:
    if outcome.config is None:
        return
    attempt_count = await session.scalar(
        select(func.count())
        .select_from(LLMCallAttempt)
        .where(
            LLMCallAttempt.prediction_run_id == run.id,
        )
    )
    if not attempt_count:
        # Missing credentials / budget refusal is not an actual runtime model call.
        return
    actual = outcome.config.model_dump(mode="json")
    if outcome.result is not None:
        actual["model"] = outcome.result.model
        run.provider_request_id = outcome.result.request_id
    run.actual_provider, run.actual_model = actual["provider"], actual["model"]
    actual_spec = ModelSpec.model_validate(actual)
    run.model_config_id = await persist_model_config(session, actual)
    run.semantic_identity = prediction_identity(
        context_hash=run.context_hash,
        prompt_hash=prompt.content_hash,
        prompt_version=prompt.semantic_version,
        provider=actual_spec.provider,
        model=actual_spec.model,
        config_hash=actual_spec.hash,
        variant=run.variant,
        role=run.role,
        phase=run.forecast_phase,
        policy_hash=run.policy_hash,
    )
