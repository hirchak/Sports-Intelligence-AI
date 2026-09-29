"""Collector orchestration framework (M4.1 redesign).

Execution contract per collector run:

1. fast freshness check → hit returns the REAL persisted snapshot id;
2. acquire the coalescing lock — a budget/correctness boundary:
   a caller that cannot acquire NEVER falls back to its own provider
   call; it either reuses the winner's published result or fails loud;
3. winner re-checks freshness under the lock (double-check);
4. quota reservation (atomic across workers, estimated-cost aware);
5. provider fetch with real telemetry boundaries (started_at BEFORE the
   network operation, duration covering it);
6. raw evidence persistence (content-deduped payload + observation row)
   and normalized snapshot persistence linked via payload_id;
7. request-ledger row with status/error class/provider headers/cost;
8. publish the persisted SnapshotRefs so waiters reuse REAL ids without
   calling the provider, persisting duplicates or writing ledger rows.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sports_intelligence.collectors.freshness import FreshnessPolicy
from sports_intelligence.collectors.locks import CoalesceLockManager
from sports_intelligence.collectors.quota import (
    QuotaManager,
    QuotaUnavailableError,
)
from sports_intelligence.core.config import Settings
from sports_intelligence.core.logging import get_logger
from sports_intelligence.core.phases import ForecastPhase, FreshnessCategory, Priority
from sports_intelligence.db.repositories.discovery import store_raw_evidence
from sports_intelligence.providers.base import OddsProvider, SportsDataProvider
from sports_intelligence.providers.search.base import SearchProvider

logger = get_logger(__name__)


@dataclass(frozen=True)
class CollectorContext:
    provider: SportsDataProvider | OddsProvider | SearchProvider
    quota: QuotaManager
    locks: CoalesceLockManager
    freshness: FreshnessPolicy
    session_factory: async_sessionmaker[AsyncSession]
    settings: Settings
    redis: object
    phase: ForecastPhase = ForecastPhase.MORNING

    def provider_name(self) -> str:
        name = getattr(self.provider, "name", None)
        if isinstance(name, str) and name:
            return name
        capabilities = getattr(self.provider, "capabilities", None)
        caps_provider = getattr(capabilities, "provider", None)
        if isinstance(caps_provider, str) and caps_provider:
            return caps_provider
        return type(self.provider).__name__


@dataclass(frozen=True)
class CollectorResult:
    raw_payload: dict[str, Any] | None
    normalized: dict[str, Any]
    rate_headers: dict[str, str] | None = None
    retrieved_at: datetime | None = None


@dataclass(frozen=True)
class SnapshotRef:
    table: str
    snapshot_id: uuid.UUID
    captured_at: datetime
    team_id: uuid.UUID | None = None


class LockContendedError(RuntimeError):
    """The coalescing lock was busy and no winner result appeared in time.

    Quota-sensitive external requests must never bypass the lock.
    """


class Collector(Protocol):
    name: str
    category: FreshnessCategory
    priority: Priority

    def lock_key(self, **inputs: Any) -> str: ...

    async def latest_snapshot(
        self, session: AsyncSession, **inputs: Any
    ) -> tuple[datetime | None, uuid.UUID | None]: ...

    async def fetch(self, ctx: CollectorContext, **inputs: Any) -> CollectorResult: ...

    async def persist(
        self,
        ctx: CollectorContext,
        result: CollectorResult,
        *,
        captured_at: datetime,
        source_fingerprint: str,
        payload_id: uuid.UUID | None,
        **inputs: Any,
    ) -> tuple[SnapshotRef, ...]: ...


async def collector_refresh_due(
    collector: Collector,
    ctx: CollectorContext,
    inputs: dict[str, Any],
    captured_at: datetime | None,
    now: datetime,
) -> bool:
    """Ask the collector whether a refresh is due.

    Collectors may override the default TTL policy (lineups use the
    state/window policy, never the generic 24h TTL).
    """
    override = getattr(collector, "refresh_due", None)
    if override is not None:
        due = await override(ctx, inputs, captured_at=captured_at, now=now)
        return bool(due)
    if captured_at is None:
        return True
    return ctx.freshness.is_stale(collector.category, captured_at, now, ctx.phase)


_REGISTRY: dict[str, Collector] = {}


def register(collector: Any) -> Any:
    """Register a collector. Concrete collectors declare keyword-only
    inputs (mypy-strict Protocol variance requires the untyped boundary)."""
    _REGISTRY[collector.name] = collector
    return collector


def resolve(name: str) -> Collector:
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"unknown collector: {name!r}") from exc


async def latest_snapshot_state(
    ctx: CollectorContext,
    collector: Collector,
    inputs: dict[str, Any],
) -> tuple[datetime | None, uuid.UUID | None]:
    async with ctx.session_factory() as session:
        return await collector.latest_snapshot(session, **inputs)


def _canonical_params(inputs: dict[str, Any]) -> dict[str, str]:
    return {key: str(value)[:64] for key, value in sorted(inputs.items()) if value is not None}


def _payload_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _refs_to_json(refs: list[SnapshotRef]) -> str:
    return json.dumps(
        [
            {
                "table": ref.table,
                "snapshot_id": str(ref.snapshot_id),
                "captured_at": ref.captured_at.isoformat(),
                "team_id": str(ref.team_id) if ref.team_id else None,
            }
            for ref in refs
        ],
        ensure_ascii=False,
    )


def _refs_from_json(raw: str) -> list[SnapshotRef]:
    try:
        items = json.loads(raw)
    except (TypeError, ValueError):
        return []
    refs: list[SnapshotRef] = []
    if not isinstance(items, list):
        return refs
    for item in items:
        try:
            refs.append(
                SnapshotRef(
                    table=str(item["table"]),
                    snapshot_id=uuid.UUID(str(item["snapshot_id"])),
                    captured_at=datetime.fromisoformat(str(item["captured_at"])),
                    team_id=(uuid.UUID(str(item["team_id"])) if item.get("team_id") else None),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return refs


def _select_ref(refs: list[SnapshotRef], inputs: dict[str, Any]) -> SnapshotRef:
    """Pick the ref bound to the requesting team when applicable."""
    team_input = inputs.get("team_id")
    if team_input is not None:
        wanted = str(team_input)
        for ref in refs:
            if ref.team_id is not None and str(ref.team_id) == wanted:
                return ref
    if len(refs) == 1:
        return refs[0]
    # Multi-ref without a team binding: newest wins deterministically.
    return sorted(refs, key=lambda r: r.captured_at)[-1]


async def run_collector(
    ctx: CollectorContext,
    name: str,
    *,
    inputs: dict[str, Any],
    now: datetime | None = None,
    on_provider_call: Callable[[], None] | None = None,
    estimated_cost: int = 1,
    max_wait_seconds: float | None = None,
) -> SnapshotRef:
    collector = resolve(name)
    provider_name = ctx.provider_name()
    now = now or datetime.now(UTC)

    # 1. Fast freshness check (read-only).
    captured, snapshot_id = await latest_snapshot_state(ctx, collector, inputs)
    if (
        captured is not None
        and snapshot_id is not None
        and not await collector_refresh_due(collector, ctx, inputs, captured, now)
    ):
        return SnapshotRef(
            table=_table_for(collector),
            snapshot_id=snapshot_id,
            captured_at=captured,
            team_id=_uuid_or_none(inputs.get("team_id")),
        )

    # 2. Coalescing lock — correctness/budget boundary, never bypassed.
    lock_key = collector.lock_key(**inputs)
    lock = await ctx.locks.acquire(key=lock_key)
    if lock is None:
        published_raw = await ctx.locks.wait_for_published(
            lock_key,
            max_wait=max_wait_seconds or ctx.settings.redis_lock_acquire_timeout_seconds,
        )
        if published_raw is not None:
            refs = _refs_from_json(published_raw)
            if refs:
                return _select_ref(refs, inputs)
        raise LockContendedError(
            f"collector {name} lock contended without a published result: {lock_key}"
        )

    try:
        # 3. Winner double-check under the lock (same `now` semantics as
        # the fast check — deterministic window/TTL decisions).
        captured, snapshot_id = await latest_snapshot_state(ctx, collector, inputs)
        if (
            captured is not None
            and snapshot_id is not None
            and not await collector_refresh_due(collector, ctx, inputs, captured, now)
        ):
            ref = SnapshotRef(
                table=_table_for(collector),
                snapshot_id=snapshot_id,
                captured_at=captured,
                team_id=_uuid_or_none(inputs.get("team_id")),
            )
            await ctx.locks.publish_result(lock_key, _refs_to_json([ref]), _ttl(ctx))
            return ref

        owns_quota = getattr(collector, "owns_quota", False)

        # 4. Quota reservation BEFORE external work (skipped if collector owns quota).
        if not owns_quota:
            decision = await ctx.quota.reserve(
                provider=provider_name,
                priority=collector.priority,
                estimated_cost=estimated_cost,
            )
            if decision.denied:
                raise QuotaUnavailableError(
                    f"quota denied for {name} ({decision.reason})", decision=decision
                )

        # 5. Provider fetch — telemetry starts BEFORE the network op.
        started_at = datetime.now(UTC)

        async def _do() -> CollectorResult:
            if on_provider_call is not None:
                on_provider_call()
            return await collector.fetch(ctx, **inputs)

        try:
            result = await _do()
        except Exception as exc:
            if not owns_quota:
                await ctx.quota.record_failure(
                    provider=provider_name,
                    endpoint_category=name,
                    started_at=started_at,
                    exc=exc,
                    headers=getattr(exc, "quota_headers", None),
                    priority=collector.priority,
                    estimated_cost=estimated_cost,
                    fixture_id=inputs.get("fixture_id"),
                    league_id=inputs.get("league_id"),
                )
            raise

        finished_at = datetime.now(UTC)

        # 6. Raw evidence first (content dedup + observation row),
        # committed BEFORE the snapshot persists — collectors open their
        # own sessions and the payload_id FK must observe a committed
        # raw_provider_payloads row.
        fingerprint_params = _canonical_params(inputs)
        fingerprint = f"{provider_name}:{name}:{json.dumps(fingerprint_params, sort_keys=True)}"
        source_fingerprint = f"{provider_name}:{name}:norm.v1:{fingerprint}"
        raw_payload = result.raw_payload or {"normalized": result.normalized}
        payload_hash = _payload_sha256(raw_payload)

        async with ctx.session_factory() as session, session.begin():
            content_created = await store_raw_evidence(
                session,
                provider_name,
                name,
                fingerprint,
                payload_hash,
                raw_payload,
                result.retrieved_at or finished_at,
            )
            stmt_payload_id = (
                await session.execute(_payload_id_stmt(provider_name, name, payload_hash))
            ).scalar_one()

        logger.debug(
            "collector stored evidence",
            extra={
                "collector": name,
                "content_created": content_created,
            },
        )

        # 6b. Normalized snapshots linked to the committed payload row.
        refs = list(
            await collector.persist(
                ctx,
                result,
                captured_at=result.retrieved_at or finished_at,
                source_fingerprint=source_fingerprint,
                payload_id=stmt_payload_id,
                **inputs,
            )
        )

        # 7. Request-ledger row with real telemetry (skipped if collector owns per-request quota).
        if not owns_quota:
            await ctx.quota.record_success(
                provider=provider_name,
                endpoint_category=name,
                started_at=started_at,
                finished_at=finished_at,
                headers=result.rate_headers,
                priority=collector.priority,
                estimated_cost=estimated_cost,
                fixture_id=inputs.get("fixture_id"),
                league_id=inputs.get("league_id"),
            )

        # 8. Publish REAL persisted refs for waiters; release lock.
        await ctx.locks.publish_result(lock_key, _refs_to_json(refs), _ttl(ctx))
        return _select_ref(refs, inputs)
    finally:
        try:
            await ctx.locks.release(lock)
        except Exception:  # noqa: BLE001 — release failures must not mask results
            logger.warning("coalescing lock release failed", exc_info=True)


def _table_for(collector: Collector) -> str:
    mapping: dict[str, str] = {
        "standings": "standings_snapshots",
        "team_stats": "team_statistics_snapshots",
        "form_inputs": "team_form_snapshots",
        "availability": "availability_snapshots",
        "lineups": "lineup_snapshots",
        "odds": "odds_snapshot_sets",
    }
    return mapping.get(collector.name, f"{collector.name}_snapshots")


def _uuid_or_none(value: object) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def _payload_id_stmt(provider: str, endpoint_family: str, payload_hash: str) -> Any:
    from sqlalchemy import select

    from sports_intelligence.db.models import RawProviderPayload

    return select(RawProviderPayload.id).where(
        RawProviderPayload.provider == provider,
        RawProviderPayload.endpoint_family == endpoint_family,
        RawProviderPayload.payload_hash == payload_hash,
    )


def _ttl(ctx: CollectorContext) -> Any:
    from datetime import timedelta

    return timedelta(seconds=ctx.settings.redis_lock_default_ttl_seconds)


def list_registered() -> list[str]:
    return list(_REGISTRY)
