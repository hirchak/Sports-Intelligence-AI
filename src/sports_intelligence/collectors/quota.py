from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import IntEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sports_intelligence.core.config import Settings
from sports_intelligence.core.phases import DegradationMode, Priority


class QuotaDecisionKind(IntEnum):
    ALLOWED = 0
    DENIED_LOW_PRIORITY_PAUSED = 1
    DENIED_CRITICAL_ONLY = 2
    DENIED_RESERVE_ONLY = 3
    DENIED_NO_REMAINING = 4


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


@dataclass
class _Buckets:
    daily_limit: int
    daily_remaining: int
    minute_limit: int
    minute_remaining: int


@dataclass(frozen=True)
class _ObservedBuckets:
    """Freshest daily/minute remaining for a provider, taken from DB."""

    daily_remaining: int | None
    minute_remaining: int | None
    limit_value: int


def _degradation_mode(
    *,
    daily_remaining: int | None,
    daily_limit: int,
    reserve: int,
    thresholds: tuple[int, int, int],
) -> DegradationMode:
    if daily_remaining is None:
        return DegradationMode.NORMAL
    if daily_remaining <= reserve:
        return DegradationMode.RESERVE_ONLY
    if daily_remaining <= thresholds[0]:
        return DegradationMode.CRITICAL
    if daily_remaining <= thresholds[1]:
        return DegradationMode.CONSERVE
    return DegradationMode.NORMAL


def decide(
    *,
    daily_remaining: int | None,
    daily_limit: int,
    minute_remaining: int | None,
    minute_limit: int,
    reserve: int,
    thresholds: tuple[int, int, int],
    priority: Priority,
) -> QuotaDecision:
    """Pure-function quota decision. Deterministic and unit-testable."""
    mode = _degradation_mode(
        daily_remaining=daily_remaining,
        daily_limit=daily_limit,
        reserve=reserve,
        thresholds=thresholds,
    )

    if minute_remaining is not None and minute_remaining <= 0:
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

    if mode == DegradationMode.CRITICAL and priority == Priority.P3:
        return QuotaDecision(
            allowed=False,
            mode=mode,
            kind=QuotaDecisionKind.DENIED_LOW_PRIORITY_PAUSED,
            reason="critical_only_p3_paused",
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


@dataclass(frozen=True)
class QuotaHeaders:
    """Provider rate-limit headers (API-Football style + Odds API style)."""

    daily_remaining: int | None
    daily_limit: int | None
    minute_remaining: int | None


def parse_provider_headers(headers: dict[str, str] | None) -> QuotaHeaders:
    """Centralized header parser — supports API-Football + The Odds API."""
    if not headers:
        return QuotaHeaders(None, None, None)

    def _first(*keys: str) -> int | None:
        for key in keys:
            value = headers.get(key) or headers.get(key.lower()) or headers.get(key.upper())
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return None

    daily_remaining = _first("x-ratelimit-requests-remaining", "x-requests-remaining")
    daily_limit = _first("x-ratelimit-requests-limit", "x-requests-limit")
    minute_remaining = _first("x-ratelimit-minutes-remaining", "x-requests-last")
    return QuotaHeaders(
        daily_remaining=daily_remaining, daily_limit=daily_limit, minute_remaining=minute_remaining
    )


class QuotaManager:
    """Deterministic, DB-backed quota manager.

    The DB ledger (`external_api_requests` + `quota_buckets`) is the
    authoritative source of truth; this class adds a small in-process
    cache so steady-state decisions are cheap.
    """

    _clock: Callable[[], datetime]

    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    @property
    def _thresholds(self) -> tuple[int, int, int]:
        return (
            self._settings.quota_degrade_critical_remaining_pct,
            self._settings.quota_degrade_conserve_remaining_pct,
            self._settings.quota_degrade_normal_remaining_pct,
        )

    def decide(
        self, *, daily_remaining: int | None, minute_remaining: int | None, priority: Priority
    ) -> QuotaDecision:
        daily_limit = self._settings.quota_provider_daily_limit_default
        minute_limit = self._settings.quota_provider_minute_limit_default
        return decide(
            daily_remaining=daily_remaining,
            daily_limit=daily_limit,
            minute_remaining=minute_remaining,
            minute_limit=minute_limit,
            reserve=self._settings.quota_reserve_p0_calls,
            thresholds=self._thresholds,
            priority=priority,
        )

    async def acquire(self, *, provider: str, priority: Priority) -> QuotaDecision:
        async with self._session_factory() as session:
            observed = await self._observe_buckets(session, provider)
        return self.decide(
            daily_remaining=observed.daily_remaining,
            minute_remaining=observed.minute_remaining,
            priority=priority,
        )

    async def record(
        self,
        *,
        provider: str,
        endpoint_category: str,
        fixture_id: object | None,
        league_id: object | None,
        started_at: datetime,
        duration_ms: int,
        status_code: int | None,
        cache_hit: bool,
        headers: dict[str, str] | None,
        priority: Priority,
    ) -> None:
        import uuid as _uuid

        from sports_intelligence.db.models import ExternalApiRequest, QuotaBucket

        parsed = parse_provider_headers(headers)
        mode = self._mode_from_headers(parsed)

        fixture_uuid = (
            None
            if fixture_id is None
            else _uuid.UUID(str(fixture_id))
            if not isinstance(fixture_id, _uuid.UUID)
            else fixture_id
        )
        league_uuid = (
            None
            if league_id is None
            else _uuid.UUID(str(league_id))
            if not isinstance(league_id, _uuid.UUID)
            else league_id
        )

        async with self._session_factory() as session:
            session.add(
                ExternalApiRequest(
                    provider=provider,
                    endpoint_category=endpoint_category,
                    fixture_id=fixture_uuid,
                    league_id=league_uuid,
                    started_at=started_at,
                    duration_ms=duration_ms,
                    status_code=status_code,
                    cache_hit=cache_hit,
                    daily_remaining=parsed.daily_remaining,
                    minute_remaining=parsed.minute_remaining,
                    priority=priority.value,
                    degradation_mode=mode.value,
                )
            )
            if parsed.daily_remaining is not None or parsed.minute_remaining is not None:
                if parsed.daily_remaining is not None:
                    session.add(
                        QuotaBucket(
                            provider=provider,
                            window="daily",
                            limit_value=parsed.daily_limit
                            or self._settings.quota_provider_daily_limit_default,
                            remaining_value=parsed.daily_remaining,
                            observed_at=started_at,
                        )
                    )
                if parsed.minute_remaining is not None:
                    session.add(
                        QuotaBucket(
                            provider=provider,
                            window="minute",
                            limit_value=self._settings.quota_provider_minute_limit_default,
                            remaining_value=parsed.minute_remaining,
                            observed_at=started_at,
                        )
                    )
            await session.commit()

    def _mode_from_headers(self, parsed: QuotaHeaders) -> DegradationMode:
        if parsed.daily_remaining is None:
            return DegradationMode.NORMAL
        return self.decide(
            daily_remaining=parsed.daily_remaining,
            minute_remaining=parsed.minute_remaining,
            priority=Priority.P2,
        ).mode

    async def _observe_buckets(self, session: AsyncSession, provider: str) -> _ObservedBuckets:

        from sports_intelligence.db.models import QuotaBucket

        stmt = (
            select(QuotaBucket.remaining_value, QuotaBucket.limit_value, QuotaBucket.window)
            .where(QuotaBucket.provider == provider)
            .order_by(QuotaBucket.observed_at.desc())
            .limit(20)
        )
        rows = (await session.execute(stmt)).all()
        daily_remaining: int | None = None
        daily_limit: int | None = None
        minute_remaining: int | None = None
        for remaining, limit, window in rows:
            if window == "daily" and daily_remaining is None:
                daily_remaining = int(remaining)
                daily_limit = int(limit)
            elif window == "minute" and minute_remaining is None:
                minute_remaining = int(remaining)
        if daily_limit is None:
            daily_limit = self._settings.quota_provider_daily_limit_default
        return _ObservedBuckets(
            daily_remaining=daily_remaining,
            minute_remaining=minute_remaining,
            limit_value=daily_limit,
        )

    def snapshot_today(self, observed: _ObservedBuckets) -> DegradationMode:
        return self.decide(
            daily_remaining=observed.daily_remaining,
            minute_remaining=observed.minute_remaining,
            priority=Priority.P2,
        ).mode
