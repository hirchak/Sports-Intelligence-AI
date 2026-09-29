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
        fixture_teams: tuple[uuid.UUID, uuid.UUID] | None = None,
        external_to_internal=None,
    ) -> None:
        self.added: list[object] = []
        self.committed = False
        self._fixture_id = fixture_id
        self.team_mapping = team_mapping or {}
        self.fixture_teams = fixture_teams
        self.external_to_internal = external_to_internal

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
            if self.fixture_teams is not None:
                fake = MagicMock()
                fake.home_team_id = self.fixture_teams[0]
                fake.away_team_id = self.fixture_teams[1]
                fake.kickoff_at = datetime.now(UTC)
                return fake
            return MagicMock()
        return None

    async def execute(self, stmt: object = None, *_args: object, **_kwargs: object) -> MagicMock:
        result = MagicMock()
        result.first = MagicMock(
            return_value=(self._resolve_external(stmt),)
            if self._resolve_external(stmt) is not None
            else None
        )
        result.scalar_one_or_none = MagicMock(side_effect=lambda *a: self._resolve_external(stmt))
        result.scalar_one = MagicMock(return_value=uuid.uuid4())
        return result

    def _resolve_external(self, stmt: object) -> uuid.UUID | None:
        """Resolve the external team id from compiled statement params
        (e.g. external_id = '9001')."""
        if stmt is not None:
            try:
                params = stmt.compile().params  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                params = {}
            for ext, internal in self.team_mapping.items():
                if any(str(value) == str(ext) for value in params.values()):
                    return internal
        if self.team_mapping:
            return next(iter(self.team_mapping.values()))
        return None


class _FakeSessionFactory:
    def __init__(
        self,
        *,
        fixture_id: uuid.UUID | None,
        team_mapping: dict[int, uuid.UUID] | None = None,
        fixture_teams: tuple[uuid.UUID, uuid.UUID] | None = None,
    ) -> None:
        self.fixture_id = fixture_id
        self.team_mapping = team_mapping or {}
        self.fixture_teams = fixture_teams
        self.sessions: list[_FakeSession] = []

    def __call__(self) -> _FakeSession:  # type: ignore[no-untyped-def]
        session = _FakeSession(
            fixture_id=self.fixture_id,
            team_mapping=self.team_mapping,
            fixture_teams=self.fixture_teams,
            external_to_internal=self._resolve,
        )
        self.sessions.append(session)
        return session

    def _resolve(self, stmt: object) -> uuid.UUID | None:
        if stmt is not None:
            try:
                params = stmt.compile().params  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                params = {}
            for ext, internal in self.team_mapping.items():
                if any(str(value) == str(ext) for value in params.values()):
                    return internal
        return None


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
        fixture_id=uuid.uuid4(),
        team_mapping={9001: home_internal, 9002: away_internal},
        fixture_teams=(home_internal, away_internal),
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
    """NOT_YET_PUBLISHED persists as immutable observations for BOTH
    fixture teams — never collapsed into an empty confirmed lineup."""
    home_internal = uuid.uuid4()
    away_internal = uuid.uuid4()
    session_factory = _FakeSessionFactory(
        fixture_id=uuid.uuid4(),
        team_mapping={9001: home_internal, 9002: away_internal},
        fixture_teams=(home_internal, away_internal),
    )
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
        team_id=home_internal,
    )
    added = session_factory.sessions[-1].added
    assert len(added) == 2
    assert all(s.publication_state == "NOT_YET_PUBLISHED" for s in added)
    assert all(s.players_jsonb == [] for s in added)
    assert all(s.confirmed is False for s in added)
    # Published refs contain BOTH team refs.
    assert len(refs) == 2
    assert {r.team_id for r in refs} == {home_internal, away_internal}


@pytest.mark.asyncio
async def test_lineup_persist_confirmed_with_players() -> None:
    home_internal = uuid.uuid4()
    away_internal = uuid.uuid4()
    session_factory = _FakeSessionFactory(
        fixture_id=uuid.uuid4(),
        team_mapping={9001: home_internal, 9002: away_internal},
        fixture_teams=(home_internal, away_internal),
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
        team_id=home_internal,
    )
    added = session_factory.sessions[-1].added
    by_team = {snap.team_id: snap for snap in added}
    home = by_team[home_internal]
    assert home.publication_state == "CONFIRMED"
    assert home.formation == "4-3-3"
    assert len(home.players_jsonb) == 1
    away = by_team[away_internal]
    assert away.publication_state == "NOT_YET_PUBLISHED"
    assert away.confirmed is False


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


@pytest.mark.asyncio
async def test_latest_snapshot_includes_season_id() -> None:
    """M4.4 §2: StandingCollector and TeamStatisticsCollector latest_snapshot()
    must include exact season_id in freshness identity when provided."""
    executed_stmts: list[object] = []
    session = MagicMock()

    async def fake_execute(stmt: object) -> MagicMock:
        executed_stmts.append(stmt)
        result = MagicMock()
        result.first.return_value = (datetime.now(UTC), uuid.uuid4())
        return result

    session.execute = fake_execute

    league_id = uuid.uuid4()
    season_id = uuid.uuid4()
    team_id = uuid.uuid4()

    sc = StandingsCollector()
    await sc.latest_snapshot(session, league_id=league_id, season_id=season_id)
    assert len(executed_stmts) == 1
    compiled_sc = str(executed_stmts[0].compile(compile_kwargs={"literal_binds": True}))  # type: ignore[attr-defined]
    assert league_id.hex in compiled_sc
    assert season_id.hex in compiled_sc

    tc = TeamStatisticsCollector()
    await tc.latest_snapshot(session, team_id=team_id, league_id=league_id, season_id=season_id)
    assert len(executed_stmts) == 2
    compiled_tc = str(executed_stmts[1].compile(compile_kwargs={"literal_binds": True}))  # type: ignore[attr-defined]
    assert team_id.hex in compiled_tc
    assert league_id.hex in compiled_tc
    assert season_id.hex in compiled_tc

    # M4.4 §2: missing season identity MUST NOT execute a broad query or match any season
    snap_sc, id_sc = await sc.latest_snapshot(session, league_id=league_id, season_id=None)
    assert snap_sc is None and id_sc is None
    snap_tc, id_tc = await tc.latest_snapshot(
        session, team_id=team_id, league_id=league_id, season_id=None
    )
    assert snap_tc is None and id_tc is None
    # Still only the 2 previous queries:
    assert len(executed_stmts) == 2

    # Lock keys differ across seasons and none:
    sid_a = uuid.UUID("11111111-1111-1111-1111-111111111111")
    sid_b = uuid.UUID("22222222-2222-2222-2222-222222222222")
    assert (
        len(
            {
                sc.lock_key(league_id=league_id, season_id=sid_a),
                sc.lock_key(league_id=league_id, season_id=sid_b),
                sc.lock_key(league_id=league_id, season_id=None),
            }
        )
        == 3
    )
    assert (
        len(
            {
                tc.lock_key(team_id=team_id, league_id=league_id, season_id=sid_a),
                tc.lock_key(team_id=team_id, league_id=league_id, season_id=sid_b),
                tc.lock_key(team_id=team_id, league_id=league_id, season_id=None),
            }
        )
        == 3
    )
