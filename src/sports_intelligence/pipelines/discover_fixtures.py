from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sports_intelligence.collectors.quota import QuotaManager  # noqa: E402
from sports_intelligence.core.job_status import JobStatus
from sports_intelligence.core.league_config import LeagueConfig, LeagueConfigEntry
from sports_intelligence.core.phases import Priority
from sports_intelligence.db.models import Job
from sports_intelligence.db.repositories.discovery import (
    get_or_create_team_id,
    record_fixture_metadata_snapshot,
    store_raw_evidence_with_payload_id,
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
        quota: QuotaManager | None = None,
        priority: Priority = Priority.P1,
    ) -> None:
        self._provider = provider
        self._session_factory = session_factory
        self._league_config = league_config
        self._app_timezone = app_timezone
        self._quota = quota
        self._priority = priority

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

        # Quota policy gates EVERY provider call (M4.1 §1): scheduled and
        # manual discovery both pass through the reservation + ledger.
        if self._quota is not None:
            decision = await self._quota.reserve(
                provider=provider_name,
                priority=self._priority,
                estimated_cost=1,
            )
            if decision.denied:
                from sports_intelligence.collectors.quota import QuotaUnavailableError

                raise QuotaUnavailableError(
                    f"quota denied for discovery ({decision.reason})", decision=decision
                )

        started_at = datetime.now(UTC)
        try:
            result = await self._provider.get_fixtures_by_date(
                fixture_date, timezone_name=self._app_timezone
            )
        except Exception as exc:
            if self._quota is not None:
                await self._quota.record_failure(
                    provider=provider_name,
                    endpoint_category="fixtures_by_date",
                    started_at=started_at,
                    exc=exc,
                    priority=self._priority,
                    estimated_cost=1,
                )
            raise
        finished_at = datetime.now(UTC)
        if self._quota is not None:
            await self._quota.record_success(
                provider=provider_name,
                endpoint_category="fixtures_by_date",
                started_at=started_at,
                finished_at=finished_at,
                headers=result.metadata.rate_headers,
                priority=self._priority,
                estimated_cost=1,
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

        payload_id: uuid.UUID | None = None
        async with self._session_factory() as session:
            if result.raw_payload is not None:
                raw_payload_stored, payload_id = await store_raw_evidence_with_payload_id(
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

                fixture_id, created = await upsert_fixture_id(
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

                await record_fixture_metadata_snapshot(
                    session,
                    fixture_id=fixture_id,
                    provider=fixture.provider,
                    provider_fixture_id=str(fixture.provider_fixture_id),
                    captured_at=result.metadata.retrieved_at,
                    league_id=league_id,
                    season_id=season_id,
                    home_team_id=home_team_id,
                    away_team_id=away_team_id,
                    observed_home_team_name=fixture.home_team_name or "",
                    observed_away_team_name=fixture.away_team_name or "",
                    observed_league_name=entry.name,
                    observed_league_slug=entry.slug,
                    kickoff_at=fixture.kickoff_utc,
                    venue=fixture.venue,
                    round_name=fixture.round,
                    status=fixture.status_short,
                    payload_id=payload_id,
                    source_version="v1",
                )

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


async def transition_job_status_if(
    session: AsyncSession, job_id: str, from_status: JobStatus, to_status: JobStatus
) -> bool:
    """Conditional (CAS) status transition; never downgrades a newer state."""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        return False
    statement = (
        update(Job)
        .where(Job.id == job_uuid, Job.status == from_status.value)
        .values(status=to_status.value)
    )
    result = await session.execute(statement)
    rowcount: int = getattr(result, "rowcount", 0)
    return rowcount == 1
