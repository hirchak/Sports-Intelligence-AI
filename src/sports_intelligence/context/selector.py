from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sports_intelligence.core.phases import ForecastPhase
from sports_intelligence.db.models import (
    AvailabilitySnapshot,
    Fixture,
    League,
    LineupSnapshot,
    OddsPrice,
    OddsSnapshotSet,
    ProviderEntityId,
    StandingSnapshot,
    Team,
    TeamFormSnapshot,
    TeamStatisticsSnapshot,
)
from sports_intelligence.research.service import FixtureResearchView, get_research_for_fixture


@dataclass(frozen=True)
class SelectedFixtureInfo:
    fixture_id: uuid.UUID
    league_id: uuid.UUID
    season_id: uuid.UUID | None
    home_team_id: uuid.UUID
    away_team_id: uuid.UUID
    kickoff_at: datetime
    venue: str | None
    round: str | None
    status: str
    league_slug: str
    league_name: str
    home_team_name: str | None
    away_team_name: str | None
    home_external_id: str | None
    away_external_id: str | None


@dataclass(frozen=True)
class SelectedEvidence:
    fixture_id: uuid.UUID
    forecast_phase: ForecastPhase
    as_of: datetime
    fixture: SelectedFixtureInfo
    standings: StandingSnapshot | None
    home_team_stats: TeamStatisticsSnapshot | None
    away_team_stats: TeamStatisticsSnapshot | None
    home_form: TeamFormSnapshot | None
    away_form: TeamFormSnapshot | None
    home_availability: AvailabilitySnapshot | None
    away_availability: AvailabilitySnapshot | None
    home_lineup: LineupSnapshot | None
    away_lineup: LineupSnapshot | None
    odds_set: OddsSnapshotSet | None
    odds_prices: list[OddsPrice] = field(default_factory=list)
    prev_odds_set: OddsSnapshotSet | None = None
    prev_odds_prices: list[OddsPrice] = field(default_factory=list)
    research: FixtureResearchView | None = None


async def select_evidence(
    session: AsyncSession,
    *,
    fixture_id: uuid.UUID,
    forecast_phase: ForecastPhase,
    as_of: datetime,
    research_enabled: bool = True,
) -> SelectedEvidence:
    """Select point-in-time snapshot evidence strictly available at or before `as_of`.

    Enforces immutable point-in-time boundaries:
    - Never uses implicit datetime.now().
    - Rows with captured_at / as_of > requested as_of are strictly excluded.
    - Standings & Team Stats strictly match exact league and season_id.
    - Research uses accepted historical as_of point-in-time semantics (mode='latest_run').
    """
    as_of_utc = as_of.astimezone(UTC) if as_of.tzinfo else as_of.replace(tzinfo=UTC)

    # 1. Fixture Identity
    fix_stmt = (
        select(Fixture, League, Team, Team)
        .join(League, Fixture.league_id == League.id)
        .join(Team, Fixture.home_team_id == Team.id)
        .where(Fixture.id == fixture_id)
    )
    fix_row = (await session.execute(fix_stmt)).first()
    if fix_row is None:
        raise ValueError(f"Fixture {fixture_id} not found in database")

    fixture_obj, league_obj, home_team_obj, _ = fix_row
    # Query away team
    away_team_obj = await session.get(Team, fixture_obj.away_team_id)
    away_name = away_team_obj.name if away_team_obj else None

    # Resolve provider external IDs if present
    ext_stmt = select(ProviderEntityId).where(
        ProviderEntityId.entity_type == "team",
        ProviderEntityId.internal_entity_id.in_(
            [fixture_obj.home_team_id, fixture_obj.away_team_id]
        ),
    )
    ext_rows = (await session.execute(ext_stmt)).scalars().all()
    home_ext = next(
        (e.external_id for e in ext_rows if e.internal_entity_id == fixture_obj.home_team_id), None
    )
    away_ext = next(
        (e.external_id for e in ext_rows if e.internal_entity_id == fixture_obj.away_team_id), None
    )

    fixture_info = SelectedFixtureInfo(
        fixture_id=fixture_obj.id,
        league_id=league_obj.id,
        season_id=fixture_obj.season_id,
        home_team_id=fixture_obj.home_team_id,
        away_team_id=fixture_obj.away_team_id,
        kickoff_at=fixture_obj.kickoff_at,
        venue=fixture_obj.venue,
        round=fixture_obj.round,
        status=fixture_obj.status,
        league_slug=league_obj.slug,
        league_name=league_obj.name,
        home_team_name=home_team_obj.name if home_team_obj else None,
        away_team_name=away_name,
        home_external_id=home_ext,
        away_external_id=away_ext,
    )

    # 2. Standings (exact league + season, captured_at <= as_of)
    standings: StandingSnapshot | None = None
    if fixture_obj.season_id is not None:
        st_stmt = (
            select(StandingSnapshot)
            .where(
                StandingSnapshot.league_id == fixture_obj.league_id,
                StandingSnapshot.season_id == fixture_obj.season_id,
                StandingSnapshot.captured_at <= as_of_utc,
            )
            .order_by(StandingSnapshot.captured_at.desc())
            .limit(1)
        )
        standings = (await session.execute(st_stmt)).scalar_one_or_none()

    # 3. Team Statistics (exact team + league + season, captured_at <= as_of)
    home_team_stats: TeamStatisticsSnapshot | None = None
    away_team_stats: TeamStatisticsSnapshot | None = None
    if fixture_obj.season_id is not None:
        home_ts_stmt = (
            select(TeamStatisticsSnapshot)
            .where(
                TeamStatisticsSnapshot.team_id == fixture_obj.home_team_id,
                TeamStatisticsSnapshot.league_id == fixture_obj.league_id,
                TeamStatisticsSnapshot.season_id == fixture_obj.season_id,
                TeamStatisticsSnapshot.captured_at <= as_of_utc,
            )
            .order_by(TeamStatisticsSnapshot.captured_at.desc())
            .limit(1)
        )
        home_team_stats = (await session.execute(home_ts_stmt)).scalar_one_or_none()

        away_ts_stmt = (
            select(TeamStatisticsSnapshot)
            .where(
                TeamStatisticsSnapshot.team_id == fixture_obj.away_team_id,
                TeamStatisticsSnapshot.league_id == fixture_obj.league_id,
                TeamStatisticsSnapshot.season_id == fixture_obj.season_id,
                TeamStatisticsSnapshot.captured_at <= as_of_utc,
            )
            .order_by(TeamStatisticsSnapshot.captured_at.desc())
            .limit(1)
        )
        away_team_stats = (await session.execute(away_ts_stmt)).scalar_one_or_none()

    # 4. Team Form (exact team, as_of <= requested as_of)
    home_form_stmt = (
        select(TeamFormSnapshot)
        .where(
            TeamFormSnapshot.team_id == fixture_obj.home_team_id,
            TeamFormSnapshot.as_of <= as_of_utc,
        )
        .order_by(TeamFormSnapshot.as_of.desc())
        .limit(1)
    )
    home_form = (await session.execute(home_form_stmt)).scalar_one_or_none()

    away_form_stmt = (
        select(TeamFormSnapshot)
        .where(
            TeamFormSnapshot.team_id == fixture_obj.away_team_id,
            TeamFormSnapshot.as_of <= as_of_utc,
        )
        .order_by(TeamFormSnapshot.as_of.desc())
        .limit(1)
    )
    away_form = (await session.execute(away_form_stmt)).scalar_one_or_none()

    # 5. Availability (exact fixture + team, captured_at <= as_of)
    home_avail_stmt = (
        select(AvailabilitySnapshot)
        .where(
            AvailabilitySnapshot.fixture_id == fixture_id,
            AvailabilitySnapshot.team_id == fixture_obj.home_team_id,
            AvailabilitySnapshot.captured_at <= as_of_utc,
        )
        .order_by(AvailabilitySnapshot.captured_at.desc())
        .limit(1)
    )
    home_availability = (await session.execute(home_avail_stmt)).scalar_one_or_none()

    away_avail_stmt = (
        select(AvailabilitySnapshot)
        .where(
            AvailabilitySnapshot.fixture_id == fixture_id,
            AvailabilitySnapshot.team_id == fixture_obj.away_team_id,
            AvailabilitySnapshot.captured_at <= as_of_utc,
        )
        .order_by(AvailabilitySnapshot.captured_at.desc())
        .limit(1)
    )
    away_availability = (await session.execute(away_avail_stmt)).scalar_one_or_none()

    # 6. Lineups (exact fixture + team, captured_at <= as_of)
    home_lineup_stmt = (
        select(LineupSnapshot)
        .where(
            LineupSnapshot.fixture_id == fixture_id,
            LineupSnapshot.team_id == fixture_obj.home_team_id,
            LineupSnapshot.captured_at <= as_of_utc,
        )
        .order_by(LineupSnapshot.captured_at.desc())
        .limit(1)
    )
    home_lineup = (await session.execute(home_lineup_stmt)).scalar_one_or_none()

    away_lineup_stmt = (
        select(LineupSnapshot)
        .where(
            LineupSnapshot.fixture_id == fixture_id,
            LineupSnapshot.team_id == fixture_obj.away_team_id,
            LineupSnapshot.captured_at <= as_of_utc,
        )
        .order_by(LineupSnapshot.captured_at.desc())
        .limit(1)
    )
    away_lineup = (await session.execute(away_lineup_stmt)).scalar_one_or_none()

    # 7. Odds (latest captured_at <= as_of, and prior compatible set for movement)
    odds_stmt = (
        select(OddsSnapshotSet)
        .where(
            OddsSnapshotSet.fixture_id == fixture_id,
            OddsSnapshotSet.captured_at <= as_of_utc,
        )
        .order_by(OddsSnapshotSet.captured_at.desc())
        .limit(1)
    )
    odds_set = (await session.execute(odds_stmt)).scalar_one_or_none()

    odds_prices: list[OddsPrice] = []
    prev_odds_set: OddsSnapshotSet | None = None
    prev_odds_prices: list[OddsPrice] = []

    if odds_set is not None:
        prices_stmt = select(OddsPrice).where(OddsPrice.snapshot_set_id == odds_set.id)
        odds_prices = list((await session.execute(prices_stmt)).scalars().all())

        # Find previous odds snapshot set strictly earlier than latest captured_at
        prev_stmt = (
            select(OddsSnapshotSet)
            .where(
                OddsSnapshotSet.fixture_id == fixture_id,
                OddsSnapshotSet.captured_at < odds_set.captured_at,
            )
            .order_by(OddsSnapshotSet.captured_at.desc())
            .limit(1)
        )
        prev_odds_set = (await session.execute(prev_stmt)).scalar_one_or_none()
        if prev_odds_set is not None:
            prev_prices_stmt = select(OddsPrice).where(
                OddsPrice.snapshot_set_id == prev_odds_set.id
            )
            prev_odds_prices = list((await session.execute(prev_prices_stmt)).scalars().all())

    # 8. Web Research (mode='latest_run', retrieved_at/published_at/extracted_at <= as_of)
    research_view = await get_research_for_fixture(
        session,
        fixture_id,
        as_of=as_of_utc,
        mode="latest_run",
        capability_enabled=research_enabled,
    )

    return SelectedEvidence(
        fixture_id=fixture_id,
        forecast_phase=forecast_phase,
        as_of=as_of_utc,
        fixture=fixture_info,
        standings=standings,
        home_team_stats=home_team_stats,
        away_team_stats=away_team_stats,
        home_form=home_form,
        away_form=away_form,
        home_availability=home_availability,
        away_availability=away_availability,
        home_lineup=home_lineup,
        away_lineup=away_lineup,
        odds_set=odds_set,
        odds_prices=odds_prices,
        prev_odds_set=prev_odds_set,
        prev_odds_prices=prev_odds_prices,
        research=research_view,
    )
