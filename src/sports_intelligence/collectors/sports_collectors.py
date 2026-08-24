"""Sports collectors (M4.1): provider-backed, team-split, window-aware.

Hard rules enforced here:

- data comes from the configured `SportsDataProvider` ONLY; the mock
  provider lives behind the same typed boundary and canned payloads can
  never appear under a non-mock provider name;
- internal UUIDs are resolved to provider external ids via
  `provider_entity_ids` before any provider call;
- availability/lineups use ONE provider request per fixture and persist
  ONE snapshot PER TEAM from that single observation (never merged);
- lineup persistence distinguishes NOT_YET_PUBLISHED / CONFIRMED /
  UNSUPPORTED / PROVIDER_ERROR; corrections append new snapshots;
- form inputs derive deterministic last-5/last-10 outcomes from
  completed fixtures — no LLM anywhere.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sports_intelligence.collectors.framework import (
    CollectorContext,
    CollectorResult,
    SnapshotRef,
    register,
)
from sports_intelligence.collectors.ids import resolve_external_id
from sports_intelligence.core.phases import FreshnessCategory, Priority
from sports_intelligence.db.models import (
    AvailabilitySnapshot,
    LineupSnapshot,
    StandingSnapshot,
    TeamFormSnapshot,
    TeamStatisticsSnapshot,
)
from sports_intelligence.db.models import (
    Fixture as FixtureModel,
)
from sports_intelligence.providers.base import SportsDataProvider

# Deterministic pre-kickoff polling policy for lineups/availability.
_LINEUP_STATES = {"NOT_YET_PUBLISHED", "CONFIRMED", "UNSUPPORTED", "PROVIDER_ERROR"}


def lineup_poll_due(
    *,
    kickoff_at: datetime,
    now: datetime,
    windows_minutes: list[int],
    latest_state: str | None,
    latest_captured_at: datetime | None,
) -> bool:
    """State-aware pre-kickoff polling decision.

    - already-started fixtures are never polled;
    - a CONFIRMED lineup stops all normal polling;
    - within an active T-window a refresh is due once per window even if
      an earlier window produced NOT_YET_PUBLISHED (a 24h TTL must not
      suppress the T-60/T-20 checks);
    - outside every window there is nothing to do.
    """
    kickoff = _aware(kickoff_at)
    moment = _aware(now)
    minutes_to_kickoff = (kickoff - moment).total_seconds() / 60.0
    if minutes_to_kickoff <= 0:
        return False
    if latest_state == "CONFIRMED":
        return False
    # The smallest window the fixture is inside of (most restrictive).
    windows = sorted(w for w in windows_minutes if w > 0)
    current_window = next((w for w in windows if minutes_to_kickoff <= w), None)
    if current_window is None:
        return False
    if latest_captured_at is None:
        return True
    window_opened_at = kickoff - timedelta(minutes=current_window)
    return _aware(latest_captured_at) < window_opened_at


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class _ResolverMixin:
    def _sports_provider(self, ctx: CollectorContext) -> SportsDataProvider:
        if not isinstance(ctx.provider, SportsDataProvider):
            raise RuntimeError("sports collector requires a SportsDataProvider context")
        return ctx.provider

    async def _external_fixture_id(
        self, session: AsyncSession, ctx: CollectorContext, fixture_id: uuid.UUID
    ) -> int:
        return await resolve_external_id(
            session, provider=ctx.provider_name(), entity_type="fixture", internal_id=fixture_id
        )

    async def _external_team_id(
        self, session: AsyncSession, ctx: CollectorContext, team_id: uuid.UUID
    ) -> int:
        return await resolve_external_id(
            session, provider=ctx.provider_name(), entity_type="team", internal_id=team_id
        )

    async def _external_league_id(
        self, session: AsyncSession, ctx: CollectorContext, league_id: uuid.UUID
    ) -> int:
        return await resolve_external_id(
            session, provider=ctx.provider_name(), entity_type="league", internal_id=league_id
        )

    async def _season_number(self, session: AsyncSession, league_id: uuid.UUID) -> int | None:
        from sports_intelligence.db.models import Season

        stmt = (
            select(Season.name)
            .where(Season.league_id == league_id, Season.active == True)  # noqa: E712
            .limit(1)
        )
        value = (await session.execute(stmt)).scalar_one_or_none()
        if value is None:
            return None
        try:
            return int(str(value).split("/")[0])
        except ValueError:
            return None


class StandingsCollector(_ResolverMixin):
    name = "standings"
    category = FreshnessCategory.STANDINGS
    priority = Priority.P2

    def lock_key(
        self, *, league_id: uuid.UUID, season_id: uuid.UUID | None = None, **_: object
    ) -> str:
        return f"standings:{league_id}:{season_id or 'no-season'}"

    async def latest_snapshot(
        self,
        session: AsyncSession,
        *,
        league_id: uuid.UUID,
        season_id: uuid.UUID | None = None,
        **_: object,
    ) -> tuple[datetime | None, uuid.UUID | None]:
        stmt = (
            select(StandingSnapshot.captured_at, StandingSnapshot.id)
            .where(
                StandingSnapshot.league_id == league_id,
                *([StandingSnapshot.season_id == season_id] if season_id else [True]),
            )
            .order_by(StandingSnapshot.captured_at.desc())
            .limit(1)
        )
        row = (await session.execute(stmt)).first()
        return (row[0], row[1]) if row else (None, None)

    async def fetch(
        self, ctx: CollectorContext, *, league_id: uuid.UUID, **_: object
    ) -> CollectorResult:
        async with ctx.session_factory() as session:
            external_league = await self._external_league_id(session, ctx, league_id)
            season = await self._season_number(session, league_id)
        result = await self._sports_provider(ctx).get_standings(
            provider_league_id=external_league, season=season
        )
        return CollectorResult(
            raw_payload=result.raw_payload,
            normalized={"rows": [row.model_dump(mode="json") for row in result.rows]},
            rate_headers=result.rate_headers,
            retrieved_at=result.retrieved_at,
        )

    async def persist(
        self,
        ctx: CollectorContext,
        result: CollectorResult,
        *,
        captured_at: datetime,
        source_fingerprint: str,
        payload_id: uuid.UUID | None,
        league_id: uuid.UUID,
        season_id: uuid.UUID | None = None,
        **_inputs: object,
    ) -> tuple[SnapshotRef, ...]:
        rows = [row for row in result.normalized.get("rows", []) if isinstance(row, dict)]
        snapshot = StandingSnapshot(
            provider=ctx.provider_name(),
            league_id=league_id,
            season_id=season_id,
            captured_at=captured_at,
            source_fingerprint=source_fingerprint,
            payload_id=payload_id,
            rows_jsonb=rows,
            updated_at=datetime.now(UTC),
        )
        async with ctx.session_factory() as session, session.begin():
            session.add(snapshot)
        return (
            SnapshotRef(
                table="standings_snapshots",
                snapshot_id=snapshot.id,
                captured_at=captured_at,
            ),
        )


class TeamStatisticsCollector(_ResolverMixin):
    name = "team_stats"
    category = FreshnessCategory.TEAM_STATISTICS
    priority = Priority.P2

    def lock_key(
        self,
        *,
        team_id: uuid.UUID,
        league_id: uuid.UUID,
        season_id: uuid.UUID | None = None,
        **_: object,
    ) -> str:
        return f"team_stats:{team_id}:{league_id}:{season_id or 'no-season'}"

    async def latest_snapshot(
        self,
        session: AsyncSession,
        *,
        team_id: uuid.UUID,
        league_id: uuid.UUID,
        season_id: uuid.UUID | None = None,
        **_: object,
    ) -> tuple[datetime | None, uuid.UUID | None]:
        stmt = (
            select(TeamStatisticsSnapshot.captured_at, TeamStatisticsSnapshot.id)
            .where(
                TeamStatisticsSnapshot.team_id == team_id,
                TeamStatisticsSnapshot.league_id == league_id,
            )
            .order_by(TeamStatisticsSnapshot.captured_at.desc())
            .limit(1)
        )
        row = (await session.execute(stmt)).first()
        return (row[0], row[1]) if row else (None, None)

    async def fetch(
        self,
        ctx: CollectorContext,
        *,
        team_id: uuid.UUID,
        league_id: uuid.UUID,
        **_: object,
    ) -> CollectorResult:
        async with ctx.session_factory() as session:
            external_team = await self._external_team_id(session, ctx, team_id)
            external_league = await self._external_league_id(session, ctx, league_id)
            season = await self._season_number(session, league_id)
        result = await self._sports_provider(ctx).get_team_statistics(
            provider_team_id=external_team,
            provider_league_id=external_league,
            season=season,
        )
        return CollectorResult(
            raw_payload=result.raw_payload,
            normalized={"metrics": result.metrics},
            rate_headers=result.rate_headers,
            retrieved_at=result.retrieved_at,
        )

    async def persist(
        self,
        ctx: CollectorContext,
        result: CollectorResult,
        *,
        captured_at: datetime,
        source_fingerprint: str,
        payload_id: uuid.UUID | None,
        team_id: uuid.UUID,
        league_id: uuid.UUID,
        season_id: uuid.UUID | None = None,
        **_inputs: object,
    ) -> tuple[SnapshotRef, ...]:
        metrics = result.normalized.get("metrics", {})
        snapshot = TeamStatisticsSnapshot(
            provider=ctx.provider_name(),
            team_id=team_id,
            league_id=league_id,
            season_id=season_id,
            captured_at=captured_at,
            source_fingerprint=source_fingerprint,
            payload_id=payload_id,
            metrics_jsonb=dict(metrics),
            updated_at=datetime.now(UTC),
        )
        async with ctx.session_factory() as session, session.begin():
            session.add(snapshot)
        return (
            SnapshotRef(
                table="team_statistics_snapshots",
                snapshot_id=snapshot.id,
                captured_at=captured_at,
                team_id=team_id,
            ),
        )


async def _internal_team_for_external(
    session: AsyncSession, provider: str, external_team_id: int
) -> uuid.UUID | None:
    from sports_intelligence.db.models import ProviderEntityId

    stmt = select(ProviderEntityId.internal_entity_id).where(
        ProviderEntityId.provider == provider,
        ProviderEntityId.entity_type == "team",
        ProviderEntityId.external_id == str(external_team_id),
    )
    row = (await session.execute(stmt)).first()
    return row[0] if row else None


class AvailabilityCollector(_ResolverMixin):
    """One provider request per fixture → ONE snapshot PER TEAM.

    A single normalized result carries explicit team identity; this
    persist writes separated home/away snapshots from the SAME
    observation (never concatenating squads).
    """

    name = "availability"
    category = FreshnessCategory.AVAILABILITY
    priority = Priority.P1

    def lock_key(self, *, fixture_id: uuid.UUID, **_: object) -> str:
        # Fixture-level lock: home+away share one provider call.
        return f"availability:{fixture_id}"

    async def latest_snapshot(
        self,
        session: AsyncSession,
        *,
        fixture_id: uuid.UUID,
        team_id: uuid.UUID,
        **_: object,
    ) -> tuple[datetime | None, uuid.UUID | None]:
        stmt = (
            select(AvailabilitySnapshot.captured_at, AvailabilitySnapshot.id)
            .where(
                AvailabilitySnapshot.fixture_id == fixture_id,
                AvailabilitySnapshot.team_id == team_id,
            )
            .order_by(AvailabilitySnapshot.captured_at.desc())
            .limit(1)
        )
        row = (await session.execute(stmt)).first()
        return (row[0], row[1]) if row else (None, None)

    async def fetch(
        self, ctx: CollectorContext, *, fixture_id: uuid.UUID, **_: object
    ) -> CollectorResult:
        async with ctx.session_factory() as session:
            external_fixture = await self._external_fixture_id(session, ctx, fixture_id)
        result = await self._sports_provider(ctx).get_availability(
            provider_fixture_id=external_fixture
        )
        return CollectorResult(
            raw_payload=result.raw_payload,
            normalized={
                "teams": [team.model_dump(mode="json") for team in result.teams],
            },
            rate_headers=result.rate_headers,
            retrieved_at=result.retrieved_at,
        )

    async def persist(
        self,
        ctx: CollectorContext,
        result: CollectorResult,
        *,
        captured_at: datetime,
        source_fingerprint: str,
        payload_id: uuid.UUID | None,
        fixture_id: uuid.UUID,
        team_id: uuid.UUID,
        **_inputs: object,
    ) -> tuple[SnapshotRef, ...]:
        teams_data = [t for t in result.normalized.get("teams", []) if isinstance(t, dict)]

        async with ctx.session_factory() as session:
            exists = await session.get(FixtureModel, fixture_id)
            if exists is None:
                raise LookupError(f"fixture {fixture_id} not found for availability persist")

            refs: list[SnapshotRef] = []
            persisted_internal: set[uuid.UUID] = set()
            for team in teams_data:
                ext_team_id = int(team["provider_team_id"])
                internal = await _internal_team_for_external(
                    session, ctx.provider_name(), ext_team_id
                )
                row_team_id = internal or team_id
                if row_team_id in persisted_internal:
                    continue
                persisted_internal.add(row_team_id)
                entries = [e for e in team.get("entries", []) if isinstance(e, dict)]
                missing = [e for e in entries if e.get("missing")]
                state = "UNKNOWN" if not entries else ("KNOWN_PRESENT" if missing else "KNOWN_NONE")
                impact_flags = [
                    str(e["player_name"])
                    for e in entries
                    if e.get("missing") and e.get("player_name")
                ]
                snapshot = AvailabilitySnapshot(
                    provider=ctx.provider_name(),
                    fixture_id=fixture_id,
                    team_id=row_team_id,
                    captured_at=captured_at,
                    payload_id=payload_id,
                    players_jsonb=entries,
                    impact_flags_jsonb=impact_flags,
                    conflicts_jsonb=[],
                    availability_state=state,
                )
                session.add(snapshot)
                await session.flush()
                refs.append(
                    SnapshotRef(
                        table="availability_snapshots",
                        snapshot_id=snapshot.id,
                        captured_at=captured_at,
                        team_id=row_team_id,
                    )
                )

            # The requested side produced no provider entry at all →
            # still store an UNKNOWN observation bound to it so the
            # freshness view never confuses silence with healthy.
            if team_id not in persisted_internal:
                snapshot = AvailabilitySnapshot(
                    provider=ctx.provider_name(),
                    fixture_id=fixture_id,
                    team_id=team_id,
                    captured_at=captured_at,
                    payload_id=payload_id,
                    players_jsonb=[],
                    impact_flags_jsonb=[],
                    conflicts_jsonb=[],
                    availability_state="UNKNOWN",
                )
                session.add(snapshot)
                refs.append(
                    SnapshotRef(
                        table="availability_snapshots",
                        snapshot_id=snapshot.id,
                        captured_at=captured_at,
                        team_id=team_id,
                    )
                )
            await session.commit()
        return tuple(refs)


class LineupCollector(_ResolverMixin):
    """One provider request per fixture → per-team snapshots with
    explicit publication semantics."""

    name = "lineups"
    category = FreshnessCategory.LINEUPS
    priority = Priority.P1

    def lock_key(self, *, fixture_id: uuid.UUID, **_: object) -> str:
        return f"lineups:{fixture_id}"

    async def latest_snapshot(
        self,
        session: AsyncSession,
        *,
        fixture_id: uuid.UUID,
        team_id: uuid.UUID,
        **_: object,
    ) -> tuple[datetime | None, uuid.UUID | None]:
        stmt = (
            select(LineupSnapshot.captured_at, LineupSnapshot.id)
            .where(
                LineupSnapshot.fixture_id == fixture_id,
                LineupSnapshot.team_id == team_id,
            )
            .order_by(LineupSnapshot.captured_at.desc())
            .limit(1)
        )
        row = (await session.execute(stmt)).first()
        if row is None:
            return None, None
        return (row[0], row[1]) if row else (None, None)

    async def fetch(
        self, ctx: CollectorContext, *, fixture_id: uuid.UUID, **_: object
    ) -> CollectorResult:
        async with ctx.session_factory() as session:
            external_fixture = await self._external_fixture_id(session, ctx, fixture_id)
        result = await self._sports_provider(ctx).get_lineups(provider_fixture_id=external_fixture)
        return CollectorResult(
            raw_payload=result.raw_payload,
            normalized={
                "publication_state": result.publication_state.value,
                "teams": [team.model_dump(mode="json") for team in result.teams],
            },
            rate_headers=result.rate_headers,
            retrieved_at=result.retrieved_at,
        )

    async def persist(
        self,
        ctx: CollectorContext,
        result: CollectorResult,
        *,
        captured_at: datetime,
        source_fingerprint: str,
        payload_id: uuid.UUID | None,
        fixture_id: uuid.UUID,
        team_id: uuid.UUID,
        **_inputs: object,
    ) -> tuple[SnapshotRef, ...]:
        publication_state = str(result.normalized.get("publication_state", "UNKNOWN"))
        if publication_state not in _LINEUP_STATES:
            publication_state = "PROVIDER_ERROR"
        teams_data = [t for t in result.normalized.get("teams", []) if isinstance(t, dict)]
        confirmed_flag = publication_state == "CONFIRMED"
        formation = None
        players: list[dict[str, Any]] = []
        persist_team_id = team_id

        async with ctx.session_factory() as session:
            exists = await session.get(FixtureModel, fixture_id)
            if exists is None:
                raise LookupError(f"fixture {fixture_id} not found for lineup persist")

            if teams_data:
                target = None
                for candidate in teams_data:
                    ext_team_id = int(candidate.get("provider_team_id", -1))
                    internal = await _internal_team_for_external(
                        session, ctx.provider_name(), ext_team_id
                    )
                    if internal == team_id:
                        target = candidate
                        break
                if target is None:
                    # Requested team not published yet in this response.
                    target = None
                else:
                    formation = target.get("formation")
                    starters = target.get("starters", [])
                    substitutes = target.get("substitutes", [])
                    players = [p for p in [*starters, *substitutes] if isinstance(p, dict)]
                    confirmed_flag = bool(target.get("confirmed", confirmed_flag))
                    ext_team_id = int(target["provider_team_id"])
                    internal_for_ext = await _internal_team_for_external(
                        session, ctx.provider_name(), ext_team_id
                    )
                    persist_team_id = internal_for_ext or team_id

            # NOT_YET_PUBLISHED / UNSUPPORTED / PROVIDER_ERROR still store
            # an immutable observation bound to the requesting team.
            snapshot = LineupSnapshot(
                provider=ctx.provider_name(),
                fixture_id=fixture_id,
                team_id=persist_team_id,
                captured_at=captured_at,
                payload_id=payload_id,
                confirmed=confirmed_flag,
                formation=formation,
                players_jsonb=players,
                publication_state=publication_state if not teams_data else "CONFIRMED",
            )
            session.add(snapshot)
            await session.commit()
        return (
            SnapshotRef(
                table="lineup_snapshots",
                snapshot_id=snapshot.id,
                captured_at=captured_at,
                team_id=persist_team_id,
            ),
        )


class FormInputsCollector(_ResolverMixin):
    """Deterministic completed-result inputs for future last-5/last-10.

    Persists normalized completed fixture history per team; outcome
    letters (W/D/L) computed locally from goals — no settlement logic,
    no LLM.
    """

    name = "form_inputs"
    category = FreshnessCategory.TEAM_FORM
    priority = Priority.P2

    def lock_key(
        self, *, team_id: uuid.UUID, window_size: int = 5, scope: str = "overall", **_: object
    ) -> str:
        return f"form:{team_id}:{window_size}:{scope}"

    async def latest_snapshot(
        self,
        session: AsyncSession,
        *,
        team_id: uuid.UUID,
        window_size: int = 5,
        scope: str = "overall",
        **_: object,
    ) -> tuple[datetime | None, uuid.UUID | None]:
        stmt = (
            select(TeamFormSnapshot.as_of, TeamFormSnapshot.id)
            .where(
                TeamFormSnapshot.team_id == team_id,
                TeamFormSnapshot.window_size == window_size,
                TeamFormSnapshot.scope == scope,
            )
            .order_by(TeamFormSnapshot.as_of.desc())
            .limit(1)
        )
        row = (await session.execute(stmt)).first()
        return (row[0], row[1]) if row else (None, None)

    async def fetch(
        self,
        ctx: CollectorContext,
        *,
        team_id: uuid.UUID,
        window_size: int = 5,
        scope: str = "overall",
        **_: object,
    ) -> CollectorResult:
        del scope
        async with ctx.session_factory() as session:
            external_team = await self._external_team_id(session, ctx, team_id)
        result = await self._sports_provider(ctx).get_completed_fixtures(
            provider_team_id=external_team, last_n=max(window_size + 5, 10)
        )
        outcomes: list[dict[str, Any]] = []
        for fx in result.fixtures:
            if fx.home_goals is None or fx.away_goals is None:
                continue
            is_home = fx.provider_home_team_id == external_team
            goals_for = fx.home_goals if is_home else fx.away_goals
            goals_against = fx.away_goals if is_home else fx.home_goals
            letter = (
                "W" if goals_for > goals_against else ("D" if goals_for == goals_against else "L")
            )
            opponent_ext = fx.provider_away_team_id if is_home else fx.provider_home_team_id
            outcomes.append(
                {
                    "provider_fixture_id": fx.provider_fixture_id,
                    "kickoff_utc": fx.kickoff_utc.isoformat(),
                    "opponent_provider_team_id": opponent_ext,
                    "goals_for": goals_for,
                    "goals_against": goals_against,
                    "outcome": letter,
                    "status": fx.status_short,
                }
            )
        outcomes.sort(key=lambda item: item["kickoff_utc"], reverse=True)
        normalized = {
            "outcomes": outcomes[:window_size],
            "history": outcomes,
            "computed_locally": True,
        }
        return CollectorResult(
            raw_payload=result.raw_payload,
            normalized=normalized,
            rate_headers=result.rate_headers,
            retrieved_at=result.retrieved_at,
        )

    async def persist(
        self,
        ctx: CollectorContext,
        result: CollectorResult,
        *,
        captured_at: datetime,
        source_fingerprint: str,
        payload_id: uuid.UUID | None,
        team_id: uuid.UUID,
        window_size: int = 5,
        scope: str = "overall",
        **_inputs: object,
    ) -> tuple[SnapshotRef, ...]:
        snapshot = TeamFormSnapshot(
            team_id=team_id,
            as_of=captured_at,
            window_size=window_size,
            scope=scope,
            metrics_jsonb=dict(result.normalized),
            source_fingerprint=source_fingerprint,
        )
        async with ctx.session_factory() as session, session.begin():
            session.add(snapshot)
        return (
            SnapshotRef(
                table="team_form_snapshots",
                snapshot_id=snapshot.id,
                captured_at=captured_at,
                team_id=team_id,
            ),
        )


register(StandingsCollector())
register(TeamStatisticsCollector())
register(AvailabilityCollector())
register(LineupCollector())
register(FormInputsCollector())
