from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sports_intelligence.api.dependencies import get_session
from sports_intelligence.core.time import utc_window_for_local_day
from sports_intelligence.db.models import Fixture, League, Team
from sports_intelligence.schemas.fixtures import FixtureOut

router = APIRouter(prefix="/v1/fixtures", tags=["fixtures"])

SessionDependency = Annotated[AsyncSession, Depends(get_session)]


def _to_out(
    fixture: Fixture, league_slug: str, home_name: str | None, away_name: str | None
) -> FixtureOut:
    return FixtureOut(
        id=fixture.id,
        league_slug=league_slug,
        home_team=home_name,
        away_team=away_name,
        kickoff_at=fixture.kickoff_at,
        venue=fixture.venue,
        round=fixture.round,
        status=fixture.status,
    )


@router.get("", response_model=list[FixtureOut])
async def list_fixtures(
    request: Request,
    session: SessionDependency,
    date: date | None = None,
    league: str | None = None,
) -> list[FixtureOut]:
    home = Team.__table__.alias("home_team")
    away = Team.__table__.alias("away_team")
    statement = (
        select(Fixture, League.slug, home.c.name.label("home_name"), away.c.name.label("away_name"))
        .join(League, Fixture.league_id == League.id)
        .join(home, Fixture.home_team_id == home.c.id)
        .join(away, Fixture.away_team_id == away.c.id)
        .order_by(Fixture.kickoff_at)
    )
    if date is not None:
        settings = request.app.state.settings
        day_start, day_end = utc_window_for_local_day(date, settings.app_timezone)
        statement = statement.where(Fixture.kickoff_at >= day_start, Fixture.kickoff_at < day_end)
    if league is not None:
        statement = statement.where(League.slug == league)

    rows = (await session.execute(statement)).all()
    return [
        _to_out(fixture, league_slug, home_name, away_name)
        for fixture, league_slug, home_name, away_name in rows
    ]


@router.get("/{fixture_id}", response_model=FixtureOut)
async def get_fixture(fixture_id: uuid.UUID, session: SessionDependency) -> FixtureOut:
    home = Team.__table__.alias("home_team")
    away = Team.__table__.alias("away_team")
    statement = (
        select(Fixture, League.slug, home.c.name.label("home_name"), away.c.name.label("away_name"))
        .join(League, Fixture.league_id == League.id)
        .join(home, Fixture.home_team_id == home.c.id)
        .join(away, Fixture.away_team_id == away.c.id)
        .where(Fixture.id == fixture_id)
    )
    row = (await session.execute(statement)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="fixture not found")
    fixture, league_slug, home_name, away_name = row
    return _to_out(fixture, league_slug, home_name, away_name)
