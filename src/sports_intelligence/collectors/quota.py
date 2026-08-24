"""Deterministic quota management + request ledger (M4/M4.1).

Semantics (review M4.1 §6/§7):

- degradation thresholds (`*_pct`) are PERCENTAGES of the actual
  provider limit (observed limit preferred, settings default fallback);
- CONSERVE pauses P3 work;
- CRITICAL additionally pauses P2 work (P0/P1 essential work preserved);
- RESERVE_ONLY protects the absolute P0 reserve budget;
- the default reserve must not swallow the whole CRITICAL band — the
  reserve check runs AFTER the percentage bands;
- reservations are concurrency-safe across workers via atomic Redis
  counters keyed by provider/window/period, supporting ESTIMATED COST
  (credits), not just request counts;
- header parsing is provider-specific: API-Football exposes daily +
  minute windows; The Odds API exposes credit remaining/used and the
  COST of the last call (`x-requests-last` is NOT minute remaining).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import IntEnum

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sports_intelligence.core.config import Settings
from sports_intelligence.core.logging import get_logger
from sports_intelligence.core.phases import DegradationMode, Priority
from sports_intelligence.db.models import ExternalApiRequest, QuotaBucket

logger = get_logger(__name__)


class QuotaDecisionKind(IntEnum):
    ALLOWED = 0
    DENIED_LOW_PRIORITY_PAUSED = 1
    DENIED_RESERVE_ONLY = 2
    DENIED_NO_REMAINING = 3
    DENIED_RESERVATION_EXHAUSTED = 4


@dataclass(frozen=True)
class QuotaDecision:
    allowed: bool
    mode: DegradationMode
    kind: QuotaDecisionKind
    reason: str
    remaining_daily: int | None
    remaining_minute: int | None

    @property
    def denied(self) -> bool:
        return not self.allowed


class QuotaUnavailableError(RuntimeError):
    """Raised when a quota decision denies an external request."""

    def __init__(self, message: str, *, decision: QuotaDecision | None = None) -> None:
        super().__init__(message)
        self.decision = decision


# ---------------------------------------------------------------------------
# Provider-specific header parsing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QuotaObservation:
    """Normalized provider rate-limit state from one response."""

    daily_remaining: int | None = None
    daily_limit: int | None = None
    minute_remaining: int | None = None
    minute_limit: int | None = None
    last_call_cost: int | None = None
    raw: dict[str, str] = field(default_factory=dict)


def _header_value(headers: dict[str, str], name: str) -> str | None:
    lowered = {k.lower(): v for k, v in headers.items()}
    value = lowered.get(name.lower())
    return value if value is not None and value != "" else None


def _int_header(headers: dict[str, str], name: str) -> int | None:
    value = _header_value(headers, name)
    if value is None:
        return None
    try:
        # Some providers send floats like "42.0".
        return int(float(value))
    except (TypeError, ValueError):
        return None


def parse_quota_headers(provider: str, headers: dict[str, str] | None) -> QuotaObservation:
    if not headers:
        return QuotaObservation()

    if provider == "api_football":
        return QuotaObservation(
            daily_remaining=_int_header(headers, "x-ratelimit-requests-remaining"),
            daily_limit=_int_header(headers, "x-ratelimit-requests-limit"),
            minute_remaining=_int_header(headers, "x-ratelimit-remaining"),
            minute_limit=_int_header(headers, "x-ratelimit-limit"),
            raw=dict(headers),
        )

    if provider in ("theoddsapi", "the_odds_api"):
        # x-requests-last is the CREDIT COST of the last call — never a
        # per-minute budget.
        return QuotaObservation(
            daily_remaining=_int_header(headers, "x-requests-remaining"),
            daily_limit=None,
            minute_remaining=None,
            minute_limit=None,
            last_call_cost=_int_header(headers, "x-requests-last"),
            raw=dict(headers),
        )

    # Unknown providers: best-effort legacy keys.
    return QuotaObservation(
        daily_remaining=_int_header(headers, "x-requests-remaining"),
        daily_limit=_int_header(headers, "x-requests-limit"),
        raw=dict(headers),
    )


# ---------------------------------------------------------------------------
# Pure deterministic decision core
# ---------------------------------------------------------------------------


def effective_reserve(daily_limit: int, reserve: int, critical_pct: int) -> int:
    """Absolute reserve clamped into the CRITICAL band.

    Keeps the configured reserve meaningful on large limits while
    guaranteeing CRITICAL stays reachable on small ones (e.g. limit 100 /
    reserve 20 / critical 10% → effective reserve 10, so remaining 11–25
    still exercises CRITICAL instead of collapsing into RESERVE_ONLY).
    """
    critical_floor = max(1, int(daily_limit * critical_pct / 100))
    return max(0, min(reserve, critical_floor))


def _degradation_mode(
    *,
    daily_remaining: int,
    daily_limit: int,
    reserve: int,
    critical_pct: int,
    conserve_pct: int,
) -> DegradationMode:
    """Percentage-based bands against the ACTUAL observed limit."""
    limit = max(daily_limit, 1)
    pct_remaining = (daily_remaining / limit) * 100.0
    if daily_remaining <= reserve:
        return DegradationMode.RESERVE_ONLY
    if pct_remaining <= critical_pct:
        return DegradationMode.CRITICAL
    if pct_remaining <= conserve_pct:
        return DegradationMode.CONSERVE
    return DegradationMode.NORMAL


def decide(
    *,
    daily_remaining: int | None,
    daily_limit: int,
    minute_remaining: int | None,
    minute_limit: int,
    reserve: int,
    critical_pct: int,
    conserve_pct: int,
    priority: Priority,
    estimated_cost: int = 1,
) -> QuotaDecision:
    """Pure-function quota decision. Deterministic and unit-testable."""
    if daily_remaining is not None:
        reserve_eff = effective_reserve(daily_limit, reserve, critical_pct)
        mode = _degradation_mode(
            daily_remaining=daily_remaining,
            daily_limit=daily_limit,
            reserve=reserve_eff,
            critical_pct=critical_pct,
            conserve_pct=conserve_pct,
        )
        # A cost larger than what remains cannot be afforded even by P0.
        if daily_remaining - estimated_cost < 0:
            return QuotaDecision(
                allowed=False,
                mode=mode,
                kind=QuotaDecisionKind.DENIED_NO_REMAINING,
                reason="insufficient_daily_budget_for_estimated_cost",
                remaining_daily=daily_remaining,
                remaining_minute=minute_remaining,
            )
        # Non-P0 work must not burn through the protected reserve.
        if (
            priority != Priority.P0
            and daily_remaining - estimated_cost < reserve_eff
            and mode is not DegradationMode.RESERVE_ONLY
        ):
            return QuotaDecision(
                allowed=False,
                mode=DegradationMode.RESERVE_ONLY,
                kind=QuotaDecisionKind.DENIED_RESERVE_ONLY,
                reason="reserve_protection",
                remaining_daily=daily_remaining,
                remaining_minute=minute_remaining,
            )
    else:
        mode = DegradationMode.NORMAL

    if minute_remaining is not None and minute_remaining - estimated_cost < 0:
        return QuotaDecision(
            allowed=False,
            mode=mode,
            kind=QuotaDecisionKind.DENIED_NO_REMAINING,
            reason="minute_budget_exhausted",
            remaining_daily=daily_remaining,
            remaining_minute=minute_remaining,
        )

    if mode == DegradationMode.RESERVE_ONLY and priority != Priority.P0:
        return QuotaDecision(
            allowed=False,
            mode=mode,
            kind=QuotaDecisionKind.DENIED_RESERVE_ONLY,
            reason="reserve_only",
            remaining_daily=daily_remaining,
            remaining_minute=minute_remaining,
        )

    if mode == DegradationMode.CRITICAL and priority in (Priority.P2, Priority.P3):
        return QuotaDecision(
            allowed=False,
            mode=mode,
            kind=QuotaDecisionKind.DENIED_LOW_PRIORITY_PAUSED,
            reason="critical_p2_p3_paused",
            remaining_daily=daily_remaining,
            remaining_minute=minute_remaining,
        )

    if mode == DegradationMode.CONSERVE and priority == Priority.P3:
        return QuotaDecision(
            allowed=False,
            mode=mode,
            kind=QuotaDecisionKind.DENIED_LOW_PRIORITY_PAUSED,
            reason="conserve_p3_paused",
            remaining_daily=daily_remaining,
            remaining_minute=minute_remaining,
        )

    return QuotaDecision(
        allowed=True,
        mode=mode,
        kind=QuotaDecisionKind.ALLOWED,
        reason="ok",
        remaining_daily=daily_remaining,
        remaining_minute=minute_remaining,
    )


# ---------------------------------------------------------------------------
# DB-backed manager with atomic Redis reservation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ObservedBuckets:
    daily_remaining: int | None
    daily_limit: int | None
    minute_remaining: int | None
    minute_limit: int | None


class QuotaManager:
    """Deterministic quota manager: DB ledger + Redis atomic reservation.

    `reserve()` must be called BEFORE the external HTTP call; it either
    atomically consumes `estimated_cost` units across workers or denies.
    `record_success()/record_failure()` persist the request-ledger row
    with real telemetry (timing, status/error class, provider headers,
    actual cost where reported).
    """

    _clock: Callable[[], datetime]

    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        redis: object | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._redis = redis
        self._clock = clock or (lambda: datetime.now(UTC))

    @property
    def _critical_pct(self) -> int:
        return self._settings.quota_degrade_critical_remaining_pct

    @property
    def _conserve_pct(self) -> int:
        return self._settings.quota_degrade_conserve_remaining_pct

    def decide(
        self,
        *,
        daily_remaining: int | None,
        minute_remaining: int | None,
        priority: Priority,
        daily_limit: int | None = None,
        estimated_cost: int = 1,
    ) -> QuotaDecision:
        limit = daily_limit or self._settings.quota_provider_daily_limit_default
        return decide(
            daily_remaining=daily_remaining,
            daily_limit=limit,
            minute_remaining=minute_remaining,
            minute_limit=self._settings.quota_provider_minute_limit_default,
            reserve=self._settings.quota_reserve_p0_calls,
            critical_pct=self._critical_pct,
            conserve_pct=self._conserve_pct,
            priority=priority,
            estimated_cost=estimated_cost,
        )

    async def _observe_buckets(self, session: AsyncSession, provider: str) -> _ObservedBuckets:
        stmt = (
            select(
                QuotaBucket.remaining_value,
                QuotaBucket.limit_value,
                QuotaBucket.window,
            )
            .where(QuotaBucket.provider == provider)
            .order_by(QuotaBucket.observed_at.desc())
            .limit(40)
        )
        rows = (await session.execute(stmt)).all()
        daily_remaining: int | None = None
        daily_limit: int | None = None
        minute_remaining: int | None = None
        minute_limit: int | None = None
        for remaining, limit, window in rows:
            if window == "daily" and daily_remaining is None:
                daily_remaining = int(remaining)
                daily_limit = int(limit)
            elif window == "minute" and minute_remaining is None:
                minute_remaining = int(remaining)
                minute_limit = int(limit)
        return _ObservedBuckets(
            daily_remaining=daily_remaining,
            daily_limit=daily_limit,
            minute_remaining=minute_remaining,
            minute_limit=minute_limit,
        )

    async def observe(self, provider: str) -> tuple[int | None, int | None, DegradationMode]:
        """Read-only view for status endpoints (no reservation)."""
        async with self._session_factory() as session:
            buckets = await self._observe_buckets(session, provider)
        decision = self.decide(
            daily_remaining=buckets.daily_remaining,
            minute_remaining=buckets.minute_remaining,
            priority=Priority.P2,
            daily_limit=buckets.daily_limit,
        )
        return buckets.daily_remaining, buckets.minute_remaining, decision.mode

    async def acquire(self, *, provider: str, priority: Priority) -> QuotaDecision:
        """Legacy read-only gate kept for compatibility."""
        async with self._session_factory() as session:
            buckets = await self._observe_buckets(session, provider)
        return self.decide(
            daily_remaining=buckets.daily_remaining,
            minute_remaining=buckets.minute_remaining,
            priority=priority,
            daily_limit=buckets.daily_limit,
        )

    async def reserve(
        self,
        *,
        provider: str,
        priority: Priority,
        estimated_cost: int = 1,
    ) -> QuotaDecision:
        """Gate + atomically consume estimated cost across workers.

        The Redis reservation is based on the provider's LATEST OBSERVED
        remaining budget minus reservations made since that observation
        (M4.2 §9) — never a fresh counter against the original full
        limit. Each INCR is atomic, so concurrent workers cannot all
        spend the last remaining units.

        Without Redis the decision falls back to the read-only path
        (unit-test / degraded mode).
        """
        async with self._session_factory() as session:
            buckets = await self._observe_buckets(session, provider)

        base_decision = self.decide(
            daily_remaining=buckets.daily_remaining,
            minute_remaining=buckets.minute_remaining,
            priority=priority,
            daily_limit=buckets.daily_limit,
        )
        if base_decision.denied:
            return base_decision

        if self._redis is None:
            return base_decision

        now = self._clock()
        day_key = f"quota:{provider}:daily:{now:%Y%m%d}"
        minute_key = f"quota:{provider}:minute:{now:%Y%m%d%H%M}"

        daily_limit = buckets.daily_limit or self._settings.quota_provider_daily_limit_default
        # Baseline = latest observed remaining; reservations since that
        # observation accumulate in the Redis counter.
        baseline_daily = (
            buckets.daily_remaining if buckets.daily_remaining is not None else daily_limit
        )
        reserve_eff = effective_reserve(
            daily_limit, self._settings.quota_reserve_p0_calls, self._critical_pct
        )
        baseline_minute = (
            buckets.minute_remaining
            if buckets.minute_remaining is not None
            else self._settings.quota_provider_minute_limit_default
        )

        incr = getattr(self._redis, "incrby", None)
        expire = getattr(self._redis, "expire", None)
        decrby = getattr(self._redis, "decrby", None)
        ttl_seconds = 2 * 24 * 3600

        if incr is None or expire is None or decrby is None:  # pragma: no cover
            return base_decision

        # Daily budget: atomically reserve; decision on the post-INCR
        # running total so concurrent callers serialize correctly.
        used_daily = int(await incr(day_key, estimated_cost))
        if used_daily == estimated_cost:
            await expire(day_key, ttl_seconds)
        current_daily = baseline_daily - used_daily
        if current_daily < 0:
            await decrby(day_key, estimated_cost)
            return QuotaDecision(
                allowed=False,
                mode=base_decision.mode,
                kind=QuotaDecisionKind.DENIED_NO_REMAINING,
                reason="insufficient_daily_budget_for_estimated_cost",
                remaining_daily=buckets.daily_remaining,
                remaining_minute=buckets.minute_remaining,
            )
        if priority != Priority.P0 and current_daily < reserve_eff:
            await decrby(day_key, estimated_cost)
            return QuotaDecision(
                allowed=False,
                mode=DegradationMode.RESERVE_ONLY,
                kind=QuotaDecisionKind.DENIED_RESERVE_ONLY,
                reason="reserve_protection",
                remaining_daily=buckets.daily_remaining,
                remaining_minute=buckets.minute_remaining,
            )

        # Minute budget.
        used_minute = int(await incr(minute_key, estimated_cost))
        if used_minute == estimated_cost:
            await expire(minute_key, 120)
        current_minute = baseline_minute - used_minute
        if current_minute < 0:
            await decrby(minute_key, estimated_cost)
            await decrby(day_key, estimated_cost)
            return QuotaDecision(
                allowed=False,
                mode=base_decision.mode,
                kind=QuotaDecisionKind.DENIED_NO_REMAINING,
                reason="minute_budget_exhausted",
                remaining_daily=buckets.daily_remaining,
                remaining_minute=buckets.minute_remaining,
            )

        return base_decision

    async def _persist_ledger_row(
        self,
        *,
        provider: str,
        endpoint_category: str,
        fixture_id: uuid.UUID | None,
        league_id: uuid.UUID | None,
        started_at: datetime,
        finished_at: datetime,
        status_code: int | None,
        error_class: str | None,
        observation: QuotaObservation,
        cache_hit: bool,
        priority: Priority,
        estimated_cost: int,
        degradation_mode: DegradationMode,
    ) -> None:
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)

        def _bucket(window: str, remaining: int | None, limit: int | None) -> QuotaBucket | None:
            if remaining is None:
                return None
            return QuotaBucket(
                provider=provider,
                window=window,
                limit_value=limit or self._settings.quota_provider_daily_limit_default,
                remaining_value=int(remaining),
                observed_at=started_at,
            )

        async with self._session_factory() as session:
            session.add(
                ExternalApiRequest(
                    provider=provider,
                    endpoint_category=endpoint_category,
                    fixture_id=fixture_id,
                    league_id=league_id,
                    started_at=started_at,
                    duration_ms=duration_ms,
                    status_code=status_code,
                    cache_hit=cache_hit,
                    daily_remaining=observation.daily_remaining,
                    minute_remaining=observation.minute_remaining,
                    priority=priority.value,
                    degradation_mode=degradation_mode.value,
                    error_class=error_class[:128] if error_class else None,
                    estimated_cost=estimated_cost,
                    actual_cost=observation.last_call_cost,
                )
            )
            daily_bucket = _bucket("daily", observation.daily_remaining, observation.daily_limit)
            if daily_bucket is not None:
                stmt = (
                    pg_insert(QuotaBucket)
                    .values(
                        provider=daily_bucket.provider,
                        window=daily_bucket.window,
                        limit_value=daily_bucket.limit_value,
                        remaining_value=daily_bucket.remaining_value,
                        observed_at=daily_bucket.observed_at,
                    )
                    .on_conflict_do_nothing()
                )
                await session.execute(stmt)
            minute_bucket = _bucket(
                "minute", observation.minute_remaining, observation.minute_limit
            )
            if minute_bucket is not None:
                stmt = (
                    pg_insert(QuotaBucket)
                    .values(
                        provider=minute_bucket.provider,
                        window=minute_bucket.window,
                        limit_value=minute_bucket.limit_value,
                        remaining_value=minute_bucket.remaining_value,
                        observed_at=minute_bucket.observed_at,
                    )
                    .on_conflict_do_nothing()
                )
                await session.execute(stmt)
            await session.commit()

    async def record_success(
        self,
        *,
        provider: str,
        endpoint_category: str,
        started_at: datetime,
        finished_at: datetime,
        headers: dict[str, str] | None,
        priority: Priority,
        estimated_cost: int = 1,
        fixture_id: uuid.UUID | str | None = None,
        league_id: uuid.UUID | str | None = None,
    ) -> None:
        observation = parse_quota_headers(provider, headers)
        mode = self.decide(
            daily_remaining=observation.daily_remaining,
            minute_remaining=observation.minute_remaining,
            priority=Priority.P2,
            daily_limit=observation.daily_limit,
        ).mode
        await self._persist_ledger_row(
            provider=provider,
            endpoint_category=endpoint_category,
            fixture_id=_as_uuid(fixture_id),
            league_id=_as_uuid(league_id),
            started_at=started_at,
            finished_at=finished_at,
            status_code=200,
            error_class=None,
            observation=observation,
            cache_hit=False,
            priority=priority,
            estimated_cost=estimated_cost,
            degradation_mode=mode,
        )

    async def record_failure(
        self,
        *,
        provider: str,
        endpoint_category: str,
        started_at: datetime,
        exc: BaseException,
        headers: dict[str, str] | None = None,
        priority: Priority,
        estimated_cost: int = 1,
        fixture_id: uuid.UUID | str | None = None,
        league_id: uuid.UUID | str | None = None,
    ) -> None:
        observation = parse_quota_headers(provider, headers)
        status_code = getattr(exc, "status_code", None)
        error_class = type(exc).__name__
        mode = self.decide(
            daily_remaining=observation.daily_remaining,
            minute_remaining=observation.minute_remaining,
            priority=Priority.P2,
            daily_limit=observation.daily_limit,
        ).mode
        try:
            await self._persist_ledger_row(
                provider=provider,
                endpoint_category=endpoint_category,
                fixture_id=_as_uuid(fixture_id),
                league_id=_as_uuid(league_id),
                started_at=started_at,
                finished_at=datetime.now(UTC),
                status_code=status_code if isinstance(status_code, int) else None,
                error_class=error_class,
                observation=observation,
                cache_hit=False,
                priority=priority,
                estimated_cost=estimated_cost,
                degradation_mode=mode,
            )
        except Exception:  # noqa: BLE001 — telemetry must never mask the original error
            logger.warning("failed to persist failure ledger row", exc_info=True)

    # Backwards-compatible alias used by older call sites.
    async def record(
        self,
        *,
        provider: str,
        endpoint_category: str,
        fixture_id: uuid.UUID | str | None,
        league_id: uuid.UUID | str | None,
        started_at: datetime,
        duration_ms: int,
        status_code: int | None,
        cache_hit: bool,
        headers: dict[str, str] | None,
        priority: Priority,
        estimated_cost: int = 1,
        actual_cost: int | None = None,
    ) -> None:
        observation = parse_quota_headers(provider, headers)
        if actual_cost is not None:
            observation = QuotaObservation(
                daily_remaining=observation.daily_remaining,
                daily_limit=observation.daily_limit,
                minute_remaining=observation.minute_remaining,
                minute_limit=observation.minute_limit,
                last_call_cost=actual_cost,
                raw=observation.raw,
            )
        mode = self.decide(
            daily_remaining=observation.daily_remaining,
            minute_remaining=observation.minute_remaining,
            priority=Priority.P2,
            daily_limit=observation.daily_limit,
        ).mode
        finished_at = datetime.now(UTC)
        await self._persist_ledger_row(
            provider=provider,
            endpoint_category=endpoint_category,
            fixture_id=_as_uuid(fixture_id),
            league_id=_as_uuid(league_id),
            started_at=started_at,
            finished_at=finished_at,
            status_code=status_code,
            error_class=None,
            observation=observation,
            cache_hit=cache_hit,
            priority=priority,
            estimated_cost=estimated_cost,
            degradation_mode=mode,
        )


def _as_uuid(value: uuid.UUID | str | None) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None
