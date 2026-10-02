from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sports_intelligence.collectors.locks import CoalesceLockManager
from sports_intelligence.collectors.quota import QuotaManager, QuotaUnavailableError
from sports_intelligence.core.config import Settings
from sports_intelligence.core.phases import Priority
from sports_intelligence.db.models import (
    CandidateSettlement,
    Fixture,
    FixtureResult,
    MarketPrediction,
    PredictionRun,
    PredictionSettlement,
    ProviderEntityId,
    RankedCandidate,
)
from sports_intelligence.db.repositories.discovery import store_raw_evidence_with_payload_id
from sports_intelligence.evaluation.settlement import (
    Outcome,
    ResultObservation,
    ResultStatus,
    fixed_return,
    settle,
)
from sports_intelligence.predictions.contracts import MARKETS, Selection
from sports_intelligence.providers.base import SportsDataProvider
from sports_intelligence.providers.errors import RETRYABLE_PROVIDER_ERRORS, ProviderMappingError

TERMINAL = (ResultStatus.FINAL.value, ResultStatus.CANCELLED.value, ResultStatus.ABANDONED.value)


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False
        ).encode()
    ).hexdigest()


def latest_results_query(cutoff: datetime | None = None) -> Select[tuple[uuid.UUID]]:
    query = select(FixtureResult.id).distinct(FixtureResult.fixture_id)
    if cutoff is not None:
        query = query.where(FixtureResult.observed_at <= cutoff, FixtureResult.created_at <= cutoff)
    return query.order_by(FixtureResult.fixture_id, FixtureResult.version.desc())


async def persist_result(
    session: AsyncSession,
    fixture_id: uuid.UUID,
    provider: str,
    result: ResultObservation,
    payload_id: uuid.UUID | None = None,
) -> tuple[FixtureResult, bool]:
    result = ResultObservation.model_validate(result.model_dump())
    # Fixture row serializes versions even before the first result exists.
    fixture = await session.scalar(
        select(Fixture).where(Fixture.id == fixture_id).with_for_update()
    )
    if fixture is None:
        raise ProviderMappingError("unknown canonical fixture")
    if result.provider_home_team_id is not None:
        team_rows = (
            await session.execute(
                select(ProviderEntityId.external_id, ProviderEntityId.internal_entity_id).where(
                    ProviderEntityId.provider == provider,
                    ProviderEntityId.entity_type == "team",
                    ProviderEntityId.external_id.in_(
                        [str(result.provider_home_team_id), str(result.provider_away_team_id)]
                    ),
                )
            )
        ).all()
        teams = {external: internal for external, internal in team_rows}
        if (
            teams.get(str(result.provider_home_team_id)) != fixture.home_team_id
            or teams.get(str(result.provider_away_team_id)) != fixture.away_team_id
        ):
            raise ProviderMappingError("result team identity mismatch")
    if result.observed_at < fixture.kickoff_at and result.status in (
        ResultStatus.FINAL,
        ResultStatus.AFTER_EXTRA_TIME,
        ResultStatus.AFTER_PENALTIES,
    ):
        raise ProviderMappingError("completed result observed before kickoff")
    prior = await session.scalar(
        select(FixtureResult)
        .where(FixtureResult.fixture_id == fixture_id)
        .order_by(FixtureResult.version.desc())
        .limit(1)
    )
    data = result.model_dump(mode="json")
    identity = digest(
        {"provider": provider, "result": {k: v for k, v in data.items() if k != "observed_at"}}
    )
    if prior:
        if prior.provider != provider:
            raise ProviderMappingError("conflicting result authority")
        if prior.source_identity == identity:
            return prior, False
        if result.observed_at <= prior.observed_at:
            raise ProviderMappingError("out-of-order result correction")
    record = FixtureResult(
        fixture_id=fixture_id,
        provider=provider,
        provider_fixture_id=str(result.provider_fixture_id),
        status=result.status.value,
        regulation_home=result.regulation_home,
        regulation_away=result.regulation_away,
        extra_time_home=result.extra_time_home,
        extra_time_away=result.extra_time_away,
        penalties_home=result.penalties_home,
        penalties_away=result.penalties_away,
        observed_at=result.observed_at,
        version=prior.version + 1 if prior else 1,
        source_identity=identity,
        normalized_jsonb=data,
        raw_payload_id=payload_id,
        supersedes_id=prior.id if prior else None,
    )
    session.add(record)
    await session.flush()
    return record, True


async def settle_result(
    session: AsyncSession, result_id: uuid.UUID, version: str = "regulation_v1"
) -> int:
    record = await session.scalar(
        select(FixtureResult).where(FixtureResult.id == result_id).with_for_update()
    )
    if record is None:
        raise ValueError("unknown result")
    result = ResultObservation.model_validate(record.normalized_jsonb)
    predictions = list(
        (
            await session.scalars(
                select(MarketPrediction)
                .join(PredictionRun, PredictionRun.id == MarketPrediction.prediction_run_id)
                .where(
                    PredictionRun.fixture_id == record.fixture_id,
                    PredictionRun.status == "SUCCEEDED",
                )
            )
        ).all()
    )
    candidates = {
        c.market_prediction_id: c
        for c in (
            await session.scalars(
                select(RankedCandidate)
                .join(PredictionRun, PredictionRun.id == RankedCandidate.prediction_run_id)
                .where(
                    PredictionRun.fixture_id == record.fixture_id,
                    RankedCandidate.displayed.is_(True),
                )
            )
        ).all()
    }
    count = 0
    for prediction in predictions:
        if prediction.market != MARKETS[Selection(prediction.selection)]:
            raise ValueError("market/selection mismatch")
        outcome = settle(Selection(prediction.selection), result, version)
        sid = await session.scalar(
            pg_insert(PredictionSettlement)
            .values(
                id=uuid.uuid4(),
                market_prediction_id=prediction.id,
                fixture_result_id=record.id,
                settlement_version=version,
                outcome=outcome.value,
                reason=result.status.value,
            )
            .on_conflict_do_nothing(constraint="uq_prediction_settlements_identity")
            .returning(PredictionSettlement.id)
        )
        if sid is None:
            continue
        count += int(outcome != Outcome.UNSETTLED)
        candidate = candidates.get(prediction.id)
        if candidate:
            if candidate.captured_odds is None:
                raise ValueError("displayed candidate lacks captured odds")
            session.add(
                CandidateSettlement(
                    ranked_candidate_id=candidate.id,
                    prediction_settlement_id=sid,
                    net_return=fixed_return(outcome, candidate.captured_odds),
                    stake=1,
                )
            )
    await session.flush()
    return count


async def unresolved_date(
    session: AsyncSession,
    provider: str,
    day: date,
    settings: Settings,
    now: datetime,
    force: bool = False,
) -> dict[int, uuid.UUID]:
    start = datetime.combine(day, datetime.min.time(), UTC)
    query = (
        select(ProviderEntityId.external_id, Fixture.id)
        .join(Fixture, Fixture.id == ProviderEntityId.internal_entity_id)
        .where(
            ProviderEntityId.provider == provider,
            ProviderEntityId.entity_type == "fixture",
            Fixture.kickoff_at >= start,
            Fixture.kickoff_at < start + timedelta(days=1),
            Fixture.kickoff_at
            <= now
            - timedelta(
                minutes=settings.result_expected_finish_minutes + settings.result_grace_minutes
            ),
        )
    )
    if not force:
        confirmed = select(FixtureResult.fixture_id).where(
            FixtureResult.id.in_(latest_results_query()),
            (
                (FixtureResult.status.in_(TERMINAL))
                | (
                    (
                        FixtureResult.status.in_(
                            [
                                ResultStatus.AFTER_EXTRA_TIME.value,
                                ResultStatus.AFTER_PENALTIES.value,
                            ]
                        )
                    )
                    & FixtureResult.regulation_home.is_not(None)
                )
            ),
        )
        query = query.where(Fixture.id.not_in(confirmed))
    try:
        return {int(external): fid for external, fid in (await session.execute(query)).all()}
    except ValueError as exc:
        raise ProviderMappingError("invalid provider fixture mapping") from exc


def retry_delay(exc: BaseException, attempt: int, now: datetime) -> float | None:
    """Respect bounded Retry-After. Longer waits defer to a later scan, never retry early."""
    import math
    from email.utils import parsedate_to_datetime

    header = (getattr(exc, "quota_headers", None) or {}).get("retry-after")
    delay = float(min(30, 2 ** (attempt + 1)))
    if header:
        try:
            required = float(header)
        except ValueError:
            try:
                required = (parsedate_to_datetime(header) - now).total_seconds()
            except (TypeError, ValueError):
                return None
        if not math.isfinite(required):
            return None
        delay = max(delay, required)
    return delay if delay <= 30 else None


async def collect_date(
    *,
    factory: async_sessionmaker[AsyncSession],
    provider: SportsDataProvider,
    quota: QuotaManager,
    locks: CoalesceLockManager,
    settings: Settings,
    day: date,
    now: datetime | None = None,
    force: bool = False,
) -> dict[str, int]:
    now = now or datetime.now(UTC)
    name = provider.capabilities.provider
    if not provider.capabilities.supports_results_by_date:
        raise ProviderMappingError("provider has no date result capability")
    key = f"m8:results:{name}:{day}:{'correction' if force else 'scan'}"
    async with factory() as session:
        pending = await unresolved_date(session, name, day, settings, now, force)
    if not pending:
        return {"observed": 0, "created": 0, "settled": 0}
    lock = await locks.acquire(key=key)
    if lock is None:
        # Never bypass a winner to issue another external request.
        return {"observed": 0, "created": 0, "settled": 0}
    try:
        if not force and await locks.fetch_result(key):
            return {"observed": 0, "created": 0, "settled": 0}
        async with factory() as session:
            pending = await unresolved_date(session, name, day, settings, now, force)
        if not pending:
            return {"observed": 0, "created": 0, "settled": 0}
        batch = None
        for attempt in range(settings.result_retry_limit + 1):
            decision = await quota.reserve(provider=name, priority=Priority.P0)
            if decision.denied:
                raise QuotaUnavailableError("result quota denied", decision=decision)
            started = datetime.now(UTC)
            try:
                batch = await provider.get_results_by_date(day)
            except Exception as exc:
                await quota.record_failure(
                    provider=name,
                    endpoint_category="results",
                    started_at=started,
                    exc=exc,
                    headers=getattr(exc, "quota_headers", None),
                    priority=Priority.P0,
                )
                if (
                    not isinstance(exc, RETRYABLE_PROVIDER_ERRORS)
                    or attempt >= settings.result_retry_limit
                ):
                    raise
                delay = retry_delay(exc, attempt, datetime.now(UTC))
                if delay is None:
                    raise
                await asyncio.sleep(delay)
            else:
                await quota.record_success(
                    provider=name,
                    endpoint_category="results",
                    started_at=started,
                    finished_at=datetime.now(UTC),
                    headers=batch.rate_headers,
                    priority=Priority.P0,
                )
                break
        if batch is None or batch.provider != name:
            raise ProviderMappingError("result authority mismatch")
        async with factory() as session, session.begin():
            _, payload_id = await store_raw_evidence_with_payload_id(
                session,
                name,
                "results",
                f"{name}:results:{day}",
                digest(batch.raw_payload),
                batch.raw_payload,
                batch.retrieved_at,
            )
        created = settled = observed = 0
        async with factory() as session, session.begin():
            for observation in batch.results:
                fixture_id = pending.get(observation.provider_fixture_id)
                if fixture_id is None:
                    continue  # Untracked provider fixtures are outside requested population.
                observed += 1
                record, fresh = await persist_result(
                    session, fixture_id, name, observation, payload_id
                )
                created += fresh
                settled += await settle_result(session, record.id)
        await locks.publish_result(
            key, "confirmed_date_pass", timedelta(seconds=settings.result_scan_interval_seconds)
        )
        return {"observed": observed, "created": created, "settled": settled}
    finally:
        await locks.release(lock)


async def settle_pending(factory: async_sessionmaker[AsyncSession]) -> int:
    """Only latest results with missing settlements; bounded pages, no completed work rescans."""
    count = 0
    exists_settlement = (
        select(PredictionSettlement.id)
        .where(
            PredictionSettlement.market_prediction_id == MarketPrediction.id,
            PredictionSettlement.fixture_result_id == FixtureResult.id,
            PredictionSettlement.settlement_version == "regulation_v1",
        )
        .correlate(MarketPrediction, FixtureResult)
        .exists()
    )
    missing = (
        select(MarketPrediction.id)
        .join(PredictionRun, PredictionRun.id == MarketPrediction.prediction_run_id)
        .where(
            PredictionRun.fixture_id == FixtureResult.fixture_id,
            PredictionRun.status == "SUCCEEDED",
            ~exists_settlement,
        )
        .correlate(FixtureResult)
        .exists()
    )
    while True:
        async with factory() as session:
            ids = list(
                (
                    await session.scalars(
                        select(FixtureResult.id)
                        .where(FixtureResult.id.in_(latest_results_query()), missing)
                        .order_by(FixtureResult.id)
                        .limit(200)
                    )
                ).all()
            )
        if not ids:
            return count
        for rid in ids:
            async with factory() as session, session.begin():
                count += await settle_result(session, rid)
