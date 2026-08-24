from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sports_intelligence.collectors.freshness import FreshnessPolicy
from sports_intelligence.collectors.quota import QuotaManager
from sports_intelligence.core.config import Settings
from sports_intelligence.core.phases import ForecastPhase, FreshnessCategory
from sports_intelligence.db.models import (
    AvailabilitySnapshot,
    Fixture,
    LineupSnapshot,
    OddsSnapshotSet,
    StandingSnapshot,
    TeamStatisticsSnapshot,
)
from sports_intelligence.schemas.status import (
    CategoryStatus,
    FixtureStatusOut,
    SystemStatusOut,
)

router = APIRouter(tags=["status"])

_CONFIRMED = "CONFIRMED"


def _age_seconds(captured: datetime | None, now: datetime) -> int | None:
    if captured is None:
        return None
    if captured.tzinfo is None:
        captured = captured.replace(tzinfo=UTC)
    return int((now - captured).total_seconds())


async def _latest_snapshot(
    session: AsyncSession, model: Any, **filters: object
) -> tuple[datetime | None, UUID | None]:
    stmt = (
        select(model.captured_at, model.id)
        .where(*[getattr(model, k) == v for k, v in filters.items()])
        .order_by(model.captured_at.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    return (row[0], row[1]) if row else (None, None)


def _combined_status(
    policy: FreshnessPolicy,
    category: FreshnessCategory,
    latest_rows: list[tuple[datetime | None, UUID | None]],
    now: datetime,
    phase: ForecastPhase,
) -> CategoryStatus:
    """Both-team semantics: fresh only when EVERY requested side is
    fresh; stale when ANY side is stale; unknown when ALL are missing."""
    present = [captured for captured, _ in latest_rows if captured is not None]
    if not present:
        return CategoryStatus(captured_at=None, age_seconds=None, state="unknown")
    newest = max(present)
    any_stale = any(policy.is_stale(category, captured, now, phase) for captured in present)
    state = "stale" if any_stale else "fresh"
    return CategoryStatus(
        captured_at=newest,
        age_seconds=_age_seconds(newest, now),
        state=state,
    )


async def _fixture_freshness(
    session: AsyncSession,
    policy: FreshnessPolicy,
    now: datetime,
    *,
    fixture: Fixture,
) -> dict[str, CategoryStatus]:
    out: dict[str, CategoryStatus] = {}
    league_id = fixture.league_id
    team_ids = [fixture.home_team_id, fixture.away_team_id]
    phase = ForecastPhase.MORNING

    if league_id is not None:
        captured, _ = await _latest_snapshot(session, StandingSnapshot, league_id=league_id)
        out["standings"] = CategoryStatus(
            captured_at=captured,
            age_seconds=_age_seconds(captured, now),
            state=(
                "fresh"
                if not policy.is_stale(FreshnessCategory.STANDINGS, captured, now)
                else ("stale" if captured else "unknown")
            ),
        )

    # Team stats: BOTH teams must be fresh.
    team_rows: list[tuple[datetime | None, UUID | None]] = []
    for team_id in team_ids:
        team_rows.append(await _latest_snapshot(session, TeamStatisticsSnapshot, team_id=team_id))
    out["team_stats"] = _combined_status(
        policy, FreshnessCategory.TEAM_STATISTICS, team_rows, now, phase
    )

    # Availability + lineups: BOTH teams; lineups are publication-aware.
    availability_rows = [
        await _latest_snapshot(session, AvailabilitySnapshot, fixture_id=fixture.id, team_id=t)
        for t in team_ids
    ]
    out["availability"] = _combined_status(
        policy, FreshnessCategory.AVAILABILITY, availability_rows, now, phase
    )

    lineup_rows = [
        await _latest_snapshot(session, LineupSnapshot, fixture_id=fixture.id, team_id=t)
        for t in team_ids
    ]
    out["lineups"] = _combined_status(policy, FreshnessCategory.LINEUPS, lineup_rows, now, phase)

    odds_captured, _ = await _latest_snapshot(session, OddsSnapshotSet, fixture_id=fixture.id)
    out["odds"] = CategoryStatus(
        captured_at=odds_captured,
        age_seconds=_age_seconds(odds_captured, now),
        state=(
            "fresh"
            if not policy.is_stale(FreshnessCategory.ODDS, odds_captured, now)
            else ("stale" if odds_captured else "unknown")
        ),
    )
    return out


async def _lineup_confirmed_for_all_teams(
    session: AsyncSession, fixture_id: UUID, team_ids: list[UUID]
) -> bool:
    for team_id in team_ids:
        stmt = (
            select(LineupSnapshot.publication_state)
            .where(
                LineupSnapshot.fixture_id == fixture_id,
                LineupSnapshot.team_id == team_id,
            )
            .order_by(LineupSnapshot.captured_at.desc())
            .limit(1)
        )
        state = (await session.execute(stmt)).scalar_one_or_none()
        if state != _CONFIRMED:
            return False
    return True


@router.get("/v1/fixtures/{fixture_id}/status", response_model=FixtureStatusOut)
async def fixture_status(fixture_id: UUID, request: Request) -> FixtureStatusOut:
    settings: Settings = request.app.state.settings
    session_factory = request.app.state.session_factory
    now = datetime.now(UTC)
    policy = FreshnessPolicy(settings)

    from sqlalchemy.ext.asyncio import async_sessionmaker

    if not isinstance(session_factory, async_sessionmaker):
        raise RuntimeError("session factory not configured")

    quota = QuotaManager(settings, session_factory)
    daily_remaining, minute_remaining, degraded_mode = await quota.observe(
        provider=settings.sports_provider or "mock"
    )

    async with session_factory() as session:
        fixture = await session.get(Fixture, fixture_id)
        if fixture is None:
            raise HTTPException(status_code=404, detail="fixture not found")
        freshness = await _fixture_freshness(session, policy, now, fixture=fixture)
        team_ids = [fixture.home_team_id, fixture.away_team_id]
        lineup_confirmed = await _lineup_confirmed_for_all_teams(session, fixture.id, team_ids)

    return FixtureStatusOut(
        fixture_id=fixture.id,
        kickoff_at=fixture.kickoff_at,
        last_refresh={category: status.captured_at for category, status in freshness.items()},
        freshness=freshness,
        lineup_available=lineup_confirmed,
        degraded_mode=degraded_mode.value,
        quota_daily_remaining=daily_remaining,
        quota_minute_remaining=minute_remaining,
    )


@router.get("/v1/system/status", response_model=SystemStatusOut)
async def system_status(request: Request) -> SystemStatusOut:
    settings: Settings = request.app.state.settings
    session_factory = request.app.state.session_factory
    daily, minute = (None, None)
    mode = "NORMAL"
    from sqlalchemy.ext.asyncio import async_sessionmaker

    if isinstance(session_factory, async_sessionmaker):
        quota = QuotaManager(settings, session_factory)
        daily, minute, mode_obj = await quota.observe(provider=settings.sports_provider or "mock")
        mode = mode_obj.value
    return SystemStatusOut(
        scheduler_enabled=settings.scheduler_enabled,
        degradation_mode=mode,
        daily_remaining=daily,
        minute_remaining=minute,
    )
