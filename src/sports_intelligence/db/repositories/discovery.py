from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from sports_intelligence.db.models import (
    Fixture,
    League,
    ProviderEntityId,
    RawProviderPayload,
    Season,
    Team,
)


async def upsert_league_id(
    session: AsyncSession,
    slug: str,
    name: str,
    country: str | None,
    enabled: bool,
) -> uuid.UUID:
    statement = (
        pg_insert(League)
        .values(slug=slug, name=name, country=country, enabled=enabled)
        .on_conflict_do_update(
            index_elements=[League.slug],
            set_={"name": name, "country": country},
        )
        .returning(League.id)
    )
    row = (await session.execute(statement)).scalar_one()
    return row


async def upsert_season_id(
    session: AsyncSession, league_id: uuid.UUID, name: str
) -> tuple[uuid.UUID, bool]:
    statement = (
        pg_insert(Season)
        .values(league_id=league_id, name=name, active=True)
        .on_conflict_do_nothing(constraint="uq_seasons_league_name")
        .returning(Season.id)
    )
    row = (await session.execute(statement)).scalar_one_or_none()
    if row is not None:
        return row, True
    existing = await session.execute(
        select(Season.id).where(Season.league_id == league_id, Season.name == name)
    )
    return existing.scalar_one(), False


async def find_internal_id(
    session: AsyncSession, provider: str, entity_type: str, external_id: int
) -> uuid.UUID | None:
    result = await session.execute(
        select(ProviderEntityId.internal_entity_id).where(
            ProviderEntityId.provider == provider,
            ProviderEntityId.entity_type == entity_type,
            ProviderEntityId.external_id == str(external_id),
        )
    )
    return result.scalar_one_or_none()


async def insert_entity_mapping(
    session: AsyncSession,
    provider: str,
    entity_type: str,
    external_id: int,
    internal_entity_id: uuid.UUID,
) -> None:
    await session.execute(
        pg_insert(ProviderEntityId)
        .values(
            provider=provider,
            entity_type=entity_type,
            external_id=str(external_id),
            internal_entity_id=internal_entity_id,
        )
        .on_conflict_do_nothing(constraint="uq_provider_entity_ids_identity")
    )


async def get_or_create_team_id(
    session: AsyncSession, provider: str, external_id: int, name: str
) -> tuple[uuid.UUID, bool]:
    internal_id = await find_internal_id(session, provider, "team", external_id)
    if internal_id is not None:
        team = await session.get(Team, internal_id)
        if team is not None and team.name != name:
            team.name = name
            await session.flush()
        return internal_id, False
    team = Team(name=name)
    session.add(team)
    await session.flush()
    await insert_entity_mapping(session, provider, "team", external_id, team.id)
    return team.id, True


async def upsert_league_with_mapping(
    session: AsyncSession,
    provider: str,
    external_id: int,
    slug: str,
    name: str,
    country: str | None,
    enabled: bool,
) -> tuple[uuid.UUID, bool]:
    internal_id = await find_internal_id(session, provider, "league", external_id)
    if internal_id is not None:
        await upsert_league_id(session, slug, name, country, enabled)
        return internal_id, False
    league_id = await upsert_league_id(session, slug, name, country, enabled)
    await insert_entity_mapping(session, provider, "league", external_id, league_id)
    return league_id, True


async def upsert_fixture_id(
    session: AsyncSession,
    provider: str,
    external_id: int,
    league_id: uuid.UUID,
    season_id: uuid.UUID | None,
    home_team_id: uuid.UUID,
    away_team_id: uuid.UUID,
    kickoff_at: datetime,
    venue: str | None,
    round_name: str | None,
    status: str,
) -> tuple[uuid.UUID, bool]:
    internal_id = await find_internal_id(session, provider, "fixture", external_id)
    if internal_id is not None:
        fixture = await session.get(Fixture, internal_id)
        if fixture is not None:
            fixture.status = status
            if venue is not None:
                fixture.venue = venue
            if round_name is not None:
                fixture.round = round_name
            await session.flush()
        return internal_id, False
    fixture = Fixture(
        league_id=league_id,
        season_id=season_id,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        kickoff_at=kickoff_at,
        venue=venue,
        round=round_name,
        status=status,
    )
    session.add(fixture)
    await session.flush()
    await insert_entity_mapping(session, provider, "fixture", external_id, fixture.id)
    return fixture.id, True


async def store_raw_payload(
    session: AsyncSession,
    provider: str,
    endpoint_family: str,
    request_fingerprint: str,
    payload_hash: str,
    payload: dict[str, Any],
    retrieved_at: datetime,
) -> bool:
    statement = (
        pg_insert(RawProviderPayload)
        .values(
            provider=provider,
            endpoint_family=endpoint_family,
            request_fingerprint=request_fingerprint,
            payload_hash=payload_hash,
            payload=payload,
            retrieved_at=retrieved_at,
        )
        .on_conflict_do_nothing(constraint="uq_raw_payloads_hash")
    )
    result = await session.execute(statement)
    rowcount: int = getattr(result, "rowcount", 0)
    return rowcount == 1
