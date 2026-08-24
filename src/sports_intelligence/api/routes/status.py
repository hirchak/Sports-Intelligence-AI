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
from sports_intelligence.core.phases import FreshnessCategory
from sports_intelligence.db.models import (
    AvailabilitySnapshot,
    Fixture,
    LineupSnapshot,
    OddsSnapshotSet,
    QuotaBucket,
    StandingSnapshot,
    TeamStatisticsSnapshot,
)
from sports_intelligence.schemas.status import (
    CategoryStatus,
    FixtureStatusOut,
    SystemStatusOut,
)

router = APIRouter(tags=["status"])


def _age_seconds(captured: datetime | None, now: datetime) -> int | None:
    if captured is None:
        return None
    if captured.tzinfo is None:
        captured = captured.replace(tzinfo=UTC)
    return int((now - captured).total_seconds())


async def _latest_captured(session: AsyncSession, model: Any, **filters: object) -> datetime | None:
    stmt = select(model.captured_at)
    for col, val in filters.items():
        stmt = stmt.where(getattr(model, col) == val)
    stmt = stmt.order_by(model.captured_at.desc()).limit(1)
    return (await session.execute(stmt)).scalar_one_or_none()


async def _freshness_snapshot(
    session: AsyncSession,
    policy: FreshnessPolicy,
    now: datetime,
    *,
    league_id: UUID | None = None,
    team_ids: list[UUID] | None = None,
    fixture_id: UUID | None = None,
) -> dict[str, CategoryStatus]:
    """Build the freshness dict for a fixture (or a league for standings)."""
    out: dict[str, CategoryStatus] = {}

    if league_id is not None:
        captured = await _latest_captured(session, StandingSnapshot, league_id=league_id)
        out["standings"] = CategoryStatus(
            captured_at=captured,
            age_seconds=_age_seconds(captured, now),
            state=(
                "fresh"
                if not policy.is_stale(FreshnessCategory.STANDINGS, captured, now)
                else ("stale" if captured else "unknown")
            ),
        )

    if team_ids:
        # Use the most recent across the team's snapshots as a coarse
        # overall signal (per-team stats are typically shared across
        # upcoming fixtures).
        captured = None
        for team_id in team_ids:
            row = await _latest_captured(session, TeamStatisticsSnapshot, team_id=team_id)
            if captured is None or (row is not None and row > captured):
                captured = row
        out["team_stats"] = CategoryStatus(
            captured_at=captured,
            age_seconds=_age_seconds(captured, now),
            state=(
                "fresh"
                if not policy.is_stale(FreshnessCategory.TEAM_STATISTICS, captured, now)
                else ("stale" if captured else "unknown")
            ),
        )

    if fixture_id is not None:
        captured = await _latest_captured(session, AvailabilitySnapshot, fixture_id=fixture_id)
        out["availability"] = CategoryStatus(
            captured_at=captured,
            age_seconds=_age_seconds(captured, now),
            state=(
                "fresh"
                if not policy.is_stale(FreshnessCategory.AVAILABILITY, captured, now)
                else ("stale" if captured else "unknown")
            ),
        )

        captured = await _latest_captured(session, LineupSnapshot, fixture_id=fixture_id)
        out["lineups"] = CategoryStatus(
            captured_at=captured,
            age_seconds=_age_seconds(captured, now),
            state=(
                "fresh"
                if not policy.is_stale(FreshnessCategory.LINEUPS, captured, now)
                else ("stale" if captured else "unknown")
            ),
        )

        captured = await _latest_captured(session, OddsSnapshotSet, fixture_id=fixture_id)
        out["odds"] = CategoryStatus(
            captured_at=captured,
            age_seconds=_age_seconds(captured, now),
            state=(
                "fresh"
                if not policy.is_stale(FreshnessCategory.ODDS, captured, now)
                else ("stale" if captured else "unknown")
            ),
        )

    return out


async def _quota_snapshot(session: AsyncSession, provider: str) -> tuple[int | None, int | None]:
    daily: int | None = None
    minute: int | None = None
    stmt = (
        select(QuotaBucket.remaining_value, QuotaBucket.window)
        .where(QuotaBucket.provider == provider)
        .order_by(QuotaBucket.observed_at.desc())
        .limit(10)
    )
    for remaining, window in (await session.execute(stmt)).all():
        if window == "daily" and daily is None:
            daily = int(remaining)
        elif window == "minute" and minute is None:
            minute = int(remaining)
    return daily, minute


@router.get("/v1/fixtures/{fixture_id}/status", response_model=FixtureStatusOut)
async def fixture_status(fixture_id: UUID, request: Request) -> FixtureStatusOut:
    settings: Settings = request.app.state.settings
    session_factory = request.app.state.session_factory
    now = datetime.now(UTC)
    policy = FreshnessPolicy(settings)

    from sqlalchemy.ext.asyncio import async_sessionmaker

    if not isinstance(session_factory, async_sessionmaker):
        raise RuntimeError("session factory not configured")

    async with session_factory() as session:
        fixture = await session.get(Fixture, fixture_id)
        if fixture is None:
            raise HTTPException(status_code=404, detail="fixture not found")

        freshness = await _freshness_snapshot(
            session,
            policy,
            now,
            league_id=fixture.league_id,
            team_ids=[fixture.home_team_id, fixture.away_team_id],
            fixture_id=fixture.id,
        )
        last_refresh = {category: status.captured_at for category, status in freshness.items()}

        # Compute quota snapshot from latest known bucket.
        quota = QuotaManager(settings, session_factory)
        decision = await quota.acquire(provider=settings.sports_provider or "mock", priority="P0")  # type: ignore[arg-type]
        daily_remaining = decision.remaining_daily
        minute_remaining = decision.remaining_minute
        degraded_mode = decision.mode.value

    # Decide whether lineups are "available" (any captured snapshot).
    lineup_available = any(
        status.captured_at is not None
        for status in [freshness.get("lineups")]
        if status is not None
    )
    return FixtureStatusOut(
        fixture_id=fixture.id,
        kickoff_at=fixture.kickoff_at,
        last_refresh=last_refresh,
        freshness=freshness,
        lineup_available=lineup_available,
        degraded_mode=degraded_mode,
        quota_daily_remaining=daily_remaining,
        quota_minute_remaining=minute_remaining,
    )


@router.get("/v1/system/status", response_model=SystemStatusOut)
async def system_status(request: Request) -> SystemStatusOut:
    settings: Settings = request.app.state.settings
    session_factory = request.app.state.session_factory
    daily, minute = (None, None)
    from sqlalchemy.ext.asyncio import async_sessionmaker

    if isinstance(session_factory, async_sessionmaker):
        async with session_factory() as session:
            daily, minute = await _quota_snapshot(session, settings.sports_provider or "mock")
    return SystemStatusOut(
        scheduler_enabled=settings.scheduler_enabled,
        degradation_mode="NORMAL",
        daily_remaining=daily,
        minute_remaining=minute,
    )
