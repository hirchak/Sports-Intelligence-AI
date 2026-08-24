from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from sports_intelligence.collectors.framework import CollectorContext, CollectorResult
from sports_intelligence.collectors.sports_collectors import (
    AvailabilityCollector,
    FormInputsCollector,
    LineupCollector,
    StandingsCollector,
    TeamStatisticsCollector,
    lineup_poll_due,
)
from sports_intelligence.core.phases import ForecastPhase


class _FakeSession:
    def __init__(
        self,
        *,
        fixture_id: uuid.UUID | None,
        team_mapping: dict[int, uuid.UUID] | None = None,
    ) -> None:
        self.added: list[object] = []
        self.committed = False
        self._fixture_id = fixture_id
        self.team_mapping = team_mapping or {}

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    def begin(self):  # type: ignore[no-untyped-def]
        class _CM:
            async def __aenter__(self2) -> None:  # type: ignore[no-untyped-def]
                return None

            async def __aexit__(self2, *exc: object) -> bool:  # type: ignore[no-untyped-def]
                return False

        return _CM()

    def add(self, obj: object) -> None:
        self.added.append(obj)
        if getattr(obj, "id", None) is None and hasattr(obj, "id"):
            obj.id = uuid.uuid4()  # type: ignore[attr-defined]

    async def commit(self) -> None:
        self.committed = True

    async def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None and hasattr(obj, "id"):
                obj.id = uuid.uuid4()  # type: ignore[attr-defined]

    async def get(self, _model: object, key: uuid.UUID) -> object | None:
        if self._fixture_id is not None and key == self._fixture_id:
            return MagicMock()
        return None

    async def execute(self, *_args: object, **_kwargs: object) -> MagicMock:
        result = MagicMock()
        result.first = MagicMock(
            return_value=(next(iter(self.team_mapping.values()), None),)
            if self.team_mapping
            else None
        )
        result.scalar_one_or_none = MagicMock(side_effect=self._scalar_one_or_none)
        result.scalar_one = MagicMock(return_value=uuid.uuid4())
        return result

    def _scalar_one_or_none(self, *args: object) -> object:
        # Team external-id resolution: return the mapped internal uuid.
        if self.team_mapping:
            # The query filters by external_id; our fake cannot inspect
            # SQL, so fall back to the first mapping.
            return next(iter(self.team_mapping.values()))
        return 42


class _FakeSessionFactory:
    def __init__(
        self, *, fixture_id: uuid.UUID | None, team_mapping: dict[int, uuid.UUID] | None = None
    ) -> None:
        self.fixture_id = fixture_id
        self.team_mapping = team_mapping or {}
        self.sessions: list[_FakeSession] = []

    def __call__(self) -> _FakeSession:  # type: ignore[no-untyped-def]
        session = _FakeSession(fixture_id=self.fixture_id, team_mapping=self.team_mapping)
        self.sessions.append(session)
        return session


def _ctx(
    *, fixture_id: uuid.UUID | None, session_factory: _FakeSessionFactory | None = None
) -> CollectorContext:
    from sports_intelligence.collectors.freshness import FreshnessPolicy
    from sports_intelligence.core.config import Settings

    quota = MagicMock()
    locks = MagicMock()
    settings = Settings(_env_file=None, app_env="mock")
    factory = session_factory or _FakeSessionFactory(fixture_id=fixture_id)
    return CollectorContext(
        provider=MagicMock(name="mock"),
        quota=quota,
        locks=locks,
        freshness=FreshnessPolicy(settings),
        session_factory=factory,
        settings=settings,
        redis=None,
        phase=ForecastPhase.PREMATCH,
    )


@pytest.mark.asyncio
async def test_availability_persist_two_team_snapshots_from_one_observation() -> None:
    """One fixture response with both teams → TWO separated snapshots,
    each with ONLY its own entries."""
    home_internal = uuid.uuid4()
    away_internal = uuid.uuid4()
    session_factory = _FakeSessionFactory(
        fixture_id=uuid.uuid4(), team_mapping={9001: home_internal, 9002: away_internal}
    )
    ctx = _ctx(fixture_id=session_factory.fixture_id, session_factory=session_factory)

    result = CollectorResult(
        raw_payload={"response": []},
        normalized={
            "teams": [
                {
                    "provider_team_id": 9001,
                    "team_name": "Mock United",
                    "entries": [
                        {
                            "player_name": "P1",
                            "provider_player_id": 1,
                            "entry_type": "Missing Fixture",
                            "missing": True,
                        }
                    ],
                },
                {
                    "provider_team_id": 9002,
                    "team_name": "Mock City",
                    "entries": [],
                },
            ]
        },
    )
    collector = AvailabilityCollector()
    refs = await collector.persist(
        ctx,
        result,
        captured_at=datetime.now(UTC),
        source_fingerprint="mock:availability:v1:test",
        payload_id=uuid.uuid4(),
        fixture_id=session_factory.fixture_id,
        team_id=uuid.uuid4(),
    )
    added = session_factory.sessions[-1].added
    assert len(added) == 2
    states = {s.availability_state for s in added}
    assert "KNOWN_PRESENT" in states
    assert "UNKNOWN" in states
    assert len(refs) == 2
    # Home entries belong only to the home snapshot.
    home = next(s for s in added if s.team_id)
    assert all(p.get("player_name") == "P1" for p in home.players_jsonb)


@pytest.mark.asyncio
async def test_availability_persist_requires_known_fixture() -> None:
    ctx = _ctx(fixture_id=None)
    collector = AvailabilityCollector()
    with pytest.raises(LookupError):
        await collector.persist(
            ctx,
            CollectorResult(raw_payload=None, normalized={"teams": []}),
            captured_at=datetime.now(UTC),
            source_fingerprint="test",
            payload_id=uuid.uuid4(),
            fixture_id=uuid.uuid4(),
            team_id=uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_lineup_persist_keeps_publication_state() -> None:
    """NOT_YET_PUBLISHED persists as an immutable observation bound to
    the requesting team — never collapsed into an empty confirmed
    lineup."""
    session_factory = _FakeSessionFactory(fixture_id=uuid.uuid4())
    ctx = _ctx(fixture_id=session_factory.fixture_id, session_factory=session_factory)
    result = CollectorResult(
        raw_payload={"response": []},
        normalized={"publication_state": "NOT_YET_PUBLISHED", "teams": []},
    )
    collector = LineupCollector()
    refs = await collector.persist(
        ctx,
        result,
        captured_at=datetime.now(UTC),
        source_fingerprint="mock:lineups:v1:test",
        payload_id=uuid.uuid4(),
        fixture_id=session_factory.fixture_id,
        team_id=uuid.uuid4(),
    )
    added = session_factory.sessions[-1].added
    assert added[0].publication_state == "NOT_YET_PUBLISHED"
    assert added[0].players_jsonb == []
    assert added[0].confirmed is False
    assert len(refs) == 1


@pytest.mark.asyncio
async def test_lineup_persist_confirmed_with_players() -> None:
    requested_team_id = uuid.uuid4()
    session_factory = _FakeSessionFactory(
        fixture_id=uuid.uuid4(), team_mapping={9001: requested_team_id}
    )
    ctx = _ctx(fixture_id=session_factory.fixture_id, session_factory=session_factory)
    result = CollectorResult(
        raw_payload={"response": []},
        normalized={
            "publication_state": "CONFIRMED",
            "teams": [
                {
                    "provider_team_id": 9001,
                    "team_name": "Mock United",
                    "formation": "4-3-3",
                    "confirmed": True,
                    "starters": [
                        {
                            "player_name": "R1",
                            "provider_player_id": 1,
                            "shirt_number": 1,
                            "starter": True,
                        }
                    ],
                    "substitutes": [],
                }
            ],
        },
    )
    collector = LineupCollector()
    await collector.persist(
        ctx,
        result,
        captured_at=datetime.now(UTC),
        source_fingerprint="test",
        payload_id=uuid.uuid4(),
        fixture_id=session_factory.fixture_id,
        team_id=requested_team_id,
    )
    added = session_factory.sessions[-1].added
    assert added[0].publication_state == "CONFIRMED"
    assert added[0].formation == "4-3-3"
    assert len(added[0].players_jsonb) == 1
    assert added[0].team_id == requested_team_id


@pytest.mark.asyncio
async def test_form_inputs_persists_snapshot() -> None:
    session_factory = _FakeSessionFactory(fixture_id=None)
    ctx = _ctx(fixture_id=None, session_factory=session_factory)
    result = CollectorResult(
        raw_payload={"response": []},
        normalized={"outcomes": [{"outcome": "W"}], "history": [], "computed_locally": True},
    )
    collector = FormInputsCollector()
    refs = await collector.persist(
        ctx,
        result,
        captured_at=datetime.now(UTC),
        source_fingerprint="test",
        payload_id=uuid.uuid4(),
        team_id=uuid.uuid4(),
    )
    assert refs[0].table == "team_form_snapshots"
    added = session_factory.sessions[-1].added
    assert added[0].metrics_jsonb["computed_locally"] is True


@pytest.mark.asyncio
async def test_standings_lock_key_includes_league_and_season() -> None:
    collector = StandingsCollector()
    league = uuid.uuid4()
    season = uuid.uuid4()
    assert collector.lock_key(league_id=league, season_id=season) != collector.lock_key(
        league_id=league, season_id=None
    )


@pytest.mark.asyncio
async def test_team_statistics_lock_key_includes_team_league_season() -> None:
    collector = TeamStatisticsCollector()
    team = uuid.uuid4()
    league = uuid.uuid4()
    assert collector.lock_key(team_id=team, league_id=league, season_id=None) != collector.lock_key(
        team_id=team, league_id=league, season_id=uuid.uuid4()
    )


def test_lineup_poll_due_started_fixture_never_polled() -> None:
    kickoff = datetime(2026, 8, 21, 14, 0, tzinfo=UTC)
    now = kickoff + timedelta(minutes=5)
    assert (
        lineup_poll_due(
            kickoff_at=kickoff,
            now=now,
            windows_minutes=[120, 60, 20],
            latest_state="NOT_YET_PUBLISHED",
            latest_captured_at=None,
        )
        is False
    )


def test_lineup_poll_due_confirmed_stops_polling() -> None:
    kickoff = datetime(2026, 8, 21, 14, 0, tzinfo=UTC)
    now = kickoff - timedelta(minutes=30)
    assert (
        lineup_poll_due(
            kickoff_at=kickoff,
            now=now,
            windows_minutes=[120, 60, 20],
            latest_state="CONFIRMED",
            latest_captured_at=None,
        )
        is False
    )


def test_lineup_poll_due_t120_unconfirmed_does_not_block_t60() -> None:
    """A T-120 NOT_YET_PUBLISHED observation must not block the T-60
    refresh (a 24h TTL is irrelevant inside the windows policy)."""
    kickoff = datetime(2026, 8, 21, 14, 0, tzinfo=UTC)
    # Last capture happened inside the T-120 window (at T-110).
    captured_t110 = kickoff - timedelta(minutes=110)
    # Now we are inside the T-60 window (T-50).
    now_t50 = kickoff - timedelta(minutes=50)
    assert (
        lineup_poll_due(
            kickoff_at=kickoff,
            now=now_t50,
            windows_minutes=[120, 60, 20],
            latest_state="NOT_YET_PUBLISHED",
            latest_captured_at=captured_t110,
        )
        is True
    )


def test_lineup_poll_due_confirmed_at_t60_blocks_t20() -> None:
    kickoff = datetime(2026, 8, 21, 14, 0, tzinfo=UTC)
    captured_t60 = kickoff - timedelta(minutes=60)
    now_t20 = kickoff - timedelta(minutes=20)
    assert (
        lineup_poll_due(
            kickoff_at=kickoff,
            now=now_t20,
            windows_minutes=[120, 60, 20],
            latest_state="CONFIRMED",
            latest_captured_at=captured_t60,
        )
        is False
    )


def test_lineup_poll_due_outside_all_windows() -> None:
    kickoff = datetime(2026, 8, 21, 14, 0, tzinfo=UTC)
    now = kickoff - timedelta(minutes=300)
    assert (
        lineup_poll_due(
            kickoff_at=kickoff,
            now=now,
            windows_minutes=[120, 60, 20],
            latest_state="NOT_YET_PUBLISHED",
            latest_captured_at=None,
        )
        is False
    )


_ = timedelta
