from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sports_intelligence.collectors.framework import (
    CollectorContext,
    CollectorResult,
    SnapshotRef,
    register,
)
from sports_intelligence.core.phases import FreshnessCategory, Priority
from sports_intelligence.db.models import (
    AvailabilitySnapshot,
    LineupSnapshot,
    StandingSnapshot,
    TeamFormSnapshot,
    TeamStatisticsSnapshot,
)

# Deterministic MOCK data — keyed by (provider, league_slug, season_name).
# Shape mirrors typical API-Football responses; numbers are coherent so
# downstream math (form, no-vig) operates on real values.
_MOCK_STANDINGS: dict[tuple[str, str, str], list[dict[str, Any]]] = {
    ("mock", "premier-league", "2026-2027"): [
        {
            "rank": 1,
            "team": "Arsenal",
            "played": 3,
            "wins": 3,
            "draws": 0,
            "losses": 0,
            "gf": 7,
            "ga": 1,
            "gd": 6,
            "points": 9,
            "form": "W W W",
        },
        {
            "rank": 2,
            "team": "Manchester City",
            "played": 3,
            "wins": 2,
            "draws": 1,
            "losses": 0,
            "gf": 6,
            "ga": 2,
            "gd": 4,
            "points": 7,
            "form": "W W D",
        },
        {
            "rank": 3,
            "team": "Coventry",
            "played": 3,
            "wins": 1,
            "draws": 1,
            "losses": 1,
            "gf": 4,
            "ga": 4,
            "gd": 0,
            "points": 4,
            "form": "L W D",
        },
    ],
}

_MOCK_TEAM_STATS: dict[tuple[str, str], dict[str, Any]] = {
    ("mock", "Arsenal"): {
        "shots_per_game": 18.4,
        "shots_on_target_per_game": 7.1,
        "possession_pct": 58.2,
        "pass_accuracy_pct": 86.7,
        "xg": 6.4,
        "xga": 1.1,
        "clean_sheets": 2,
        "form_index": 0.91,
    },
    ("mock", "Coventry"): {
        "shots_per_game": 11.2,
        "shots_on_target_per_game": 3.8,
        "possession_pct": 47.0,
        "pass_accuracy_pct": 79.1,
        "xg": 2.1,
        "xga": 3.6,
        "clean_sheets": 0,
        "form_index": 0.42,
    },
}

_MOCK_AVAILABILITY: dict[str, dict[str, list[dict[str, Any]]]] = {
    "fixture-mock-1": {
        "home": [
            {"player": "Saka", "status": "available", "type": "starter"},
            {"player": "Ødegaard", "status": "doubt", "type": "starter", "reason": "muscle"},
        ],
        "away": [
            {"player": "McAtee", "status": "available", "type": "starter"},
        ],
    },
}

_MOCK_LINEUPS: dict[str, dict[str, dict[str, Any]]] = {
    "fixture-mock-1": {
        "home": {
            "confirmed": True,
            "formation": "4-3-3",
            "players": [
                {"name": "Raya", "position": "GK", "shirt": 22, "starter": True},
                {"name": "White", "position": "DF", "shirt": 4, "starter": True},
                {"name": "Saliba", "position": "DF", "shirt": 2, "starter": True},
                {"name": "Gabriel", "position": "DF", "shirt": 6, "starter": True},
                {"name": "Zinchenko", "position": "DF", "shirt": 35, "starter": True},
                {"name": "Rice", "position": "MF", "shirt": 41, "starter": True},
                {"name": "Ødegaard", "position": "MF", "shirt": 8, "starter": True},
                {"name": "Havertz", "position": "MF", "shirt": 29, "starter": True},
                {"name": "Saka", "position": "FW", "shirt": 7, "starter": True},
                {"name": "Gabriel Jesus", "position": "FW", "shirt": 9, "starter": True},
                {"name": "Martinelli", "position": "FW", "shirt": 11, "starter": True},
            ],
        },
        "away": {
            "confirmed": False,
            "formation": None,
            "players": [],
        },
    },
}


def _to_uuid(value: object) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _to_uuid_opt(value: object | None) -> uuid.UUID | None:
    if value is None:
        return None
    return _to_uuid(value)


class _LatestMixin:
    async def _latest(
        self, model: Any, session: AsyncSession, **filters: object
    ) -> datetime | None:
        stmt = (
            select(model.captured_at)
            .where(*[getattr(model, k) == v for k, v in filters.items()])
            .order_by(model.captured_at.desc())
            .limit(1)
        )
        return (await session.execute(stmt)).scalar_one_or_none()


class StandingsCollector(_LatestMixin):
    name = "standings"
    category = FreshnessCategory.STANDINGS
    priority = Priority.P2

    def lock_key(
        self, *, league_id: uuid.UUID, season_id: uuid.UUID | None = None, **_: Any
    ) -> str:
        return f"standings:{league_id}:{season_id or 'no-season'}"

    async def latest_captured_at(
        self,
        session: AsyncSession,
        *,
        league_id: uuid.UUID,
        season_id: uuid.UUID | None = None,
        **_: Any,
    ) -> datetime | None:
        return await self._latest(
            StandingSnapshot,
            session,
            league_id=league_id,
            season_id=season_id,
        )

    async def fetch(
        self, ctx: CollectorContext, *, league_id: uuid.UUID, **_: Any
    ) -> CollectorResult:
        # In MOCK mode we ignore the league and return one canned payload.
        rows = _MOCK_STANDINGS.get(("mock", "premier-league", "2026-2027"), [])
        return CollectorResult(raw_payload={"rows": rows}, normalized={"rows": rows})

    async def persist(
        self,
        ctx: CollectorContext,
        result: CollectorResult,
        captured_at: datetime,
        source_fingerprint: str,
        *,
        league_id: uuid.UUID,
        season_id: uuid.UUID | None = None,
        **_: Any,
    ) -> SnapshotRef:
        now = datetime.now(UTC)
        snapshot = StandingSnapshot(
            provider=ctx.provider_name(),
            league_id=league_id,
            season_id=season_id,
            captured_at=captured_at,
            source_fingerprint=source_fingerprint,
            rows_jsonb=list(result.normalized.get("rows", [])),
            updated_at=now,
        )
        async with ctx.session_factory() as session:
            session.add(snapshot)
            await session.commit()
        return SnapshotRef(
            table="standings_snapshots", snapshot_id=snapshot.id, captured_at=captured_at
        )


class TeamStatisticsCollector(_LatestMixin):
    name = "team_stats"
    category = FreshnessCategory.TEAM_STATISTICS
    priority = Priority.P2

    def lock_key(
        self,
        *,
        team_id: uuid.UUID,
        league_id: uuid.UUID,
        season_id: uuid.UUID | None = None,
        **_: Any,
    ) -> str:
        return f"team_stats:{team_id}:{league_id}:{season_id or 'no-season'}"

    async def latest_captured_at(
        self,
        session: AsyncSession,
        *,
        team_id: uuid.UUID,
        league_id: uuid.UUID,
        season_id: uuid.UUID | None = None,
        **_: Any,
    ) -> datetime | None:
        return await self._latest(
            TeamStatisticsSnapshot,
            session,
            team_id=team_id,
            league_id=league_id,
            season_id=season_id,
        )

    async def fetch(
        self, ctx: CollectorContext, *, team_id: uuid.UUID, **_: Any
    ) -> CollectorResult:
        metrics = _MOCK_TEAM_STATS.get(("mock", "Arsenal"), {})
        return CollectorResult(raw_payload=metrics, normalized=metrics)

    async def persist(
        self,
        ctx: CollectorContext,
        result: CollectorResult,
        captured_at: datetime,
        source_fingerprint: str,
        *,
        team_id: uuid.UUID,
        league_id: uuid.UUID,
        season_id: uuid.UUID | None = None,
        **_: Any,
    ) -> SnapshotRef:
        now = datetime.now(UTC)
        snapshot = TeamStatisticsSnapshot(
            provider=ctx.provider_name(),
            team_id=team_id,
            league_id=league_id,
            season_id=season_id,
            captured_at=captured_at,
            source_fingerprint=source_fingerprint,
            metrics_jsonb=dict(result.normalized),
            updated_at=now,
        )
        async with ctx.session_factory() as session:
            session.add(snapshot)
            await session.commit()
        return SnapshotRef(
            table="team_statistics_snapshots", snapshot_id=snapshot.id, captured_at=captured_at
        )


class AvailabilityCollector(_LatestMixin):
    name = "availability"
    category = FreshnessCategory.AVAILABILITY
    priority = Priority.P1

    def lock_key(self, *, fixture_id: uuid.UUID, **_: Any) -> str:
        return f"availability:{fixture_id}"

    async def latest_captured_at(
        self, session: AsyncSession, *, fixture_id: uuid.UUID, **_: Any
    ) -> datetime | None:
        return await self._latest(
            AvailabilitySnapshot,
            session,
            fixture_id=fixture_id,
        )

    async def fetch(
        self, ctx: CollectorContext, *, fixture_id: uuid.UUID, **_: Any
    ) -> CollectorResult:
        # Use the fixture_id hex as MOCK key; in real life the collector
        # would need to map fixture_id -> team -> provider_player_id, which
        # is deferred to the live provider implementation.
        fixture_key = "fixture-mock-1"
        payload = _MOCK_AVAILABILITY.get(fixture_key, {})
        return CollectorResult(raw_payload=payload, normalized=payload)

    async def persist(
        self,
        ctx: CollectorContext,
        result: CollectorResult,
        captured_at: datetime,
        source_fingerprint: str,
        *,
        fixture_id: uuid.UUID,
        team_id: uuid.UUID,
        **_: Any,
    ) -> SnapshotRef:
        from sports_intelligence.core.phases import AvailabilityState
        from sports_intelligence.db.models import Fixture

        # Spec 14 §7: UNKNOWN when the provider silently returns no data;
        # KNOWN_NONE when the provider explicitly confirms zero absences;
        # KNOWN_PRESENT when at least one player is documented.
        players = list(result.normalized.get("home", []) + result.normalized.get("away", []))
        if not players:
            state = AvailabilityState.UNKNOWN
        elif all(p.get("status") == "available" for p in players):
            state = AvailabilityState.KNOWN_NONE
        else:
            state = AvailabilityState.KNOWN_PRESENT

        # Verify the fixture actually exists to avoid FK errors when the
        # MOCK payload is requested for an unknown fixture_id.
        async with ctx.session_factory() as session:
            exists = await session.get(Fixture, fixture_id)
            if exists is None:
                raise LookupError(f"fixture {fixture_id} not found for availability persist")
            snapshot = AvailabilitySnapshot(
                provider=ctx.provider_name(),
                fixture_id=fixture_id,
                team_id=team_id,
                captured_at=captured_at,
                players_jsonb=players,
                impact_flags_jsonb=[p["player"] for p in players if p.get("status") != "available"],
                conflicts_jsonb=[],
                availability_state=state.value,
            )
            session.add(snapshot)
            await session.commit()
        return SnapshotRef(
            table="availability_snapshots", snapshot_id=snapshot.id, captured_at=captured_at
        )


class LineupCollector(_LatestMixin):
    name = "lineups"
    category = FreshnessCategory.LINEUPS
    priority = Priority.P1

    def lock_key(self, *, fixture_id: uuid.UUID, **_: Any) -> str:
        return f"lineups:{fixture_id}"

    async def latest_captured_at(
        self, session: AsyncSession, *, fixture_id: uuid.UUID, **_: Any
    ) -> datetime | None:
        return await self._latest(
            LineupSnapshot,
            session,
            fixture_id=fixture_id,
        )

    async def fetch(
        self, ctx: CollectorContext, *, fixture_id: uuid.UUID, **_: Any
    ) -> CollectorResult:
        # Pre-kickoff policy: refuse to fetch outside configured T-windows
        # unless the fixture is imminent and quota permits.
        settings = ctx.settings
        now = datetime.now(UTC)

        # We require the caller to provide a team_id and the collector
        # framework passes it through `_inputs`. Without a team context,
        # we cannot tell whether this window applies. Defer the window
        # check to the framework/policy layer; here we just fetch.
        del settings, now
        payload = _MOCK_LINEUPS.get("fixture-mock-1", {}).get("home", {})
        return CollectorResult(raw_payload=payload, normalized=payload)

    async def persist(
        self,
        ctx: CollectorContext,
        result: CollectorResult,
        captured_at: datetime,
        source_fingerprint: str,
        *,
        fixture_id: uuid.UUID,
        team_id: uuid.UUID,
        **_: Any,
    ) -> SnapshotRef:
        from sports_intelligence.db.models import Fixture

        confirmed = bool(result.normalized.get("confirmed", False))
        snapshot = LineupSnapshot(
            provider=ctx.provider_name(),
            fixture_id=fixture_id,
            team_id=team_id,
            captured_at=captured_at,
            confirmed=confirmed,
            formation=result.normalized.get("formation"),
            players_jsonb=list(result.normalized.get("players", [])),
        )
        async with ctx.session_factory() as session:
            exists = await session.get(Fixture, fixture_id)
            if exists is None:
                raise LookupError(f"fixture {fixture_id} not found for lineup persist")
            session.add(snapshot)
            await session.commit()
        return SnapshotRef(
            table="lineup_snapshots", snapshot_id=snapshot.id, captured_at=captured_at
        )


class FormInputsCollector(_LatestMixin):
    """Placeholder: derived locally from completed fixture results.

    In M4 this returns the most recent TeamFormSnapshot if present; the
    upstream computation from completed fixtures is a separate concern.
    """

    name = "form_inputs"
    category = FreshnessCategory.TEAM_FORM
    priority = Priority.P2

    def lock_key(
        self, *, team_id: uuid.UUID, window_size: int = 5, scope: str = "overall", **_: Any
    ) -> str:
        return f"form:{team_id}:{window_size}:{scope}"

    async def latest_captured_at(
        self,
        session: AsyncSession,
        *,
        team_id: uuid.UUID,
        window_size: int = 5,
        scope: str = "overall",
        **_: Any,
    ) -> datetime | None:
        return await self._latest(
            TeamFormSnapshot,
            session,
            team_id=team_id,
            window_size=window_size,
            scope=scope,
        )

    async def fetch(
        self, ctx: CollectorContext, *, team_id: uuid.UUID, **_: Any
    ) -> CollectorResult:
        # MOCK form inputs derived from standings row "form" strings.
        # In a real implementation this would consume completed fixtures.
        team_form = next(
            (
                row["form"]
                for row in _MOCK_STANDINGS.get(("mock", "premier-league", "2026-2027"), [])
                if row.get("team") == "Arsenal"
            ),
            None,
        )
        metrics = {
            "team": "Arsenal",
            "form_string": team_form,
            "computed_at": datetime.now(UTC).isoformat(),
        }
        return CollectorResult(raw_payload=metrics, normalized=metrics)

    async def persist(
        self,
        ctx: CollectorContext,
        result: CollectorResult,
        captured_at: datetime,
        source_fingerprint: str,
        *,
        team_id: uuid.UUID,
        window_size: int = 5,
        scope: str = "overall",
        **_: Any,
    ) -> SnapshotRef:
        snapshot = TeamFormSnapshot(
            team_id=team_id,
            as_of=captured_at,
            window_size=window_size,
            scope=scope,
            metrics_jsonb=dict(result.normalized),
            source_fingerprint=source_fingerprint,
        )
        async with ctx.session_factory() as session:
            session.add(snapshot)
            await session.commit()
        return SnapshotRef(
            table="team_form_snapshots", snapshot_id=snapshot.id, captured_at=captured_at
        )


register(StandingsCollector())
register(TeamStatisticsCollector())
register(AvailabilityCollector())
register(LineupCollector())
register(FormInputsCollector())
