from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from sports_intelligence.context.models import MatchContextV1
from sports_intelligence.core.config import Settings
from sports_intelligence.db.models import (
    Job,
    LLMCallAttempt,
    MarketPrediction,
    MatchContextRecord,
    ModelConfig,
    PredictionRun,
    ProbabilityBaseline,
    PromptVersion,
    RankedCandidate,
)
from sports_intelligence.pipelines.discover_fixtures import create_or_get_job
from sports_intelligence.predictions.config import load_llm_config, task_type
from sports_intelligence.predictions.contracts import Role, Variant
from sports_intelligence.predictions.identity import (
    PromptIdentity,
    fingerprint,
    load_prompt,
    prediction_identity,
)
from sports_intelligence.predictions.router import ModelRouter
from sports_intelligence.predictions.telemetry import recent_health


async def persist_prompt(session: AsyncSession, prompt: PromptIdentity) -> uuid.UUID:
    statement = (
        pg_insert(PromptVersion)
        .values(
            prompt_name=prompt.name,
            semantic_version=prompt.version,
            content_hash=prompt.hash,
            source_identity=prompt.source_identity,
            content=prompt.content,
            active=True,
        )
        .on_conflict_do_nothing(constraint="uq_prompt_versions_identity")
        .returning(PromptVersion.id)
    )
    found = await session.scalar(statement)
    if found is not None:
        return found
    existing = await session.scalar(
        select(PromptVersion.id).where(
            PromptVersion.prompt_name == prompt.name,
            PromptVersion.semantic_version == prompt.version,
            PromptVersion.content_hash == prompt.hash,
        )
    )
    assert existing is not None
    return existing


async def persist_model_config(session: AsyncSession, config: dict[str, Any]) -> uuid.UUID:
    config_hash = fingerprint(config)
    found = await session.scalar(
        pg_insert(ModelConfig)
        .values(
            provider=config["provider"],
            model_id=config["model"],
            temperature=config.get("temperature"),
            max_tokens=config["max_output_tokens"],
            structured_mode=config["structured_mode"],
            config_hash=config_hash,
            config_jsonb=config,
        )
        .on_conflict_do_nothing(index_elements=[ModelConfig.config_hash])
        .returning(ModelConfig.id)
    )
    if found is not None:
        return found
    existing = await session.scalar(
        select(ModelConfig.id).where(ModelConfig.config_hash == config_hash)
    )
    assert existing is not None
    return existing


def verify_context(record: MatchContextRecord) -> MatchContextV1:
    context = MatchContextV1.model_validate(record.context_jsonb)
    digest = hashlib.sha256(context.canonical_json().encode()).hexdigest()
    if (
        digest != record.context_hash
        or context.fixture_id != str(record.fixture_id)
        or context.fixture_identity.fixture_id != context.fixture_id
        or context.data_quality.forecast_phase != context.forecast_phase
        or datetime.fromisoformat(context.data_quality.as_of) != record.as_of
    ):
        raise ValueError("context_integrity_mismatch")
    if (
        context.forecast_phase != record.forecast_phase
        or datetime.fromisoformat(context.as_of) != record.as_of
    ):
        raise ValueError("context_metadata_mismatch")
    return context


async def request_prediction(
    session: AsyncSession,
    *,
    record: MatchContextRecord,
    settings: Settings,
    role: Role = Role.PRIMARY,
    variant: Variant = Variant.WITH_ODDS,
    route_override: str | None = None,
    rerun_key: str | None = None,
) -> tuple[PredictionRun, bool]:
    context = verify_context(record)
    if record.forecast_phase not in ("MORNING", "PREMATCH"):
        raise ValueError("M7 permits only pre-match phases")
    config = load_llm_config(settings)
    health = await recent_health(session, config.policy)
    decision = ModelRouter(config).select(task_type(role), health=health, override=route_override)
    prompt = load_prompt(settings.prediction_prompt_path)
    prompt_id = await persist_prompt(session, prompt)
    model_id = await persist_model_config(session, decision.selected.model_dump(mode="json"))
    identity = prediction_identity(
        context_hash=record.context_hash,
        prompt_hash=prompt.hash,
        prompt_version=prompt.version,
        provider=decision.selected.provider,
        model=decision.selected.model,
        config_hash=decision.selected.hash,
        variant=variant.value,
        role=role.value,
        phase=record.forecast_phase,
        policy_hash=config.policy.hash,
    )
    # Routing/fallback semantics are frozen into request identity as well as probabilities.
    requested = fingerprint({"prediction": identity, "route": decision.fingerprint})
    key = fingerprint({"request": requested, "rerun": rerun_key})
    job, _ = await create_or_get_job(
        session,
        job_type="prediction",
        idempotency_key="prediction:" + key,
        scheduled_for=datetime.now(UTC),
    )
    values = dict(
        fixture_id=record.fixture_id,
        match_context_id=record.id,
        context_hash=record.context_hash,
        as_of=record.as_of,
        forecast_phase=context.forecast_phase,
        job_id=job.id,
        prompt_version_id=prompt_id,
        requested_model_config_id=model_id,
        role=role.value,
        variant=variant.value,
        task_type=task_type(role),
        requested_route=decision.route_name,
        route_fingerprint=decision.fingerprint,
        route_jsonb={
            "configs": [
                m.model_dump(mode="json") for m in (decision.selected, *decision.fallbacks)
            ],
            "fallback_errors": config.routes[decision.route_name].fallback_errors,
        },
        policy_jsonb=config.policy.model_dump(mode="json"),
        policy_hash=config.policy.hash,
        requested_identity=requested,
        request_key=key,
        rerun_key=rerun_key,
        status="QUEUED",
        audit_jsonb=list(decision.audit),
    )
    await session.execute(update(Job).where(Job.id == job.id).values(fixture_id=record.fixture_id))
    new_id = await session.scalar(
        pg_insert(PredictionRun)
        .values(**values)
        .on_conflict_do_nothing(
            index_elements=[PredictionRun.request_key],
        )
        .returning(PredictionRun.id)
    )
    run = await session.scalar(select(PredictionRun).where(PredictionRun.request_key == key))
    assert run is not None
    return run, new_id is not None


async def enqueue_prediction(
    session: AsyncSession,
    run: PredictionRun,
    created: bool,
) -> bool:
    """Persist before queueing. Worker CAS handles redelivery; enqueue errors are auditable."""
    await session.commit()
    if not created:
        return False
    from sports_intelligence.workers.tasks.llm import predict_match_task

    try:
        predict_match_task.apply_async(args=[str(run.job_id), str(run.id)], queue="llm")
    except Exception:
        from sports_intelligence.core.job_status import JobStatus
        from sports_intelligence.pipelines.discover_fixtures import update_job_status

        run.status, run.error_code = "FAILED", "enqueue_failed"
        run.completed_at = datetime.now(UTC)
        await update_job_status(session, str(run.job_id), JobStatus.FAILED)
        await session.commit()
        raise RuntimeError("prediction_enqueue_failed") from None
    return True


async def automatic_prediction(
    session: AsyncSession,
    record: MatchContextRecord,
    settings: Settings,
) -> PredictionRun | None:
    if not settings.prediction_auto_enabled or record.forecast_phase not in ("MORNING", "PREMATCH"):
        return None
    context = verify_context(record)
    policy = load_llm_config(settings).policy
    if (
        not context.data_quality.can_predict
        or context.data_quality.overall_score < policy.min_data_quality
    ):
        return None
    run, created = await request_prediction(
        session,
        record=record,
        settings=settings,
        variant=Variant(settings.prediction_auto_variant),
    )
    await enqueue_prediction(session, run, created)
    return run


async def read_prediction(session: AsyncSession, run_id: uuid.UUID) -> dict[str, Any] | None:
    run = await session.get(PredictionRun, run_id)
    if run is None:
        return None
    context = await session.get(MatchContextRecord, run.match_context_id)
    prompt = await session.get(PromptVersion, run.prompt_version_id)
    requested_config = await session.get(ModelConfig, run.requested_model_config_id)
    actual_config = (
        await session.get(ModelConfig, run.model_config_id) if run.model_config_id else None
    )
    assert context is not None and prompt is not None and requested_config is not None
    probabilities = (
        await session.scalars(
            select(MarketPrediction)
            .where(
                MarketPrediction.prediction_run_id == run.id,
            )
            .order_by(MarketPrediction.selection)
        )
    ).all()
    candidates = (
        await session.scalars(
            select(RankedCandidate)
            .where(
                RankedCandidate.prediction_run_id == run.id,
            )
            .order_by(RankedCandidate.rank.asc().nulls_last(), RankedCandidate.market_prediction_id)
        )
    ).all()
    markets_by_id = {p.id: p for p in probabilities}
    baselines = (
        await session.scalars(
            select(ProbabilityBaseline)
            .where(
                ProbabilityBaseline.prediction_run_id == run.id,
            )
            .order_by(ProbabilityBaseline.name)
        )
    ).all()
    attempts = (
        await session.scalars(
            select(LLMCallAttempt)
            .where(
                LLMCallAttempt.prediction_run_id == run.id,
            )
            .order_by(LLMCallAttempt.attempt_number)
        )
    ).all()
    identity = context.context_jsonb["fixture_identity"]
    return {
        "id": run.id,
        "fixture_id": run.fixture_id,
        "match_context_id": run.match_context_id,
        "context_hash": run.context_hash,
        "as_of": run.as_of,
        "forecast_phase": run.forecast_phase,
        "role": run.role,
        "variant": run.variant,
        "status": run.status,
        "outcome": run.outcome,
        "home_team": identity.get("home_team_name"),
        "away_team": identity.get("away_team_name"),
        "data_quality": context.context_jsonb["data_quality"]["overall_score"],
        "abstain_reason": run.abstain_reason,
        "error_code": run.error_code,
        "created_at": run.created_at,
        "completed_at": run.completed_at,
        "actual_provider": run.actual_provider,
        "actual_model": run.actual_model,
        "model_config_hash": actual_config.config_hash if actual_config else None,
        "runtime_model_config": actual_config.config_jsonb if actual_config else None,
        "requested_model_config": requested_config.config_jsonb,
        "prompt_name": prompt.prompt_name,
        "prompt_version": prompt.semantic_version,
        "prompt_hash": prompt.content_hash,
        "prompt_source": prompt.source_identity,
        "requested_identity": run.requested_identity,
        "semantic_identity": run.semantic_identity,
        "requested_route": run.requested_route,
        "route_fingerprint": run.route_fingerprint,
        "policy": run.policy_jsonb,
        "policy_hash": run.policy_hash,
        "latency_ms": run.latency_ms,
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "provider_request_id": run.provider_request_id,
        "audit": run.audit_jsonb,
        "output": run.output_jsonb,
        "probabilities": [
            {"market": p.market, "selection": p.selection, "model_probability": p.model_probability}
            for p in probabilities
        ],
        "candidates": [
            {
                "selection": markets_by_id[c.market_prediction_id].selection,
                "model_probability": markets_by_id[c.market_prediction_id].model_probability,
                "captured_odds": c.captured_odds,
                "market_probability": c.market_no_vig_probability,
                "edge": c.edge,
                "expected_value": c.expected_value,
                "rank": c.rank,
                "displayed": c.displayed,
                "filter_reasons": c.filter_reasons_jsonb,
                "bookmaker": c.bookmaker,
                "odds_snapshot_set_id": c.odds_snapshot_set_id,
                "odds_captured_at": c.odds_captured_at,
            }
            for c in candidates
        ],
        "baselines": [
            {
                "name": b.name,
                "version": b.version,
                "probabilities": b.probabilities_jsonb,
                "inputs": b.inputs_jsonb,
                "limitations": b.limitations_jsonb,
                "unavailable_reason": b.unavailable_reason,
            }
            for b in baselines
        ],
        "attempts": [
            {
                "attempt_number": a.attempt_number,
                "provider": a.provider,
                "model": a.model,
                "actual_model": a.actual_model,
                "purpose": a.purpose,
                "health": a.health,
                "error_code": a.error_code,
                "latency_ms": a.latency_ms,
                "input_tokens": a.input_tokens,
                "output_tokens": a.output_tokens,
                "request_id": a.provider_request_id,
                "finish_reason": a.finish_reason,
            }
            for a in attempts
        ],
    }
