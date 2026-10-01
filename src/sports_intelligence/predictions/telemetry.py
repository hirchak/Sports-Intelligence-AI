from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sports_intelligence.db.models import ExternalApiRequest, LLMCallAttempt, PredictionRun
from sports_intelligence.predictions.config import ModelSpec, PredictionPolicy
from sports_intelligence.predictions.router import Health
from sports_intelligence.providers.llm.base import LLMError, LLMResult


async def recent_health(
    session: AsyncSession,
    policy: PredictionPolicy,
) -> dict[tuple[str, str], Health]:
    now = datetime.now(UTC)
    rows = (
        await session.scalars(
            select(LLMCallAttempt)
            .where(
                LLMCallAttempt.finished_at >= now - timedelta(seconds=policy.health_ttl_seconds),
            )
            .order_by(LLMCallAttempt.finished_at.desc(), LLMCallAttempt.id.asc())
        )
    ).all()
    result: dict[tuple[str, str], Health] = {}
    for row in rows:
        result.setdefault((row.provider, row.model), Health(row.health))
    return result


class DatabaseAttemptObserver:
    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        run: PredictionRun,
        policy: PredictionPolicy,
    ) -> None:
        self.factory, self.run, self.policy = factory, run, policy

    async def reserve(self, config: ModelSpec, purpose: str) -> str:
        now = datetime.now(UTC)
        day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        async with self.factory() as session, session.begin():
            # One lock for all models/roles; counts include physical retries and repairs.
            await session.execute(text("SELECT pg_advisory_xact_lock(707001)"))
            total = (
                await session.scalar(
                    select(func.count())
                    .select_from(LLMCallAttempt)
                    .where(
                        LLMCallAttempt.started_at >= day,
                    )
                )
            ) or 0
            challenger = (
                await session.scalar(
                    select(func.count())
                    .select_from(LLMCallAttempt)
                    .where(
                        LLMCallAttempt.started_at >= day,
                        LLMCallAttempt.task_type == "prediction_challenger",
                    )
                )
            ) or 0
            if total >= self.policy.max_calls_per_day or (
                self.run.role == "CHALLENGER"
                and challenger >= self.policy.max_challenger_calls_per_day
            ):
                raise LLMError("daily_budget_exceeded")
            number = (
                (
                    await session.scalar(
                        select(func.max(LLMCallAttempt.attempt_number)).where(
                            LLMCallAttempt.prediction_run_id == self.run.id,
                        )
                    )
                )
                or 0
            ) + 1
            attempt = LLMCallAttempt(
                prediction_run_id=self.run.id,
                attempt_number=number,
                task_type=self.run.task_type,
                provider=config.provider,
                model=config.model,
                purpose=purpose,
                health=Health.HEALTHY.value,
                started_at=now,
            )
            session.add(attempt)
            await session.flush()
            return str(attempt.id)

    async def finish(self, attempt: str, result: LLMResult | None, error: LLMError | None) -> None:
        now = datetime.now(UTC)
        async with self.factory() as session, session.begin():
            row = await session.get(LLMCallAttempt, uuid.UUID(attempt))
            assert row is not None
            row.finished_at = now
            row.latency_ms = int((now - row.started_at).total_seconds() * 1000)
            if error:
                row.error_code, row.status_code = error.code, error.status_code
                row.health = (
                    Health.RATE_LIMITED.value
                    if error.code == "rate_limit"
                    else Health.UNAVAILABLE.value
                    if error.code == "auth"
                    else Health.DEGRADED.value
                )
            elif result:
                row.actual_model, row.provider_request_id = result.model, result.request_id
                row.input_tokens, row.output_tokens = result.input_tokens, result.output_tokens
                row.finish_reason = result.finish_reason
                row.raw_response_reference, row.error_code = (
                    result.raw_response_reference,
                    result.error_code,
                )
                row.status_code = result.status_code
                row.health = Health.DEGRADED.value if result.error_code else Health.HEALTHY.value
            # MOCK telemetry remains distinguishable, never counted as an external request.
            if row.provider != "mock":
                ledger = ExternalApiRequest(
                    provider=row.provider,
                    endpoint_category=row.task_type,
                    fixture_id=self.run.fixture_id,
                    started_at=row.started_at,
                    duration_ms=row.latency_ms,
                    status_code=row.status_code,
                    cache_hit=False,
                    priority="P3" if self.run.role == "CHALLENGER" else "P1",
                    degradation_mode="NORMAL",
                    error_class=row.error_code,
                    estimated_cost=1,
                    actual_cost=1,
                )
                session.add(ledger)
                await session.flush()
                row.external_request_id = ledger.id
