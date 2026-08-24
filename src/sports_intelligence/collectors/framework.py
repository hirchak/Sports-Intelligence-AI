from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sports_intelligence.collectors.freshness import FreshnessPolicy
from sports_intelligence.collectors.locks import CoalesceLockManager
from sports_intelligence.collectors.quota import QuotaManager, QuotaUnavailableError
from sports_intelligence.core.config import Settings
from sports_intelligence.core.phases import ForecastPhase, FreshnessCategory, Priority
from sports_intelligence.providers.base import SportsDataProvider
from sports_intelligence.providers.odds.base import OddsProvider


@dataclass(frozen=True)
class CollectorContext:
    provider: SportsDataProvider | OddsProvider
    quota: QuotaManager
    locks: CoalesceLockManager
    freshness: FreshnessPolicy
    session_factory: async_sessionmaker[AsyncSession]
    settings: Settings
    redis: object
    phase: ForecastPhase = ForecastPhase.MORNING

    def provider_name(self) -> str:
        return getattr(self.provider, "name", None) or type(self.provider).__name__


@dataclass(frozen=True)
class CollectorResult:
    raw_payload: dict[str, Any] | None
    normalized: dict[str, Any]


@dataclass(frozen=True)
class SnapshotRef:
    table: str
    snapshot_id: uuid.UUID
    captured_at: datetime


class Collector(Protocol):
    name: str
    category: FreshnessCategory
    priority: Priority

    def lock_key(self, **inputs: Any) -> str: ...

    async def latest_captured_at(self, session: AsyncSession, **inputs: Any) -> datetime | None: ...

    async def fetch(self, ctx: CollectorContext, **inputs: Any) -> CollectorResult: ...

    async def persist(
        self,
        ctx: CollectorContext,
        result: CollectorResult,
        captured_at: datetime,
        source_fingerprint: str,
        **inputs: Any,
    ) -> SnapshotRef: ...


# Concrete collectors may declare keyword-only inputs (e.g. league_id:
# UUID). mypy with `--strict` requires an explicit cast at the
# registration boundary; the runtime contract is identical.
def _register_collector(collector: Any) -> Any:
    _REGISTRY[collector.name] = collector
    return collector


_REGISTRY: dict[str, Collector] = {}


def register(collector: Any) -> Any:
    return _register_collector(collector)


def resolve(name: str) -> Collector:
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"unknown collector: {name!r}") from exc


async def is_fresh(
    ctx: CollectorContext,
    collector: Collector,
    inputs: dict[str, Any],
    now: datetime | None = None,
) -> tuple[bool, datetime | None]:
    async with ctx.session_factory() as session:
        captured = await collector.latest_captured_at(session, **inputs)
    now = now or datetime.now(UTC)
    if captured is None:
        return False, None
    stale = ctx.freshness.is_stale(collector.category, captured, now, ctx.phase)
    return (not stale), captured


async def run_collector(
    ctx: CollectorContext,
    name: str,
    *,
    inputs: dict[str, Any],
    now: datetime | None = None,
    on_provider_call: Callable[[], None] | None = None,
) -> SnapshotRef:
    """End-to-end orchestration: freshness → quota → coalesce-lock →
    fetch → persist → ledger. Idempotent at the (provider, key,
    freshness-window) level via Redis lock + ledger.

    Quota is acquired BEFORE any provider request: a denied decision
    never reaches the external API (spec: prevent unnecessary requests).
    """
    collector = resolve(name)
    provider_name = ctx.provider_name()
    fresh, existing_captured = await is_fresh(ctx, collector, inputs, now=now)
    if fresh and existing_captured is not None:
        return SnapshotRef(
            table=collector.name + "_snapshots",
            snapshot_id=uuid.uuid4(),
            captured_at=existing_captured,
        )

    decision = await ctx.quota.acquire(provider=provider_name, priority=collector.priority)
    if not decision.allowed:
        raise QuotaUnavailableError(f"quota denied for {name} ({decision.reason})")

    async def _do() -> CollectorResult:
        if on_provider_call is not None:
            on_provider_call()
        return await collector.fetch(ctx, **inputs)

    lock_key = collector.lock_key(**inputs)
    result = await ctx.locks.wait_or_use(key=lock_key, fetch_fresh=_do)
    if not isinstance(result, CollectorResult):
        # A waiter reuses the winner's published JSON view.
        result = CollectorResult(
            raw_payload=None,
            normalized=dict(result) if isinstance(result, dict) else {},
        )

    captured_at = datetime.now(UTC) if now is None else now
    provider_name = ctx.provider_name()
    source_fingerprint = f"{provider_name}:{name}:{lock_key}"
    started = captured_at
    persisted = await collector.persist(
        ctx,
        result,
        captured_at=captured_at,
        source_fingerprint=source_fingerprint,
        **inputs,
    )
    duration_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
    await ctx.quota.record(
        provider=provider_name,
        endpoint_category=name,
        fixture_id=str(inputs.get("fixture_id")) if inputs.get("fixture_id") is not None else None,
        league_id=str(inputs.get("league_id")) if inputs.get("league_id") is not None else None,
        started_at=started,
        duration_ms=duration_ms,
        status_code=200,
        cache_hit=False,
        headers=None,
        priority=collector.priority,
    )
    return persisted


def list_registered() -> list[str]:
    return list(_REGISTRY)
