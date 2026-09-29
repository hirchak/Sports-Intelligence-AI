from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import async_sessionmaker

from sports_intelligence.db.models import Fixture
from sports_intelligence.research.service import get_research_for_fixture
from sports_intelligence.schemas.research import FixtureResearchOut

router = APIRouter(tags=["research"])


@router.get("/v1/fixtures/{fixture_id}/research", response_model=FixtureResearchOut)
async def fixture_research(
    fixture_id: UUID,
    request: Request,
    as_of: Annotated[
        datetime | None,
        Query(
            description="Point-in-time timestamp for anti-leakage audit / historical replay",
        ),
    ] = None,
    mode: Annotated[
        str,
        Query(
            description="Research evidence retrieval mode: 'latest_run' (default) or 'accumulated'",
        ),
    ] = "latest_run",
) -> FixtureResearchOut:
    session_factory = request.app.state.session_factory
    if not isinstance(session_factory, async_sessionmaker):
        raise RuntimeError("session factory not configured")

    async with session_factory() as session:
        fixture = await session.get(Fixture, fixture_id)
        if fixture is None:
            raise HTTPException(status_code=404, detail="fixture not found")

        view = await get_research_for_fixture(session, fixture_id, as_of=as_of, mode=mode)

    return FixtureResearchOut.model_validate(view)
