from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
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
    FixtureMetadataSnapshot,
    Job,
    JobAttempt,
    League,
    LineupSnapshot,
    MatchContextRecord,
    OddsPrice,
    OddsSnapshotSet,
    ProviderEntityId,
    RawProviderPayload,
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
    async def _clean() -> None:
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
                FixtureMetadataSnapshot,
                Fixture,
                Season,
                League,
                Team,
                RawProviderPayload,
            ):
                await session.execute(delete(model))
            await session.commit()

    await _clean()
    try:
        yield
    finally:
        await _clean()


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


async def test_mutable_fixture_metadata_future_anti_leakage(m6_session_factory: Any) -> None:
    """M6.1 §1: Point-in-time selector respects immutable fixture observations.
    T0 (10:00): status=NS, kickoff=20:00, venue=Stadium A, round=Round 1
    T2 (14:00): updated to status=POSTPONED, kickoff=21:00, venue=Stadium B, round=Round 2
    as_of = T1 (12:00) MUST contain only T0 metadata.
    as_of = T3 (15:00) MUST contain T2 metadata.
    Old context and hash must never mutate.
    """
    t0 = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)
    t1 = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)
    t2 = datetime(2026, 8, 22, 14, 0, tzinfo=UTC)
    t3 = datetime(2026, 8, 22, 15, 0, tzinfo=UTC)
    kickoff_t0 = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)
    kickoff_t2 = datetime(2026, 8, 22, 21, 0, tzinfo=UTC)

    ids = await _seed_test_fixture(m6_session_factory, kickoff_at=kickoff_t0)
    fid = ids["fixture_id"]
    lid = ids["league_id"]
    sid = ids["season_id"]
    hid = ids["home_team_id"]
    aid = ids["away_team_id"]

    meta_t0_id = uuid.uuid4()
    meta_t2_id = uuid.uuid4()

    async with m6_session_factory() as session:
        # Observation 1 at T0
        meta_t0 = FixtureMetadataSnapshot(
            id=meta_t0_id,
            fixture_id=fid,
            provider="api_football",
            captured_at=t0,
            league_id=lid,
            season_id=sid,
            home_team_id=hid,
            away_team_id=aid,
            observed_home_team_name="Home FC",
            observed_away_team_name="Away FC",
            kickoff_at=kickoff_t0,
            venue="Stadium A",
            round="Round 1",
            status="NS",
        )
        # Observation 2 at T2
        meta_t2 = FixtureMetadataSnapshot(
            id=meta_t2_id,
            fixture_id=fid,
            provider="api_football",
            captured_at=t2,
            league_id=lid,
            season_id=sid,
            home_team_id=hid,
            away_team_id=aid,
            observed_home_team_name="Home FC",
            observed_away_team_name="Away FC",
            kickoff_at=kickoff_t2,
            venue="Stadium B",
            round="Round 2",
            status="POSTPONED",
        )
        session.add_all([meta_t0, meta_t2])

        # Update mutable Fixture to T2 values
        fix = await session.get(Fixture, fid)
        assert fix is not None
        fix.kickoff_at = kickoff_t2
        fix.venue = "Stadium B"
        fix.round = "Round 2"
        fix.status = "POSTPONED"
        await session.commit()

    # Build context at T1 (between T0 and T2)
    async with m6_session_factory() as session:
        rec_t1, q_t1, f_t1, ctx_t1 = await build_and_persist_match_context(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.MORNING,
            as_of=t1,
        )

    # Verify T1 context only contains T0 observation
    assert ctx_t1.fixture_identity["venue"] == "Stadium A"
    assert ctx_t1.fixture_identity["round"] == "Round 1"
    assert ctx_t1.fixture_identity["status"] == "NS"
    assert ctx_t1.fixture_identity["kickoff_at"] == kickoff_t0.isoformat()
    assert ctx_t1.source_manifest["sources"]["fixture_metadata"]["snapshot_id"] == str(meta_t0_id)
    hash_t1 = rec_t1.context_hash

    # Build context at T3 (after T2)
    async with m6_session_factory() as session:
        rec_t3, q_t3, f_t3, ctx_t3 = await build_and_persist_match_context(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.MORNING,
            as_of=t3,
        )

    # Verify T3 context contains T2 observation
    assert ctx_t3.fixture_identity["venue"] == "Stadium B"
    assert ctx_t3.fixture_identity["round"] == "Round 2"
    assert ctx_t3.fixture_identity["status"] == "POSTPONED"
    assert ctx_t3.fixture_identity["kickoff_at"] == kickoff_t2.isoformat()
    assert ctx_t3.source_manifest["sources"]["fixture_metadata"]["snapshot_id"] == str(meta_t2_id)

    # Verify old T1 context record in DB never mutated
    async with m6_session_factory() as session:
        reloaded_t1 = await session.get(MatchContextRecord, rec_t1.id)
        assert reloaded_t1 is not None
        assert reloaded_t1.context_hash == hash_t1
        assert reloaded_t1.context_jsonb["fixture_identity"]["venue"] == "Stadium A"


async def test_form_window_size_and_scope_filtering(m6_session_factory: Any) -> None:
    """M6.1 §6: Selector strictly filters window_size=10 and scope='overall'."""
    kickoff = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)
    ids = await _seed_test_fixture(m6_session_factory, kickoff_at=kickoff)
    fid = ids["fixture_id"]
    hid = ids["home_team_id"]

    t_correct = datetime(2026, 8, 22, 8, 0, tzinfo=UTC)
    t_wrong_window = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)
    t_wrong_scope = datetime(2026, 8, 22, 9, 30, tzinfo=UTC)

    form_correct_id = uuid.uuid4()
    async with m6_session_factory() as session:
        # Older row with window=10, scope=overall
        f_correct = TeamFormSnapshot(
            id=form_correct_id,
            team_id=hid,
            as_of=t_correct,
            window_size=10,
            scope="overall",
            metrics_jsonb={
                "outcomes": [{"result": "W", "goals_for": 2, "goals_against": 0}],
                "ppg": 2.0,
            },
            source_fingerprint="fp-correct",
        )
        # Newer row with window=5, scope=overall
        f_wrong_w = TeamFormSnapshot(
            team_id=hid,
            as_of=t_wrong_window,
            window_size=5,
            scope="overall",
            metrics_jsonb={
                "outcomes": [{"result": "L", "goals_for": 0, "goals_against": 1}],
                "ppg": 0.0,
            },
            source_fingerprint="fp-wrong-w",
        )
        # Newer row with window=10, scope=home
        f_wrong_s = TeamFormSnapshot(
            team_id=hid,
            as_of=t_wrong_scope,
            window_size=10,
            scope="home",
            metrics_jsonb={
                "outcomes": [{"result": "D", "goals_for": 1, "goals_against": 1}],
                "ppg": 1.0,
            },
            source_fingerprint="fp-wrong-s",
        )
        session.add_all([f_correct, f_wrong_w, f_wrong_s])
        await session.commit()

    # Build context at 10:00
    t_as_of = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)
    async with m6_session_factory() as session:
        rec, q, f, ctx = await build_and_persist_match_context(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.MORNING,
            as_of=t_as_of,
        )

    # Must have selected the window=10, scope=overall snapshot
    manifest = ctx.source_manifest["sources"]
    assert manifest["home_team_form"]["snapshot_id"] == str(form_correct_id)
    assert manifest["home_team_form"]["details"]["window_size"] == 10
    assert manifest["home_team_form"]["details"]["scope"] == "overall"


async def test_concurrent_context_build_idempotency(m6_session_factory: Any) -> None:
    """M6.1 §16: 10 concurrent builders for same fixture, phase, and as_of safely dedupe."""
    import asyncio

    kickoff = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)
    ids = await _seed_test_fixture(m6_session_factory, kickoff_at=kickoff)
    fid = ids["fixture_id"]
    t_as_of = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)

    async def run_worker() -> tuple[str, str, str, str]:
        async with m6_session_factory() as session:
            rec, q, f, ctx = await build_and_persist_match_context(
                session,
                fixture_id=fid,
                forecast_phase=ForecastPhase.MORNING,
                as_of=t_as_of,
            )
            return str(rec.id), rec.context_hash, str(q.id), str(f.id)

    # Run 10 concurrent builders simultaneously
    results = await asyncio.gather(*[run_worker() for _ in range(10)])

    first_res = results[0]
    for res in results:
        assert res == first_res

    # Verify exactly 1 record in each table in DB
    async with m6_session_factory() as session:
        contexts = (
            (
                await session.execute(
                    select(MatchContextRecord).where(MatchContextRecord.fixture_id == fid)
                )
            )
            .scalars()
            .all()
        )
        qualities = (
            (
                await session.execute(
                    select(DataQualityReport).where(DataQualityReport.fixture_id == fid)
                )
            )
            .scalars()
            .all()
        )
        features = (
            (
                await session.execute(
                    select(FeatureSnapshot).where(FeatureSnapshot.fixture_id == fid)
                )
            )
            .scalars()
            .all()
        )

        assert len(contexts) == 1
        assert len(qualities) == 1
        assert len(features) == 1


async def test_stale_running_collector_blocks_context_build(
    m6_session_factory: Any,
    m6_settings: Settings,
) -> None:
    """M6.1 §13: If any required collector is RUNNING,
    pre-match scan does NOT enqueue context build.
    """
    import hashlib

    from sports_intelligence.collectors.framework import resolve
    from sports_intelligence.collectors.freshness import FreshnessPolicy
    from sports_intelligence.collectors.pre_match_scan import PreMatchDecision
    from sports_intelligence.collectors.refresh import refresh_opportunity_suffix
    from sports_intelligence.core.phases import FreshnessCategory
    from sports_intelligence.workers.tasks.pre_match import _dispatch_decision

    kickoff = datetime(2026, 8, 22, 15, 0, tzinfo=UTC)
    ids = await _seed_test_fixture(m6_session_factory, kickoff_at=kickoff)
    fid = ids["fixture_id"]
    lid = ids["league_id"]
    sid = ids["season_id"]
    hid = ids["home_team_id"]
    aid = ids["away_team_id"]

    now = kickoff - timedelta(hours=1)

    # Plant stale odds snapshot (4 hours old)
    stale_odds_id = uuid.uuid4()
    async with m6_session_factory() as session:
        odds_set = OddsSnapshotSet(
            id=stale_odds_id,
            fixture_id=fid,
            provider="theoddsapi",
            captured_at=now - timedelta(hours=4),
            market_whitelist_jsonb=["h2h_1x2"],
        )
        session.add(odds_set)
        await session.commit()

    decision = PreMatchDecision(
        fixture_id=str(fid),
        league_id=str(lid),
        home_team_id=str(hid),
        away_team_id=str(aid),
        season_id=str(sid),
        kickoff_at=kickoff,
        phase=ForecastPhase.PREMATCH,
        categories_to_collect=(FreshnessCategory.ODDS,),
    )

    import sports_intelligence.collectors.odds_collector  # noqa: F401

    odds_collector = resolve("odds")
    lock_key = odds_collector.lock_key(fixture_id=str(fid), league_id=str(lid))
    ttl = FreshnessPolicy(m6_settings).ttl_for(odds_collector.category, decision.phase)
    opp = refresh_opportunity_suffix(
        collector_name="odds",
        kickoff_at=kickoff,
        now=now,
        windows_minutes=m6_settings.lineup_window_t_minutes,
        ttl_seconds=int(ttl.total_seconds()),
        latest_captured_at=now - timedelta(hours=4),
    )
    job_key = (
        f"collect:odds:{hashlib.sha1(lock_key.encode()).hexdigest()[:20]}:"
        f"{decision.phase.value}:{opp}"
    )

    async with m6_session_factory() as session:
        running_job = Job(
            job_type="collect:odds",
            idempotency_key=job_key,
            status=JobStatus.RUNNING.value,
            scheduled_for=now,
        )
        session.add(running_job)
        await session.commit()

    result = await _dispatch_decision(m6_session_factory, decision, now=now)

    assert result["has_in_flight_collectors"] is True
    assert result["jobs_enqueued"] == 0


async def test_failed_context_job_same_opportunity_retry(m6_session_factory: Any) -> None:
    """M6.1 §15: Same context-build opportunity with Job in FAILED status retries
    via CAS FAILED -> PENDING with same UUID.
    """
    from unittest.mock import patch

    from sports_intelligence.collectors.pre_match_scan import PreMatchDecision
    from sports_intelligence.pipelines.discover_fixtures import update_job_status
    from sports_intelligence.workers.tasks.context import build_match_context_task
    from sports_intelligence.workers.tasks.pre_match import _try_enqueue_context_build

    kickoff = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)
    ids = await _seed_test_fixture(m6_session_factory, kickoff_at=kickoff)
    fid = ids["fixture_id"]
    t_as_of = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)

    decision = PreMatchDecision(
        fixture_id=str(fid),
        league_id=str(ids["league_id"]),
        home_team_id=str(ids["home_team_id"]),
        away_team_id=str(ids["away_team_id"]),
        season_id=str(ids["season_id"]),
        kickoff_at=kickoff,
        phase=ForecastPhase.MORNING,
        categories_to_collect=(),
    )

    enqueued_job_ids: list[str] = []

    def mock_apply_async(*args: Any, **kwargs: Any) -> None:
        enqueued_job_ids.append(kwargs["args"][0])

    with patch.object(build_match_context_task, "apply_async", mock_apply_async):
        # 1. First context build enqueue creates job in PENDING and enqueues task
        await _try_enqueue_context_build(m6_session_factory, decision, as_of=t_as_of)
        assert len(enqueued_job_ids) == 1
        first_job_id = enqueued_job_ids[0]

        # Simulate context build failure
        async with m6_session_factory() as session:
            await update_job_status(session, first_job_id, JobStatus.FAILED)
            await session.commit()

        # 2. Next scanner opportunity: re-enqueues same UUID with CAS FAILED -> PENDING
        await _try_enqueue_context_build(m6_session_factory, decision, as_of=t_as_of)
        assert len(enqueued_job_ids) == 2
        assert enqueued_job_ids[1] == first_job_id

        async with m6_session_factory() as session:
            job = await session.get(Job, uuid.UUID(first_job_id))
            assert job is not None
            assert job.status == JobStatus.PENDING.value

        # 3. If job is RUNNING or SUCCEEDED, it is NOT retried / downgraded
        async with m6_session_factory() as session:
            await update_job_status(session, first_job_id, JobStatus.RUNNING)
            await session.commit()

        await _try_enqueue_context_build(m6_session_factory, decision, as_of=t_as_of)
        assert len(enqueued_job_ids) == 2  # No new enqueue

        async with m6_session_factory() as session:
            job = await session.get(Job, uuid.UUID(first_job_id))
            assert job is not None
            assert job.status == JobStatus.RUNNING.value


async def test_api_endpoints_phase_validation(
    m6_session_factory: Any,
    m6_settings: Settings,
) -> None:
    """M6.1 §20: Invalid phase parameter returns HTTP 422."""
    kickoff = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)
    ids = await _seed_test_fixture(m6_session_factory, kickoff_at=kickoff)
    fid = ids["fixture_id"]
    t_as_of = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)

    async with m6_session_factory() as session:
        await build_and_persist_match_context(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.MORNING,
            as_of=t_as_of,
        )

    app = create_app(m6_settings)
    with TestClient(app) as client:
        # Valid phase -> 200
        res_valid = client.get(f"/v1/fixtures/{fid}/context?phase=MORNING")
        assert res_valid.status_code == 200

        # Invalid phase -> 422
        res_invalid_ctx = client.get(f"/v1/fixtures/{fid}/context?phase=INVALID_PHASE")
        assert res_invalid_ctx.status_code == 422

        res_invalid_qual = client.get(f"/v1/fixtures/{fid}/quality?phase=INVALID_PHASE")
        assert res_invalid_qual.status_code == 422


async def test_form_snapshot_raw_evidence_link(m6_session_factory: Any) -> None:
    """M6.1 §18: Form snapshot links to raw_provider_payloads.id."""
    kickoff = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)
    ids = await _seed_test_fixture(m6_session_factory, kickoff_at=kickoff)
    fid = ids["fixture_id"]
    hid = ids["home_team_id"]
    t_as_of = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)

    payload_id = uuid.uuid4()
    form_id = uuid.uuid4()
    async with m6_session_factory() as session:
        raw_payload = RawProviderPayload(
            id=payload_id,
            provider="api_football",
            endpoint_family="teams/statistics",
            payload_hash="hash-form-raw",
            payload={"fixtures": []},
            first_seen_at=t_as_of - timedelta(hours=2),
        )
        session.add(raw_payload)
        await session.flush()

        form_snap = TeamFormSnapshot(
            id=form_id,
            team_id=hid,
            as_of=t_as_of - timedelta(hours=2),
            window_size=10,
            scope="overall",
            metrics_jsonb={"outcomes": []},
            source_fingerprint="fp-form-link",
            payload_id=payload_id,
        )
        session.add(form_snap)
        await session.commit()

    async with m6_session_factory() as session:
        rec, q, f, ctx = await build_and_persist_match_context(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.MORNING,
            as_of=t_as_of,
        )

    form_prov = ctx.source_manifest["sources"]["home_team_form"]
    assert form_prov["snapshot_id"] == str(form_id)
    assert form_prov["payload_id"] == str(payload_id)
