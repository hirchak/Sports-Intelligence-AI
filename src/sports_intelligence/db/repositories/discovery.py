from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from sports_intelligence.db.models import (
    Fixture,
    League,
    ProviderEntityId,
    ProviderObservation,
    RawProviderPayload,
    Season,
    Team,
)

_TEAM_ARBITER_SQL = text(
    """
    WITH ins_map AS (
        INSERT INTO provider_entity_ids (id, provider, entity_type, external_id, internal_entity_id)
        VALUES (:internal_id, :provider, 'team', :external_id, :internal_id)
        ON CONFLICT (provider, entity_type, external_id) DO NOTHING
        RETURNING internal_entity_id
    ),
    ins_team AS (
        INSERT INTO teams (id, name)
        SELECT internal_entity_id, :name FROM ins_map
        RETURNING id
    ),
    existing AS (
        SELECT internal_entity_id FROM provider_entity_ids
        WHERE provider = :provider AND entity_type = 'team' AND external_id = :external_id
    )
    SELECT id FROM ins_team
    UNION ALL
    SELECT internal_entity_id FROM existing
    LIMIT 1
    """
)

_FIXTURE_ARBITER_SQL = text(
    """
    WITH ins_map AS (
        INSERT INTO provider_entity_ids (id, provider, entity_type, external_id, internal_entity_id)
        VALUES (:internal_id, :provider, 'fixture', :external_id, :internal_id)
        ON CONFLICT (provider, entity_type, external_id) DO NOTHING
        RETURNING internal_entity_id
    ),
    ins_fix AS (
        INSERT INTO fixtures (
            id, league_id, season_id, home_team_id, away_team_id,
            kickoff_at, venue, round, status
        )
        SELECT
            internal_entity_id, :league_id, :season_id, :home_team_id, :away_team_id,
            :kickoff_at, :venue, :round_name, :status
        FROM ins_map
        RETURNING id
    ),
    existing AS (
        SELECT internal_entity_id FROM provider_entity_ids
        WHERE provider = :provider AND entity_type = 'fixture' AND external_id = :external_id
    )
    SELECT id FROM ins_fix
    UNION ALL
    SELECT internal_entity_id FROM existing
    LIMIT 1
    """
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
            set_={"name": name, "country": country, "enabled": enabled},
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
    session: AsyncSession, provider: str, external_id: int, name: str | None
) -> tuple[uuid.UUID, bool]:
    internal_id = uuid.uuid4()
    for attempt in range(3):
        result = await session.execute(
            _TEAM_ARBITER_SQL,
            {
                "provider": provider,
                "external_id": str(external_id),
                "internal_id": internal_id,
                "name": name,
            },
        )
        row = result.first()
        if row is not None:
            resolved = row[0]
            created = resolved == internal_id
            if not created:
                await _sync_team_name(session, resolved, name)
            return resolved, created
        existing = await find_internal_id(session, provider, "team", external_id)
        if existing is not None:
            await _sync_team_name(session, existing, name)
            return existing, False
        await asyncio.sleep(0.01 * (attempt + 1))
    raise RuntimeError(
        f"team identity resolution failed for provider={provider!r} external_id={external_id}"
    )


async def _sync_team_name(session: AsyncSession, internal_id: uuid.UUID, name: str | None) -> None:
    if name is None:
        return
    team = await session.get(Team, internal_id)
    if team is not None and team.name != name:
        team.name = name
        await session.flush()


async def upsert_league_with_mapping(
    session: AsyncSession,
    provider: str,
    external_id: int,
    slug: str,
    name: str,
    country: str | None,
    enabled: bool,
) -> tuple[uuid.UUID, bool]:
    slug_row_id = await upsert_league_id(session, slug, name, country, enabled)
    await insert_entity_mapping(session, provider, "league", external_id, slug_row_id)
    await session.flush()
    internal_id = await find_internal_id(session, provider, "league", external_id)
    if internal_id is None:
        raise RuntimeError("league mapping resolution failed")
    return internal_id, internal_id == slug_row_id


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
    internal_id = uuid.uuid4()
    for attempt in range(3):
        result = await session.execute(
            _FIXTURE_ARBITER_SQL,
            {
                "provider": provider,
                "external_id": str(external_id),
                "internal_id": internal_id,
                "league_id": league_id,
                "season_id": season_id,
                "home_team_id": home_team_id,
                "away_team_id": away_team_id,
                "kickoff_at": kickoff_at,
                "venue": venue,
                "round_name": round_name,
                "status": status,
            },
        )
        row = result.first()
        if row is not None:
            resolved = row[0]
            created = resolved == internal_id
            if not created:
                await _refresh_fixture(
                    session, resolved, league_id, season_id, kickoff_at, venue, round_name, status
                )
            return resolved, created
        existing = await find_internal_id(session, provider, "fixture", external_id)
        if existing is not None:
            await _refresh_fixture(
                session, existing, league_id, season_id, kickoff_at, venue, round_name, status
            )
            return existing, False
        await asyncio.sleep(0.01 * (attempt + 1))
    raise RuntimeError(
        f"fixture identity resolution failed for provider={provider!r} external_id={external_id}"
    )


async def _refresh_fixture(
    session: AsyncSession,
    internal_id: uuid.UUID,
    league_id: uuid.UUID,
    season_id: uuid.UUID | None,
    kickoff_at: datetime,
    venue: str | None,
    round_name: str | None,
    status: str,
) -> None:
    fixture = await session.get(Fixture, internal_id)
    if fixture is not None:
        fixture.kickoff_at = kickoff_at
        fixture.status = status
        fixture.league_id = league_id
        fixture.season_id = season_id
        fixture.venue = venue
        fixture.round = round_name
        await session.flush()


async def store_raw_evidence(
    session: AsyncSession,
    provider: str,
    endpoint_family: str,
    request_fingerprint: str,
    payload_hash: str,
    payload: dict[str, Any],
    retrieved_at: datetime,
) -> bool:
    content_id, content_created = await _upsert_raw_content(
        session, provider, endpoint_family, payload_hash, payload
    )
    await session.execute(
        pg_insert(ProviderObservation).values(
            payload_id=content_id,
            provider=provider,
            endpoint_family=endpoint_family,
            request_fingerprint=request_fingerprint,
            retrieved_at=retrieved_at,
        )
    )
    return content_created


async def _upsert_raw_content(
    session: AsyncSession,
    provider: str,
    endpoint_family: str,
    payload_hash: str,
    payload: dict[str, Any],
) -> tuple[uuid.UUID, bool]:
    statement = (
        pg_insert(RawProviderPayload)
        .values(
            provider=provider,
            endpoint_family=endpoint_family,
            payload_hash=payload_hash,
            payload=payload,
        )
        .on_conflict_do_nothing(constraint="uq_raw_payloads_hash")
        .returning(RawProviderPayload.id)
    )
    row = (await session.execute(statement)).scalar_one_or_none()
    if row is not None:
        return row, True
    existing = await session.execute(
        select(RawProviderPayload.id).where(
            RawProviderPayload.provider == provider,
            RawProviderPayload.endpoint_family == endpoint_family,
            RawProviderPayload.payload_hash == payload_hash,
        )
    )
    return existing.scalar_one(), False
