from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

import sports_intelligence.collectors.odds_collector  # noqa: F401  # registers collectors
import sports_intelligence.collectors.sports_collectors  # noqa: F401
from sports_intelligence.collectors.framework import (
    CollectorContext,
    LockContendedError,
    QuotaUnavailableError,
    SnapshotRef,
    list_registered,
    run_collector,
)
from sports_intelligence.collectors.freshness import FreshnessPolicy
from sports_intelligence.collectors.locks import CoalesceLockManager
from sports_intelligence.collectors.quota import (
    DegradationMode,
    QuotaDecision,
    QuotaDecisionKind,
)
from sports_intelligence.core.config import Settings
from sports_intelligence.providers.dto import (
    LineupPublicationState,
    ProviderAvailabilityResult,
    ProviderCompletedFixturesResult,
    ProviderLineupsResult,
    ProviderStandingsResult,
    ProviderTeamStatisticsResult,
)


class _DummyRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def set(self, key, value, ex=None, nx=False):  # type: ignore[no-untyped-def]
        if nx and key in self.store:
            return None
        self.store[key] = value if isinstance(value, str) else value.decode("utf-8")
        return True

    async def get(self, key):  # type: ignore[no-untyped-def]
        return self.store.get(key)

    async def eval(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        return 1

    async def incrby(self, key, amount):  # type: ignore[no-untyped-def]
        self.store[key] = str(int(self.store.get(key, 0)) + amount)
        return int(self.store[key])

    async def expire(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        return True

    async def decrby(self, key, amount):  # type: ignore[no-untyped-def]
        self.store[key] = str(int(self.store.get(key, 0)) - amount)
        return int(self.store[key])


def _settings() -> Settings:
    return Settings(_env_file=None, app_env="mock", app_timezone="Europe/Warsaw")


class _FakeSession:
    """Session stub: latest_snapshot returns a configurable capture."""

    def __init__(
        self,
        captured_at: datetime | None,
        snapshot_id: uuid.UUID | None,
        *,
        league_id: uuid.UUID | None = None,
    ) -> None:
        self._captured_at = captured_at
        self._snapshot_id = snapshot_id
        self._league_id = league_id
        self.added: list[object] = []

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def execute(self, *_args: object, **_kwargs: object) -> MagicMock:
        result = MagicMock()
        result.first = MagicMock(
            return_value=(self._captured_at, self._snapshot_id)
            if (self._captured_at or self._snapshot_id)
            else None
        )
        result.scalar_one = MagicMock(return_value=uuid.uuid4())
        # External-ID resolution returns a numeric provider id.
        result.scalar_one_or_none = MagicMock(return_value=42)
        return result

    async def get(self, _model: object, _key: object) -> object:
        # The exact Season resolver needs a Season-like row bound to the
        # expected league (M4.4 §2).
        from sports_intelligence.db.models import Season

        if isinstance(_model, type) and issubclass(_model, Season):
            fake = MagicMock()
            fake.league_id = self._league_id
            fake.name = "2026-2027"
            return fake
        return MagicMock()

    def add(self, _obj: object) -> None:
        self.added.append(_obj)
        id_attr = getattr(_obj, "id", None)
        if id_attr is None and hasattr(_obj, "id"):
            _obj.id = uuid.uuid4()  # type: ignore[attr-defined]

    async def commit(self) -> None:
        return None

    async def flush(self) -> None:
        for obj in self.added:
            id_attr = getattr(obj, "id", None)
            if id_attr is None and hasattr(obj, "id"):
                obj.id = uuid.uuid4()  # type: ignore[attr-defined]

    def begin(self):  # type: ignore[no-untyped-def]
        class _CM:
            async def __aenter__(self2) -> None:  # type: ignore[no-untyped-def]
                return None

            async def __aexit__(self2, *exc: object) -> bool:  # type: ignore[no-untyped-def]
                return False

        return _CM()

    async def rollback(self) -> None:
        return None

    async def close(self) -> None:
        return None


class _FakeFactory:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def __call__(self) -> _FakeSession:  # type: ignore[no-untyped-def]
        return self._session


def _allowed_quota() -> MagicMock:
    quota = MagicMock()
    quota.reserve = AsyncMock(
        return_value=QuotaDecision(
            allowed=True,
            mode=DegradationMode.NORMAL,
            kind=QuotaDecisionKind.ALLOWED,
            reason="ok",
            remaining_daily=99,
            remaining_minute=9,
        )
    )
    quota.record_success = AsyncMock()
    quota.record_failure = AsyncMock()
    return quota


class _StubSportsProvider:
    """Minimal SportsDataProvider-protocol stub returning canned DTOs."""

    name = "mock"

    @property
    def capabilities(self):  # type: ignore[no-untyped-def]
        from sports_intelligence.providers.base import ProviderCapabilities

        return ProviderCapabilities(provider="mock", supports_fixtures_by_date=True)

    async def get_fixtures_by_date(self, *a, **k):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    async def get_standings(self, *a, **k):  # type: ignore[no-untyped-def]
        from sports_intelligence.core.time import utc_now

        return ProviderStandingsResult(
            provider="mock",
            retrieved_at=utc_now(),
            raw_payload={"response": []},
            provider_league_id=39,
            season=2026,
            rows=[],
        )

    async def get_team_statistics(self, *a, **k):  # type: ignore[no-untyped-def]
        from sports_intelligence.core.time import utc_now

        return ProviderTeamStatisticsResult(
            provider="mock",
            retrieved_at=utc_now(),
            raw_payload={"response": []},
            provider_team_id=9001,
            provider_league_id=39,
            season=2026,
            metrics={},
        )

    async def get_availability(self, *a, **k):  # type: ignore[no-untyped-def]
        from sports_intelligence.core.time import utc_now

        return ProviderAvailabilityResult(
            provider="mock",
            retrieved_at=utc_now(),
            raw_payload={"response": []},
            provider_fixture_id=42,
            teams=[],
        )

    async def get_lineups(self, *a, **k):  # type: ignore[no-untyped-def]
        from sports_intelligence.core.time import utc_now

        return ProviderLineupsResult(
            provider="mock",
            retrieved_at=utc_now(),
            raw_payload={"response": []},
            provider_fixture_id=42,
            publication_state=LineupPublicationState.NOT_YET_PUBLISHED,
            teams=[],
        )

    async def get_results_by_date(self, *a, **k):  # type: ignore[no-untyped-def]
        raise AssertionError("standings tests must not collect results")

    async def get_completed_fixtures(self, *a, **k):  # type: ignore[no-untyped-def]
        from sports_intelligence.core.time import utc_now

        return ProviderCompletedFixturesResult(
            provider="mock",
            retrieved_at=utc_now(),
            raw_payload={"response": []},
            provider_team_id=9001,
            fixtures=[],
        )

    async def aclose(self) -> None:
        return None


def _context(
    *,
    captured_at: datetime | None,
    snapshot_id: uuid.UUID | None = None,
    league_id: uuid.UUID | None = None,
) -> CollectorContext:
    settings = _settings()
    session = _FakeSession(captured_at, snapshot_id, league_id=league_id)
    return CollectorContext(
        provider=_StubSportsProvider(),
        quota=_allowed_quota(),
        locks=CoalesceLockManager(_DummyRedis(), settings),
        freshness=FreshnessPolicy(settings),
        session_factory=_FakeFactory(session),
        settings=settings,
        redis=_DummyRedis(),
    )


def test_resolve_registers_all_collectors() -> None:
    import sports_intelligence.collectors.odds_collector  # noqa: F401
    import sports_intelligence.collectors.sports_collectors  # noqa: F401

    expected = {"standings", "team_stats", "availability", "lineups", "form_inputs", "odds"}
    assert expected.issubset(set(list_registered()))


@pytest.mark.asyncio
async def test_freshness_hit_returns_real_existing_snapshot_id() -> None:
    """M4.1 §5: a freshness hit must return the ACTUAL persisted
    snapshot id, never a random UUID."""
    now = datetime.now(UTC)
    captured_at = now - timedelta(minutes=1)
    real_id = uuid.uuid4()
    league_id = uuid.uuid4()
    season_id = uuid.uuid4()
    ctx = _context(captured_at=captured_at, snapshot_id=real_id, league_id=league_id)
    ref = await run_collector(
        ctx,
        "standings",
        inputs={"league_id": league_id, "season_id": season_id},
    )
    assert ref.snapshot_id == real_id
    assert ref.captured_at == captured_at


@pytest.mark.asyncio
async def test_stale_trigger_fetches_and_quota_reserved_first() -> None:
    """Stale snapshot → exactly one provider fetch; quota reservation
    happens BEFORE the provider call."""
    captured_at = datetime.now(UTC) - timedelta(hours=24)
    league_id = uuid.uuid4()
    season_id = uuid.uuid4()
    ctx = _context(captured_at=captured_at, league_id=league_id)

    provider_calls: list[int] = []
    ref = await run_collector(
        ctx,
        "standings",
        inputs={"league_id": league_id, "season_id": season_id},
        on_provider_call=lambda: provider_calls.append(1),
    )
    assert provider_calls == [1]
    assert ctx.quota.reserve.await_count == 1
    assert ctx.quota.record_success.await_count == 1
    assert ref.snapshot_id is not None


@pytest.mark.asyncio
async def test_quota_denied_skips_provider_call() -> None:
    quota = MagicMock()
    quota.reserve = AsyncMock(
        return_value=QuotaDecision(
            allowed=False,
            mode=DegradationMode.RESERVE_ONLY,
            kind=QuotaDecisionKind.DENIED_RESERVE_ONLY,
            reason="reserve_only",
            remaining_daily=1,
            remaining_minute=5,
        )
    )
    quota.record_success = AsyncMock()
    quota.record_failure = AsyncMock()

    settings = _settings()
    session = _FakeSession(None, None)
    ctx = CollectorContext(
        provider=_StubSportsProvider(),
        quota=quota,
        locks=CoalesceLockManager(_DummyRedis(), settings),
        freshness=FreshnessPolicy(settings),
        session_factory=_FakeFactory(session),
        settings=settings,
        redis=_DummyRedis(),
    )
    provider_calls: list[int] = []
    with pytest.raises(QuotaUnavailableError):
        await run_collector(
            ctx,
            "standings",
            inputs={"league_id": uuid.uuid4()},
            on_provider_call=lambda: provider_calls.append(1),
        )
    assert provider_calls == []
    assert quota.record_failure.await_count == 0


@pytest.mark.asyncio
async def test_lock_contention_never_falls_back_to_fetch() -> None:
    """M4.1 §5: a contended lock with no published result must raise
    LockContendedError — never fetch-anyway for quota-sensitive work."""
    captured_at = datetime.now(UTC) - timedelta(hours=24)  # stale → would fetch
    settings = Settings(
        _env_file=None,
        app_env="mock",
        redis_lock_acquire_timeout_seconds=0.05,
    )
    redis = _DummyRedis()
    locks = CoalesceLockManager(redis, settings)
    quota = _allowed_quota()
    session = _FakeSession(captured_at, None)
    ctx = CollectorContext(
        provider=_StubSportsProvider(),
        quota=quota,
        locks=locks,
        freshness=FreshnessPolicy(settings),
        session_factory=_FakeFactory(session),
        settings=settings,
        redis=redis,
    )
    # Pre-hold the lock so run_collector cannot acquire it.
    league_id = uuid.uuid4()
    season_id = uuid.uuid4()
    lock_key = f"standings:{league_id}:{season_id}"
    held = await locks.acquire(key=lock_key)
    assert held is not None

    provider_calls: list[int] = []
    with pytest.raises(LockContendedError):
        await run_collector(
            ctx,
            "standings",
            inputs={"league_id": league_id, "season_id": season_id},
            on_provider_call=lambda: provider_calls.append(1),
        )
    assert provider_calls == []
    assert quota.reserve.await_count == 0
    await locks.release(held)


@pytest.mark.asyncio
async def test_concurrent_callers_share_winner_result_via_published_refs() -> None:
    """Two concurrent callers on the same key: only ONE fetch; the
    waiter reuses the winner's published snapshot id."""
    stale = datetime.now(UTC) - timedelta(hours=24)
    settings = Settings(_env_file=None, app_env="mock")
    redis = _DummyRedis()
    locks = CoalesceLockManager(redis, settings)
    quota = _allowed_quota()
    session = _FakeSession(stale, None)
    ctx = CollectorContext(
        provider=_StubSportsProvider(),
        quota=quota,
        locks=locks,
        freshness=FreshnessPolicy(settings),
        session_factory=_FakeFactory(session),
        settings=settings,
        redis=redis,
    )
    league_id = uuid.uuid4()
    season_id = uuid.uuid4()
    session._league_id = league_id
    provider_calls: list[int] = []

    async def _one() -> SnapshotRef:
        return await run_collector(
            ctx,
            "standings",
            inputs={"league_id": league_id, "season_id": season_id},
            on_provider_call=lambda: provider_calls.append(1),
        )

    refs = await asyncio.gather(_one(), _one())
    # The lock serializes: exactly one provider call.
    assert provider_calls == [1]
    ids = {r.snapshot_id for r in refs}
    assert len(ids) == 1
    assert all(r.snapshot_id is not None for r in refs)


def test_lock_manager_serializes_coalescing_keys() -> None:
    settings = _settings()
    manager = CoalesceLockManager(_DummyRedis(), settings)
    a = manager.lock_key("standings", "league-1", "season-1")
    b = manager.lock_key("standings", "league-2", "season-1")
    assert a != b
