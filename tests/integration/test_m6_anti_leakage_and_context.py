from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from sports_intelligence.api.app import create_app
from sports_intelligence.context.builder import build_and_persist_match_context
from sports_intelligence.core.config import Settings
from sports_intelligence.core.job_status import JobStatus
from sports_intelligence.core.phases import ForecastPhase
from sports_intelligence.db.models import (
    AvailabilitySnapshot,
    DataQualityReport,
    FeatureSnapshot,
    Fixture,
    Job,
    JobAttempt,
    League,
    LineupSnapshot,
    MatchContextRecord,
    OddsPrice,
    OddsSnapshotSet,
    ProviderEntityId,
    ResearchClaim,
    ResearchDocument,
    ResearchRun,
    Season,
    StandingSnapshot,
    Team,
    TeamFormSnapshot,
    TeamStatisticsSnapshot,
)
from sports_intelligence.db.session import create_engine, create_session_factory
from sports_intelligence.workers.tasks.context import _run_build

requires_services = pytest.mark.skipif(
    not (os.environ.get("TEST_DATABASE_URL") and os.environ.get("TEST_REDIS_URL")),
    reason="TEST_DATABASE_URL and TEST_REDIS_URL are required",
)
pytestmark = [pytest.mark.integration, requires_services]


@pytest.fixture
def m6_settings(service_settings: Settings) -> Settings:
    return Settings(
        _env_file=None,
        app_env="mock",
        search_provider="mock",
        research_enabled=True,
        database_url=service_settings.database_url,
        redis_url=service_settings.redis_url,
    )


@pytest.fixture
async def m6_session_factory(m6_settings: Settings) -> Iterator[Any]:
    engine = create_engine(m6_settings.database_url)
    factory = create_session_factory(engine)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
async def _clean_m6_tables(m6_session_factory: Any) -> Iterator[None]:
    async with m6_session_factory() as session:
        for model in (
            MatchContextRecord,
            FeatureSnapshot,
            DataQualityReport,
            JobAttempt,
            Job,
            LineupSnapshot,
            AvailabilitySnapshot,
            OddsPrice,
            OddsSnapshotSet,
            TeamFormSnapshot,
            TeamStatisticsSnapshot,
            StandingSnapshot,
            ResearchClaim,
            ResearchDocument,
            ResearchRun,
            ProviderEntityId,
            Fixture,
            Season,
            League,
            Team,
        ):
            await session.execute(delete(model))
        await session.commit()
    yield


async def _seed_test_fixture(
    factory: Any,
    *,
    kickoff_at: datetime,
) -> dict[str, uuid.UUID]:
    async with factory() as session:
        league = League(slug=f"league-{uuid.uuid4().hex[:6]}", name="Premier League", enabled=True)
        session.add(league)
        await session.flush()

        season = Season(league_id=league.id, name="2026", active=True)
        session.add(season)
        await session.flush()

        home_team = Team(name="Home FC", country="England")
        away_team = Team(name="Away FC", country="England")
        session.add_all([home_team, away_team])
        await session.flush()

        # Provider external IDs
        session.add_all(
            [
                ProviderEntityId(
                    provider="mock",
                    entity_type="team",
                    internal_entity_id=home_team.id,
                    external_id="101",
                ),
                ProviderEntityId(
                    provider="mock",
                    entity_type="team",
                    internal_entity_id=away_team.id,
                    external_id="102",
                ),
            ]
        )

        fixture = Fixture(
            league_id=league.id,
            season_id=season.id,
            home_team_id=home_team.id,
            away_team_id=away_team.id,
            kickoff_at=kickoff_at,
            status="NS",
        )
        session.add(fixture)
        await session.commit()

        return {
            "fixture_id": fixture.id,
            "league_id": league.id,
            "season_id": season.id,
            "home_team_id": home_team.id,
            "away_team_id": away_team.id,
        }


async def test_strict_as_of_anti_leakage_boundary(m6_session_factory: Any) -> None:
    """M6 §2 & §17: Deliberately plant future rows and prove 10:00 as_of excludes every future row.

    Then verify 19:00 PREMATCH context includes allowed newer evidence without
    mutating morning context.
    """
    kickoff = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)
    ids = await _seed_test_fixture(m6_session_factory, kickoff_at=kickoff)
    fid = ids["fixture_id"]
    lid = ids["league_id"]
    sid = ids["season_id"]
    hid = ids["home_team_id"]

    t_morning = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)

    async with m6_session_factory() as session:
        # 1. Standings: past (08:00) vs future (12:00)
        st_past = StandingSnapshot(
            provider="mock",
            league_id=lid,
            season_id=sid,
            captured_at=datetime(2026, 8, 22, 8, 0, tzinfo=UTC),
            source_fingerprint="fp-st-0800",
            rows_jsonb=[
                {
                    "provider_team_id": 101,
                    "rank": 3,
                    "played": 5,
                    "points": 10,
                    "goals_for": 8,
                    "goals_against": 4,
                },
                {
                    "provider_team_id": 102,
                    "rank": 8,
                    "played": 5,
                    "points": 7,
                    "goals_for": 6,
                    "goals_against": 6,
                },
            ],
        )
        st_future = StandingSnapshot(
            provider="mock",
            league_id=lid,
            season_id=sid,
            captured_at=datetime(2026, 8, 22, 12, 0, tzinfo=UTC),
            source_fingerprint="fp-st-1200",
            rows_jsonb=[
                {
                    "provider_team_id": 101,
                    "rank": 1,
                    "played": 6,
                    "points": 13,
                    "goals_for": 11,
                    "goals_against": 4,
                },
                {
                    "provider_team_id": 102,
                    "rank": 10,
                    "played": 6,
                    "points": 7,
                    "goals_for": 6,
                    "goals_against": 9,
                },
            ],
        )
        session.add_all([st_past, st_future])

        # 2. Team Form: past (09:00) vs future (13:00)
        form_past = TeamFormSnapshot(
            team_id=hid,
            as_of=datetime(2026, 8, 22, 9, 0, tzinfo=UTC),
            window_size=10,
            scope="overall",
            source_fingerprint="fp-form-0900",
            metrics_jsonb={
                "outcomes": [
                    {
                        "outcome": "W",
                        "goals_for": 2,
                        "goals_against": 0,
                        "is_home": True,
                        "kickoff_utc": "2026-08-15T15:00:00Z",
                    },
                    {
                        "outcome": "D",
                        "goals_for": 1,
                        "goals_against": 1,
                        "is_home": False,
                        "kickoff_utc": "2026-08-08T15:00:00Z",
                    },
                ]
            },
        )
        form_future = TeamFormSnapshot(
            team_id=hid,
            as_of=datetime(2026, 8, 22, 13, 0, tzinfo=UTC),
            window_size=10,
            scope="overall",
            source_fingerprint="fp-form-1300",
            metrics_jsonb={
                "outcomes": [
                    {
                        "outcome": "L",
                        "goals_for": 0,
                        "goals_against": 5,
                        "is_home": True,
                        "kickoff_utc": "2026-08-21T20:00:00Z",
                    },
                ]
            },
        )
        session.add_all([form_past, form_future])

        # 3. Availability: past (09:30) vs future correction (11:00)
        avail_past = AvailabilitySnapshot(
            provider="mock",
            fixture_id=fid,
            team_id=hid,
            captured_at=datetime(2026, 8, 22, 9, 30, tzinfo=UTC),
            availability_state="KNOWN_PRESENT",
            players_jsonb=[{"player_name": "Player 1", "missing": True}],
            impact_flags_jsonb=[],
            conflicts_jsonb=[],
        )
        avail_future = AvailabilitySnapshot(
            provider="mock",
            fixture_id=fid,
            team_id=hid,
            captured_at=datetime(2026, 8, 22, 11, 0, tzinfo=UTC),
            availability_state="KNOWN_NONE",
            players_jsonb=[],
            impact_flags_jsonb=[],
            conflicts_jsonb=[],
        )
        session.add_all([avail_past, avail_future])

        # 4. Lineups: future only (18:45)
        lineup_future = LineupSnapshot(
            provider="mock",
            fixture_id=fid,
            team_id=hid,
            captured_at=datetime(2026, 8, 22, 18, 45, tzinfo=UTC),
            confirmed=True,
            formation="4-3-3",
            players_jsonb=[{"name": "Keeper", "position": "G"}],
            publication_state="CONFIRMED",
        )
        session.add(lineup_future)

        # 5. Odds: past (09:55) vs future closing odds (19:50)
        odds_past_id = uuid.uuid4()
        odds_past = OddsSnapshotSet(
            id=odds_past_id,
            fixture_id=fid,
            provider="mock",
            captured_at=datetime(2026, 8, 22, 9, 55, tzinfo=UTC),
            market_whitelist_jsonb=["h2h_1x2"],
        )
        odds_past_price = OddsPrice(
            snapshot_set_id=odds_past_id,
            bookmaker="sportsbook",
            market="h2h_1x2",
            selection="home",
            decimal_odds=Decimal("2.10"),
            implied_probability=Decimal("0.476190"),
            no_vig_probability=Decimal("0.450000"),
        )
        odds_future_id = uuid.uuid4()
        odds_future = OddsSnapshotSet(
            id=odds_future_id,
            fixture_id=fid,
            provider="mock",
            captured_at=datetime(2026, 8, 22, 19, 50, tzinfo=UTC),
            market_whitelist_jsonb=["h2h_1x2"],
        )
        odds_future_price = OddsPrice(
            snapshot_set_id=odds_future_id,
            bookmaker="sportsbook",
            market="h2h_1x2",
            selection="home",
            decimal_odds=Decimal("1.50"),  # heavily steamed closing price
            implied_probability=Decimal("0.666667"),
            no_vig_probability=Decimal("0.640000"),
        )
        session.add_all([odds_past, odds_future])
        await session.flush()
        session.add_all([odds_past_price, odds_future_price])

        # 6. Research: past (09:40) vs future (10:30)
        run_past = ResearchRun(
            fixture_id=fid,
            phase="MORNING",
            provider="mock",
            status="AVAILABLE",
            captured_at=datetime(2026, 8, 22, 9, 40, tzinfo=UTC),
            details_jsonb={},
        )
        session.add(run_past)
        await session.flush()

        doc_past = ResearchDocument(
            fixture_id=fid,
            run_id=run_past.id,
            url="https://news.test/arsenal-preview",
            domain="news.test",
            title="Morning Preview",
            retrieved_at=datetime(2026, 8, 22, 9, 40, tzinfo=UTC),
            content_hash="hash-doc-0940",
            provider="mock",
        )
        session.add(doc_past)

        run_future = ResearchRun(
            fixture_id=fid,
            phase="MORNING",
            provider="mock",
            status="PROVIDER_ERROR",
            captured_at=datetime(2026, 8, 22, 10, 30, tzinfo=UTC),
            details_jsonb={},
        )
        session.add(run_future)

        await session.commit()

    # Build morning context as of 10:00
    async with m6_session_factory() as session:
        m_ctx_rec, m_qual_rec, m_feat_rec, m_ctx = await build_and_persist_match_context(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.MORNING,
            as_of=t_morning,
        )

    # 1. Verify that all future records were strictly excluded from morning context
    morning_manifest = m_ctx.source_manifest["sources"]

    # Standings: 08:00 row was selected, rank=3 (not rank=1 from 12:00)
    assert morning_manifest["standings"]["snapshot_id"] == str(st_past.id)
    assert m_ctx.season_strength["home_league_position"] == 3

    # Form: 09:00 row was selected (2 outcomes, not 1 outcome from 13:00)
    assert morning_manifest["home_team_form"]["snapshot_id"] == str(form_past.id)
    assert m_ctx.team_form["home_sample_size"] == 2

    # Availability: 09:30 row was selected, 1 missing player (not 0 from 11:00)
    assert morning_manifest["home_availability"]["snapshot_id"] == str(avail_past.id)
    assert m_ctx.availability["home_missing_count"] == 1

    # Lineup: 18:45 row is EXCLUDED
    assert "home_lineup" not in morning_manifest
    assert m_ctx.lineups["home_confirmed"] is None

    # Odds: 09:55 row was selected (odds 2.10 / no-vig 0.45, not closing odds 1.50)
    assert morning_manifest["odds"]["snapshot_id"] == str(odds_past.id)
    assert m_ctx.market_snapshot["prices"][0]["decimal_odds"] == 2.10

    # Research: 09:40 run was selected (status AVAILABLE, not future PROVIDER_ERROR)
    assert m_ctx.research_claims["status"] == "AVAILABLE"

    morning_hash = m_ctx_rec.context_hash
    morning_id = m_ctx_rec.id

    # 2. Build PREMATCH context as of 19:00
    t_prematch = datetime(2026, 8, 22, 19, 0, tzinfo=UTC)
    async with m6_session_factory() as session:
        p_ctx_rec, p_qual_rec, p_feat_rec, p_ctx = await build_and_persist_match_context(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.PREMATCH,
            as_of=t_prematch,
        )

    # In PREMATCH context, lineup at 18:45 is now visible
    prematch_manifest = p_ctx.source_manifest["sources"]
    assert "home_lineup" in prematch_manifest
    assert prematch_manifest["home_lineup"]["snapshot_id"] == str(lineup_future.id)
    assert p_ctx.lineups["home_confirmed"] is True

    # But closing odds at 19:50 are STILL excluded at 19:00!
    assert p_ctx.market_snapshot["prices"][0]["decimal_odds"] != 1.50

    # 3. Assert that MORNING context record and hash in DB did NOT change
    async with m6_session_factory() as session:
        reloaded_morning = await session.get(MatchContextRecord, morning_id)
        assert reloaded_morning is not None
        assert reloaded_morning.context_hash == morning_hash
        assert reloaded_morning.forecast_phase == "MORNING"


async def test_match_context_build_idempotency(m6_session_factory: Any) -> None:
    """M6 §13 & §21: Re-running builder on same fixture, phase, and as_of reuses existing record."""
    kickoff = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)
    ids = await _seed_test_fixture(m6_session_factory, kickoff_at=kickoff)
    fid = ids["fixture_id"]
    t_as_of = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)

    async with m6_session_factory() as session:
        rec1, q1, f1, _ = await build_and_persist_match_context(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.MORNING,
            as_of=t_as_of,
        )

    async with m6_session_factory() as session:
        rec2, q2, f2, _ = await build_and_persist_match_context(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.MORNING,
            as_of=t_as_of,
        )

    # Identical record returned
    assert rec1.id == rec2.id
    assert rec1.context_hash == rec2.context_hash
    assert q1.id == q2.id
    assert f1.id == f2.id

    # Verify DB only has 1 record
    async with m6_session_factory() as session:
        records = (
            (
                await session.execute(
                    select(MatchContextRecord).where(MatchContextRecord.fixture_id == fid)
                )
            )
            .scalars()
            .all()
        )
        assert len(records) == 1


async def test_context_build_celery_task_execution(
    m6_session_factory: Any,
    m6_settings: Settings,
) -> None:
    """M6 §20: Verify background worker task executes deterministically,
    updates Job status, and records attempt.
    """
    kickoff = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)
    ids = await _seed_test_fixture(m6_session_factory, kickoff_at=kickoff)
    fid = ids["fixture_id"]
    t_as_of = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)

    job_id = uuid.uuid4()
    async with m6_session_factory() as session:
        job = Job(
            id=job_id,
            job_type="context:build_match_context",
            idempotency_key=f"ctx-test-{job_id}",
            scheduled_for=t_as_of,
            status=JobStatus.PENDING,
        )
        session.add(job)
        await session.commit()

    # Run the worker task implementation
    result = await _run_build(
        str(job_id),
        str(fid),
        "MORNING",
        t_as_of.isoformat(),
        settings=m6_settings,
        session_factory=m6_session_factory,
    )

    assert result["status"] == "success"

    assert "context_hash" in result
    assert "quality_report_id" in result

    # Check Job table status is SUCCEEDED
    async with m6_session_factory() as session:
        db_job = await session.get(Job, job_id)
        assert db_job is not None
        assert db_job.status == JobStatus.SUCCEEDED

        attempts = (
            (await session.execute(select(JobAttempt).where(JobAttempt.job_id == job_id)))
            .scalars()
            .all()
        )
        assert len(attempts) >= 1
        assert attempts[0].status == JobStatus.SUCCEEDED.value


async def test_api_endpoints_quality_and_context(
    m6_session_factory: Any,
    m6_settings: Settings,
) -> None:
    """M6 §22: Read-only API endpoints for quality and context return
    expected data with zero external calls.
    """
    kickoff = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)
    ids = await _seed_test_fixture(m6_session_factory, kickoff_at=kickoff)
    fid = ids["fixture_id"]
    t_as_of = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)

    # Build context in DB first
    async with m6_session_factory() as session:
        await build_and_persist_match_context(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.MORNING,
            as_of=t_as_of,
        )

    app = create_app(m6_settings)
    with TestClient(app) as client:
        # 1. Quality endpoint
        q_resp = client.get(f"/v1/fixtures/{fid}/quality")
        assert q_resp.status_code == 200
        q_data = q_resp.json()
        assert q_data["fixture_id"] == str(fid)
        assert "overall_score" in q_data
        assert "quality_band" in q_data
        assert "can_predict" in q_data
        assert "dimension_scores" in q_data

        # 2. Context endpoint
        c_resp = client.get(f"/v1/fixtures/{fid}/context")
        assert c_resp.status_code == 200
        c_data = c_resp.json()
        assert c_data["fixture_id"] == str(fid)
        assert "context_hash" in c_data
        assert "source_timing" in c_data
        assert "context" in c_data
        assert "fixture_identity" in c_data["context"]

        # 3. 404 for unknown fixture
        unknown_id = uuid.uuid4()
        nf_resp = client.get(f"/v1/fixtures/{unknown_id}/context")
        assert nf_resp.status_code == 404
