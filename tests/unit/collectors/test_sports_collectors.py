from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from sports_intelligence.collectors.framework import CollectorContext
from sports_intelligence.collectors.sports_collectors import (
    AvailabilityCollector,
    FormInputsCollector,
    LineupCollector,
    StandingsCollector,
    TeamStatisticsCollector,
)


class _FakeSession:
    """Minimal async session supporting add/commit/flush/get/execute."""

    def __init__(self, *, fixture_id: uuid.UUID | None) -> None:
        self.added: list[object] = []
        self.committed = False
        self._fixture_id = fixture_id

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.committed = True

    async def flush(self) -> None:
        pass

    async def get(self, _model: object, key: uuid.UUID) -> object | None:
        if self._fixture_id is not None and key == self._fixture_id:
            return MagicMock()
        return None

    async def execute(self, *_args: object, **_kwargs: object) -> MagicMock:
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=None)
        return result


class _FakeSessionFactory:
    def __init__(self, *, fixture_id: uuid.UUID | None) -> None:
        self.fixture_id = fixture_id
        self.sessions: list[_FakeSession] = []

    def __call__(self) -> _FakeSession:  # type: ignore[no-untyped-def]
        session = _FakeSession(fixture_id=self.fixture_id)
        self.sessions.append(session)
        return session


def _ctx(*, fixture_id: uuid.UUID | None) -> CollectorContext:
    quota = MagicMock()
    quota.acquire = MagicMock()
    quota.record = MagicMock()
    locks = MagicMock()
    from sports_intelligence.collectors.freshness import FreshnessPolicy
    from sports_intelligence.core.config import Settings

    settings = Settings(_env_file=None, app_env="mock")
    return CollectorContext(
        provider=MagicMock(name="mock"),
        quota=quota,
        locks=locks,
        freshness=FreshnessPolicy(settings),
        session_factory=_FakeSessionFactory(fixture_id=fixture_id),
        settings=settings,
        redis=None,
    )


@pytest.mark.asyncio
async def test_availability_persist_marks_unknown_when_provider_silent() -> None:
    """Spec 14 §7: UNKNOWN when the provider silently returns no data;
    lineup unavailable ≠ empty lineup."""
    session_factory = _FakeSessionFactory(fixture_id=None)
    quota = MagicMock()
    locks = MagicMock()
    from sports_intelligence.collectors.freshness import FreshnessPolicy
    from sports_intelligence.core.config import Settings

    settings = Settings(_env_file=None, app_env="mock")
    ctx = CollectorContext(
        provider=MagicMock(name="mock"),
        quota=quota,
        locks=locks,
        freshness=FreshnessPolicy(settings),
        session_factory=session_factory,
        settings=settings,
        redis=None,
    )

    fixture_id = uuid.uuid4()
    session_factory.fixture_id = fixture_id

    class _UnknownResult:
        def __init__(self) -> None:
            self.normalized = {"home": [], "away": []}

    # Even though the persist method delegates to a fresh session, the
    # fixture check above ensures UNKNOWN is recorded when no players
    # are present.
    from sports_intelligence.collectors.framework import CollectorResult

    result = CollectorResult(raw_payload=None, normalized={"home": [], "away": []})
    collector = AvailabilityCollector()
    ref = await collector.persist(
        ctx,
        result,
        captured_at=datetime.now(UTC),
        source_fingerprint="mock:availability:test",
        fixture_id=fixture_id,
        team_id=uuid.uuid4(),
    )
    assert ref.table == "availability_snapshots"
    added = session_factory.sessions[-1].added
    assert added[0].availability_state == "UNKNOWN"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_availability_persist_marks_known_present_when_doubt() -> None:
    session_factory = _FakeSessionFactory(fixture_id=None)
    quota = MagicMock()
    locks = MagicMock()
    from sports_intelligence.collectors.freshness import FreshnessPolicy
    from sports_intelligence.core.config import Settings

    settings = Settings(_env_file=None, app_env="mock")
    ctx = CollectorContext(
        provider=MagicMock(name="mock"),
        quota=quota,
        locks=locks,
        freshness=FreshnessPolicy(settings),
        session_factory=session_factory,
        settings=settings,
        redis=None,
    )

    fixture_id = uuid.uuid4()
    session_factory.fixture_id = fixture_id

    from sports_intelligence.collectors.framework import CollectorResult

    result = CollectorResult(
        raw_payload=None,
        normalized={
            "home": [
                {"player": "Saka", "status": "available", "type": "starter"},
                {"player": "Ødegaard", "status": "doubt", "type": "starter"},
            ],
            "away": [{"player": "McAtee", "status": "available", "type": "starter"}],
        },
    )
    collector = AvailabilityCollector()
    await collector.persist(
        ctx,
        result,
        captured_at=datetime.now(UTC),
        source_fingerprint="mock:availability:test",
        fixture_id=fixture_id,
        team_id=uuid.uuid4(),
    )
    added = session_factory.sessions[-1].added
    assert added[0].availability_state == "KNOWN_PRESENT"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_availability_persist_marks_known_none_when_all_available() -> None:
    session_factory = _FakeSessionFactory(fixture_id=None)
    quota = MagicMock()
    locks = MagicMock()
    from sports_intelligence.collectors.freshness import FreshnessPolicy
    from sports_intelligence.core.config import Settings

    settings = Settings(_env_file=None, app_env="mock")
    ctx = CollectorContext(
        provider=MagicMock(name="mock"),
        quota=quota,
        locks=locks,
        freshness=FreshnessPolicy(settings),
        session_factory=session_factory,
        settings=settings,
        redis=None,
    )

    fixture_id = uuid.uuid4()
    session_factory.fixture_id = fixture_id

    from sports_intelligence.collectors.framework import CollectorResult

    result = CollectorResult(
        raw_payload=None,
        normalized={
            "home": [
                {"player": "Saka", "status": "available", "type": "starter"},
            ],
            "away": [{"player": "McAtee", "status": "available", "type": "starter"}],
        },
    )
    collector = AvailabilityCollector()
    await collector.persist(
        ctx,
        result,
        captured_at=datetime.now(UTC),
        source_fingerprint="mock:availability:test",
        fixture_id=fixture_id,
        team_id=uuid.uuid4(),
    )
    added = session_factory.sessions[-1].added
    assert added[0].availability_state == "KNOWN_NONE"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_availability_persist_requires_known_fixture() -> None:
    session_factory = _FakeSessionFactory(fixture_id=None)  # no fixture
    quota = MagicMock()
    locks = MagicMock()
    from sports_intelligence.collectors.freshness import FreshnessPolicy
    from sports_intelligence.core.config import Settings

    settings = Settings(_env_file=None, app_env="mock")
    ctx = CollectorContext(
        provider=MagicMock(name="mock"),
        quota=quota,
        locks=locks,
        freshness=FreshnessPolicy(settings),
        session_factory=session_factory,
        settings=settings,
        redis=None,
    )

    from sports_intelligence.collectors.framework import CollectorResult

    collector = AvailabilityCollector()
    with pytest.raises(LookupError):
        await collector.persist(
            ctx,
            CollectorResult(raw_payload=None, normalized={"home": [], "away": []}),
            captured_at=datetime.now(UTC),
            source_fingerprint="mock:availability:test",
            fixture_id=uuid.uuid4(),
            team_id=uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_lineup_persist_keeps_unconfirmed_with_no_players() -> None:
    """lineup unavailable ≠ empty lineup: persist keeps the
    confirmed=False flag and an empty players list rather than
    collapsing into None."""
    session_factory = _FakeSessionFactory(fixture_id=None)
    quota = MagicMock()
    locks = MagicMock()
    from sports_intelligence.collectors.freshness import FreshnessPolicy
    from sports_intelligence.core.config import Settings

    settings = Settings(_env_file=None, app_env="mock")
    ctx = CollectorContext(
        provider=MagicMock(name="mock"),
        quota=quota,
        locks=locks,
        freshness=FreshnessPolicy(settings),
        session_factory=session_factory,
        settings=settings,
        redis=None,
    )

    fixture_id = uuid.uuid4()
    session_factory.fixture_id = fixture_id

    from sports_intelligence.collectors.framework import CollectorResult

    result = CollectorResult(
        raw_payload=None,
        normalized={
            "confirmed": False,
            "formation": None,
            "players": [],
        },
    )
    collector = LineupCollector()
    await collector.persist(
        ctx,
        result,
        captured_at=datetime.now(UTC),
        source_fingerprint="mock:lineups:test",
        fixture_id=fixture_id,
        team_id=uuid.uuid4(),
    )
    added = session_factory.sessions[-1].added
    snapshot = added[0]
    assert snapshot.confirmed is False
    assert snapshot.players_jsonb == []
    assert snapshot.formation is None


@pytest.mark.asyncio
async def test_lineup_persist_keeps_confirmed_with_players() -> None:
    session_factory = _FakeSessionFactory(fixture_id=None)
    quota = MagicMock()
    locks = MagicMock()
    from sports_intelligence.collectors.freshness import FreshnessPolicy
    from sports_intelligence.core.config import Settings

    settings = Settings(_env_file=None, app_env="mock")
    ctx = CollectorContext(
        provider=MagicMock(name="mock"),
        quota=quota,
        locks=locks,
        freshness=FreshnessPolicy(settings),
        session_factory=session_factory,
        settings=settings,
        redis=None,
    )

    fixture_id = uuid.uuid4()
    session_factory.fixture_id = fixture_id

    from sports_intelligence.collectors.framework import CollectorResult

    result = CollectorResult(
        raw_payload=None,
        normalized={
            "confirmed": True,
            "formation": "4-3-3",
            "players": [
                {"name": "Raya", "position": "GK", "shirt": 22, "starter": True},
            ],
        },
    )
    collector = LineupCollector()
    await collector.persist(
        ctx,
        result,
        captured_at=datetime.now(UTC),
        source_fingerprint="mock:lineups:test",
        fixture_id=fixture_id,
        team_id=uuid.uuid4(),
    )
    added = session_factory.sessions[-1].added
    snapshot = added[0]
    assert snapshot.confirmed is True
    assert snapshot.formation == "4-3-3"
    assert len(snapshot.players_jsonb) == 1


@pytest.mark.asyncio
async def test_standings_lock_key_includes_league_and_season() -> None:
    collector = StandingsCollector()
    league = uuid.uuid4()
    season = uuid.uuid4()
    key1 = collector.lock_key(league_id=league, season_id=season)
    key2 = collector.lock_key(league_id=league, season_id=None)
    assert key1 != key2
    assert str(league) in key1
    assert str(season) in key1


@pytest.mark.asyncio
async def test_team_statistics_lock_key_includes_team_league_season() -> None:
    collector = TeamStatisticsCollector()
    team = uuid.uuid4()
    league = uuid.uuid4()
    key1 = collector.lock_key(team_id=team, league_id=league, season_id=None)
    key2 = collector.lock_key(team_id=team, league_id=league, season_id=uuid.uuid4())
    assert key1 != key2


@pytest.mark.asyncio
async def test_form_inputs_collector_persists_snapshot() -> None:
    session_factory = _FakeSessionFactory(fixture_id=None)
    quota = MagicMock()
    locks = MagicMock()
    from sports_intelligence.collectors.freshness import FreshnessPolicy
    from sports_intelligence.core.config import Settings

    settings = Settings(_env_file=None, app_env="mock")
    ctx = CollectorContext(
        provider=MagicMock(name="mock"),
        quota=quota,
        locks=locks,
        freshness=FreshnessPolicy(settings),
        session_factory=session_factory,
        settings=settings,
        redis=None,
    )

    from sports_intelligence.collectors.framework import CollectorResult

    result = CollectorResult(
        raw_payload=None,
        normalized={"team": "Arsenal", "form_string": "W W W"},
    )
    collector = FormInputsCollector()
    ref = await collector.persist(
        ctx,
        result,
        captured_at=datetime.now(UTC),
        source_fingerprint="mock:form_inputs:test",
        team_id=uuid.uuid4(),
    )
    assert ref.table == "team_form_snapshots"
    added = session_factory.sessions[-1].added
    assert added[0].metrics_jsonb["team"] == "Arsenal"


_ = timedelta
