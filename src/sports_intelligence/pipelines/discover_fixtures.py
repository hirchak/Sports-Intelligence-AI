from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sports_intelligence.core.job_status import JobStatus
from sports_intelligence.core.league_config import LeagueConfig, LeagueConfigEntry
from sports_intelligence.db.models import Job
from sports_intelligence.db.repositories.discovery import (
    get_or_create_team_id,
    store_raw_evidence,
    upsert_fixture_id,
    upsert_league_with_mapping,
    upsert_season_id,
)
from sports_intelligence.providers.base import SportsDataProvider


class DiscoverySummary(BaseModel):
    date: date
    provider: str
    fixtures_received: int
    fixtures_eligible: int
    fixtures_created: int
    fixtures_updated: int
    leagues_processed: int
    seasons_created: int
    teams_created: int
    raw_payload_stored: bool


class FixtureDiscoveryService:
    def __init__(
        self,
        provider: SportsDataProvider,
        session_factory: async_sessionmaker[AsyncSession],
        league_config: LeagueConfig,
        app_timezone: str = "Europe/Warsaw",
    ) -> None:
        self._provider = provider
        self._session_factory = session_factory
        self._league_config = league_config
        self._app_timezone = app_timezone

    async def discover(self, fixture_date: date) -> DiscoverySummary:
        provider_name = self._provider.capabilities.provider
        enabled_by_id = self._enabled_config_by_provider_league_id(provider_name)
        if not enabled_by_id:
            return DiscoverySummary(
                date=fixture_date,
                provider=provider_name,
                fixtures_received=0,
                fixtures_eligible=0,
                fixtures_created=0,
                fixtures_updated=0,
                leagues_processed=0,
                seasons_created=0,
                teams_created=0,
                raw_payload_stored=False,
            )

        result = await self._provider.get_fixtures_by_date(
            fixture_date, timezone_name=self._app_timezone
        )
        eligible = [
            fixture for fixture in result.fixtures if fixture.provider_league_id in enabled_by_id
        ]

        fixtures_created = 0
        fixtures_updated = 0
        leagues_processed = 0
        seasons_created = 0
        teams_created = 0
        raw_payload_stored = False

        async with self._session_factory() as session:
            if result.raw_payload is not None:
                raw_payload_stored = await store_raw_evidence(
                    session,
                    provider=result.metadata.provider,
                    endpoint_family=result.metadata.endpoint_family,
                    request_fingerprint=result.metadata.request_fingerprint,
                    payload_hash=_payload_hash(result.raw_payload),
                    payload=result.raw_payload,
                    retrieved_at=result.metadata.retrieved_at,
                )

            seen_leagues: set[int] = set()
            for fixture in eligible:
                entry = enabled_by_id[fixture.provider_league_id]
                league_id, _ = await upsert_league_with_mapping(
                    session,
                    provider=fixture.provider,
                    external_id=fixture.provider_league_id,
                    slug=entry.slug,
                    name=entry.name,
                    country=entry.country,
                    enabled=True,
                )
                if fixture.provider_league_id not in seen_leagues:
                    leagues_processed += 1
                    seen_leagues.add(fixture.provider_league_id)

                season_id: uuid.UUID | None = None
                if fixture.provider_season is not None:
                    season_id, season_created = await upsert_season_id(
                        session, league_id, str(fixture.provider_season)
                    )
                    if season_created:
                        seasons_created += 1

                home_team_id, home_created = await get_or_create_team_id(
                    session,
                    fixture.provider,
                    fixture.provider_home_team_id,
                    fixture.home_team_name,
                )
                away_team_id, away_created = await get_or_create_team_id(
                    session,
                    fixture.provider,
                    fixture.provider_away_team_id,
                    fixture.away_team_name,
                )
                teams_created += int(home_created) + int(away_created)

                _, created = await upsert_fixture_id(
                    session,
                    provider=fixture.provider,
                    external_id=fixture.provider_fixture_id,
                    league_id=league_id,
                    season_id=season_id,
                    home_team_id=home_team_id,
                    away_team_id=away_team_id,
                    kickoff_at=fixture.kickoff_utc,
                    venue=fixture.venue,
                    round_name=fixture.round,
                    status=fixture.status_short,
                )
                if created:
                    fixtures_created += 1
                else:
                    fixtures_updated += 1

            await session.commit()

        return DiscoverySummary(
            date=fixture_date,
            provider=result.metadata.provider,
            fixtures_received=len(result.fixtures),
            fixtures_eligible=len(eligible),
            fixtures_created=fixtures_created,
            fixtures_updated=fixtures_updated,
            leagues_processed=leagues_processed,
            seasons_created=seasons_created,
            teams_created=teams_created,
            raw_payload_stored=raw_payload_stored,
        )

    def _enabled_config_by_provider_league_id(
        self, provider_name: str
    ) -> dict[int, LeagueConfigEntry]:
        mapping: dict[int, LeagueConfigEntry] = {}
        for entry in self._league_config.leagues:
            if not entry.enabled:
                continue
            provider_league_id = entry.provider_ids.get(provider_name)
            if provider_league_id is not None:
                mapping[provider_league_id] = entry
        return mapping


def _payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def create_or_get_job(
    session: AsyncSession,
    job_type: str,
    idempotency_key: str,
    scheduled_for: datetime,
) -> tuple[Job, bool]:
    statement = (
        pg_insert(Job)
        .values(
            job_type=job_type,
            status=JobStatus.PENDING.value,
            idempotency_key=idempotency_key,
            scheduled_for=scheduled_for,
        )
        .on_conflict_do_nothing(index_elements=[Job.idempotency_key])
        .returning(Job.id, Job.status)
    )
    row = (await session.execute(statement)).first()
    if row is not None:
        return Job(id=row.id, status=row.status), True
    existing = await session.execute(select(Job).where(Job.idempotency_key == idempotency_key))
    return existing.scalar_one(), False


async def update_job_status(session: AsyncSession, job_id: str, status: JobStatus) -> None:
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        return
    job = await session.get(Job, job_uuid)
    if job is None:
        return
    job.status = status.value
