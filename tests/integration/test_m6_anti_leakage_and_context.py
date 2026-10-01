from __future__ import annotations

import hashlib
import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update

from sports_intelligence.api.app import create_app
from sports_intelligence.collectors.freshness import FreshnessPolicy
from sports_intelligence.context.builder import (
    ContextBuildPolicy,
    assemble_match_context_v1,
    build_and_persist_match_context,
)
from sports_intelligence.context.errors import HistoricalFixtureMetadataUnavailable
from sports_intelligence.context.models import MatchContextV1
from sports_intelligence.context.provenance import build_source_manifest
from sports_intelligence.context.selector import select_evidence
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
from sports_intelligence.features.builder import build_features
from sports_intelligence.quality.engine import (
    QualityPolicy,
    QualityWeights,
    evaluate_data_quality,
)
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


async def _build_test_context(
    session: Any,
    fixture_id: uuid.UUID,
    forecast_phase: ForecastPhase,
    as_of: datetime,
    policy: QualityPolicy | None = None,
    freshness_policy: FreshnessPolicy | None = None,
    research_enabled: bool = True,
) -> tuple[MatchContextRecord, DataQualityReport, FeatureSnapshot, MatchContextV1]:
    _s = Settings(app_env="mock")
    if policy is None:
        policy = QualityPolicy(weights=QualityWeights(form=0.1), min_predict_score=0.65)
    if freshness_policy is None:
        freshness_policy = FreshnessPolicy(_s)
    _bp = ContextBuildPolicy(
        quality_policy=policy,
        freshness_policy=freshness_policy,
        research_enabled=research_enabled,
    )
    return await build_and_persist_match_context(
        session,
        fixture_id=fixture_id,
        forecast_phase=forecast_phase,
        as_of=as_of,
        build_policy=_bp,
    )


__build_and_persist_match_context = _build_test_context


async def _seed_test_fixture(
    factory: Any,
    *,
    kickoff_at: datetime,
    create_metadata: bool = True,
    metadata_captured_at: datetime | None = None,
    home_external_id: str = "101",
    away_external_id: str = "102",
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

        # Provider external IDs (seeded as historically known before kickoff)
        prov_seen = kickoff_at - timedelta(days=30)
        session.add_all(
            [
                ProviderEntityId(
                    provider="mock",
                    entity_type="team",
                    internal_entity_id=home_team.id,
                    external_id=home_external_id,
                    first_seen_at=prov_seen,
                ),
                ProviderEntityId(
                    provider="mock",
                    entity_type="team",
                    internal_entity_id=away_team.id,
                    external_id=away_external_id,
                    first_seen_at=prov_seen,
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
        await session.flush()

        if create_metadata:
            meta_cap = metadata_captured_at or (kickoff_at - timedelta(days=2))
            meta = FixtureMetadataSnapshot(
                fixture_id=fixture.id,
                provider="mock",
                provider_fixture_id=f"prov-{uuid.uuid4().hex[:8]}",
                captured_at=meta_cap,
                league_id=league.id,
                season_id=season.id,
                home_team_id=home_team.id,
                away_team_id=away_team.id,
                observed_home_team_name="Home FC",
                observed_away_team_name="Away FC",
                observed_league_name=league.name,
                observed_league_slug=league.slug,
                kickoff_at=kickoff_at,
                venue="Main Stadium",
                round="Round 1",
                status="NS",
                source_version="v1",
            )
            session.add(meta)

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
        m_ctx_rec, m_qual_rec, m_feat_rec, m_ctx = await __build_and_persist_match_context(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.MORNING,
            as_of=t_morning,
        )

    # 1. Verify that all future records were strictly excluded from morning context
    morning_manifest = m_ctx.source_manifest.sources

    # Standings: 08:00 row was selected, rank=3 (not rank=1 from 12:00)
    assert morning_manifest["standings"].snapshot_id == str(st_past.id)
    assert m_ctx.season_strength.home_league_position == 3

    # Form: 09:00 row was selected (2 outcomes, not 1 outcome from 13:00)
    assert morning_manifest["home_team_form"].snapshot_id == str(form_past.id)
    assert m_ctx.team_form.home_sample_size == 2

    # Availability: 09:30 row was selected, 1 missing player (not 0 from 11:00)
    assert morning_manifest["home_availability"].snapshot_id == str(avail_past.id)
    assert m_ctx.availability.home_missing_count == 1

    # Lineup: 18:45 row is EXCLUDED
    assert "home_lineup" not in morning_manifest
    assert m_ctx.lineups.home_confirmed is None

    # Odds: 09:55 row was selected (odds 2.10 / no-vig 0.45, not closing odds 1.50)
    assert morning_manifest["odds"].snapshot_id == str(odds_past.id)
    assert m_ctx.market_snapshot.prices[0].decimal_odds == 2.10

    # Research: 09:40 run was selected (status AVAILABLE, not future PROVIDER_ERROR)
    assert m_ctx.research_claims.status == "AVAILABLE"

    morning_hash = m_ctx_rec.context_hash
    morning_id = m_ctx_rec.id

    # 2. Build PREMATCH context as of 19:00
    t_prematch = datetime(2026, 8, 22, 19, 0, tzinfo=UTC)
    async with m6_session_factory() as session:
        p_ctx_rec, p_qual_rec, p_feat_rec, p_ctx = await __build_and_persist_match_context(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.PREMATCH,
            as_of=t_prematch,
        )

    # In PREMATCH context, lineup at 18:45 is now visible
    prematch_manifest = p_ctx.source_manifest.sources
    assert "home_lineup" in prematch_manifest
    assert prematch_manifest["home_lineup"].snapshot_id == str(lineup_future.id)
    assert p_ctx.lineups.home_confirmed is True

    # But closing odds at 19:50 are STILL excluded at 19:00!
    assert p_ctx.market_snapshot.prices[0].decimal_odds != 1.50

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
        rec1, q1, f1, _ = await __build_and_persist_match_context(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.MORNING,
            as_of=t_as_of,
        )

    async with m6_session_factory() as session:
        rec2, q2, f2, _ = await __build_and_persist_match_context(
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
        await __build_and_persist_match_context(
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

    ids = await _seed_test_fixture(m6_session_factory, kickoff_at=kickoff_t0, create_metadata=False)
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
        rec_t1, q_t1, f_t1, ctx_t1 = await __build_and_persist_match_context(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.MORNING,
            as_of=t1,
        )

    # Verify T1 context only contains T0 observation
    assert ctx_t1.fixture_identity.venue == "Stadium A"
    assert ctx_t1.fixture_identity.round == "Round 1"
    assert ctx_t1.fixture_identity.status == "NS"
    assert ctx_t1.fixture_identity.kickoff_at == kickoff_t0.isoformat()
    assert ctx_t1.source_manifest.sources["fixture_metadata"].snapshot_id == str(meta_t0_id)
    hash_t1 = rec_t1.context_hash

    # Build context at T3 (after T2)
    async with m6_session_factory() as session:
        rec_t3, q_t3, f_t3, ctx_t3 = await __build_and_persist_match_context(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.MORNING,
            as_of=t3,
        )

    # Verify T3 context contains T2 observation
    assert ctx_t3.fixture_identity.venue == "Stadium B"
    assert ctx_t3.fixture_identity.round == "Round 2"
    assert ctx_t3.fixture_identity.status == "POSTPONED"
    assert ctx_t3.fixture_identity.kickoff_at == kickoff_t2.isoformat()
    assert ctx_t3.source_manifest.sources["fixture_metadata"].snapshot_id == str(meta_t2_id)

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
        rec, q, f, ctx = await __build_and_persist_match_context(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.MORNING,
            as_of=t_as_of,
        )

    # Must have selected the window=10, scope=overall snapshot
    manifest = ctx.source_manifest.sources
    assert manifest["home_team_form"].snapshot_id == str(form_correct_id)
    assert manifest["home_team_form"].details is not None
    assert manifest["home_team_form"].details["window_size"] == 10
    assert manifest["home_team_form"].details["scope"] == "overall"


async def test_concurrent_context_build_idempotency(m6_session_factory: Any) -> None:
    """M6.1 §16: 10 concurrent builders for same fixture, phase, and as_of safely dedupe."""
    import asyncio

    kickoff = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)
    ids = await _seed_test_fixture(m6_session_factory, kickoff_at=kickoff)
    fid = ids["fixture_id"]
    t_as_of = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)

    async def run_worker() -> tuple[str, str, str, str]:
        async with m6_session_factory() as session:
            rec, q, f, ctx = await __build_and_persist_match_context(
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
        await __build_and_persist_match_context(
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
        rec, q, f, ctx = await __build_and_persist_match_context(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.MORNING,
            as_of=t_as_of,
        )

    form_prov = ctx.source_manifest.sources["home_team_form"]
    assert form_prov.snapshot_id == str(form_id)
    assert form_prov.payload_id == str(payload_id)


async def test_historical_context_no_metadata_snapshot_never_leaks_mutable_fixture(
    m6_session_factory: Any,
) -> None:
    """M6.2 §1 & §15.1: Legacy fixture with current mutable status FT and no snapshot <= as_of
    must report METADATA_UNAVAILABLE (never FT), abstain band, and can_predict=False.
    """
    kickoff = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)
    ids = await _seed_test_fixture(m6_session_factory, kickoff_at=kickoff, create_metadata=False)
    fid = ids["fixture_id"]

    # Mutate canonical fixture to finished match
    async with m6_session_factory() as session:
        fix = await session.get(Fixture, fid)
        assert fix is not None
        fix.status = "FT"
        fix.venue = "Modern Arena"
        fix.round = "Round 38"
        await session.commit()

    t_as_of = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)
    async with m6_session_factory() as session:
        with pytest.raises(HistoricalFixtureMetadataUnavailable):
            await _build_test_context(
                session,
                fixture_id=fid,
                forecast_phase=ForecastPhase.MORNING,
                as_of=t_as_of,
            )

        # M6.3 §1 & §13.2: Verify zero MatchContext/FeatureSnapshot/DataQualityReport
        # persisted on refusal
        ctx_row = (
            await session.execute(
                select(MatchContextRecord).where(MatchContextRecord.fixture_id == fid)
            )
        ).first()
        assert ctx_row is None

        q_row = (
            await session.execute(
                select(DataQualityReport).where(DataQualityReport.fixture_id == fid)
            )
        ).first()
        assert q_row is None

        f_row = (
            await session.execute(select(FeatureSnapshot).where(FeatureSnapshot.fixture_id == fid))
        ).first()
        assert f_row is None


async def test_metadata_snapshot_overrides_changed_canonical_fixture(
    m6_session_factory: Any,
) -> None:
    """M6.2 §1 & §15.2: Historical snapshot league/team dimensions strictly override
    mutated canonical Fixture dimensions.
    """
    kickoff = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)
    ids = await _seed_test_fixture(m6_session_factory, kickoff_at=kickoff, create_metadata=False)
    fid = ids["fixture_id"]
    orig_lid = ids["league_id"]
    orig_sid = ids["season_id"]
    orig_hid = ids["home_team_id"]
    orig_aid = ids["away_team_id"]

    t0_captured = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)
    meta_id = uuid.uuid4()
    payload_id = uuid.uuid4()

    async with m6_session_factory() as session:
        # Create authoritative snapshot with original dimensions
        raw_payload = RawProviderPayload(
            id=payload_id,
            provider="api_football",
            endpoint_family="fixtures",
            payload_hash="hash-fixture-raw",
            payload={"fixture": {}},
            first_seen_at=t0_captured,
        )
        session.add(raw_payload)
        await session.flush()

        meta = FixtureMetadataSnapshot(
            id=meta_id,
            fixture_id=fid,
            provider="api_football",
            provider_fixture_id="api-fix-999",
            captured_at=t0_captured,
            league_id=orig_lid,
            season_id=orig_sid,
            home_team_id=orig_hid,
            away_team_id=orig_aid,
            observed_home_team_name="Historic Home",
            observed_away_team_name="Historic Away",
            kickoff_at=kickoff,
            venue="Historic Grounds",
            round="Round 1",
            status="NS",
            source_version="v1",
            payload_id=payload_id,
        )
        session.add(meta)

        # Mutate canonical Fixture to completely different league and teams
        other_league = League(slug="mutated-league", name="Mutated League", enabled=True)
        session.add(other_league)
        await session.flush()

        fix = await session.get(Fixture, fid)
        assert fix is not None
        fix.league_id = other_league.id
        fix.venue = "Mutated Stadium"
        await session.commit()

    t_as_of = datetime(2026, 8, 21, 10, 0, tzinfo=UTC)
    async with m6_session_factory() as session:
        rec, q, f, ctx = await __build_and_persist_match_context(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.MORNING,
            as_of=t_as_of,
        )

    # Must strictly use snapshot's league_id and historic team names
    assert ctx.fixture_identity.league_id == str(orig_lid)
    assert ctx.fixture_identity.home_team_name == "Historic Home"
    assert ctx.fixture_identity.away_team_name == "Historic Away"
    assert ctx.fixture_identity.venue == "Historic Grounds"

    # Fixture provenance contains external ID, source version, and payload_id
    fix_prov = ctx.source_manifest.sources["fixture_metadata"]
    assert fix_prov.snapshot_id == str(meta_id)
    assert fix_prov.provider == "api_football"
    assert fix_prov.payload_id == str(payload_id)
    assert fix_prov.details["provider_fixture_id"] == "api-fix-999"
    assert fix_prov.details["source_version"] == "v1"


async def test_different_quality_policies_create_separate_identities_and_fingerprints(
    m6_session_factory: Any,
) -> None:
    """M6.2 §5, §15.6, §15.7: Policy A vs Policy B generates distinct policy fingerprints
    and can both be persisted for the same fixture and as_of without conflict.
    """
    kickoff = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)
    ids = await _seed_test_fixture(m6_session_factory, kickoff_at=kickoff)
    fid = ids["fixture_id"]
    t_as_of = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)

    policy_a = QualityPolicy(
        weights=QualityWeights(fixture_identity=0.10, form=0.20),
        staleness_penalty=0.05,
        max_staleness_penalty=0.20,
    )
    policy_b = QualityPolicy(
        weights=QualityWeights(fixture_identity=0.10, form=0.40),
        staleness_penalty=0.10,
        max_staleness_penalty=0.30,
    )

    async with m6_session_factory() as session:
        rec_a, q_a, f_a, ctx_a = await __build_and_persist_match_context(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.MORNING,
            as_of=t_as_of,
            policy=policy_a,
        )

    async with m6_session_factory() as session:
        rec_b, q_b, f_b, ctx_b = await __build_and_persist_match_context(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.MORNING,
            as_of=t_as_of,
            policy=policy_b,
        )

    assert q_a.policy_fingerprint != q_b.policy_fingerprint
    assert q_a.quality_policy_jsonb["weights"]["form"] == 0.20
    assert q_b.quality_policy_jsonb["weights"]["form"] == 0.40
    assert q_a.quality_policy_jsonb["staleness_penalty"] == 0.05
    assert q_b.quality_policy_jsonb["staleness_penalty"] == 0.10

    # Verify both reports co-exist in DB with their distinct policy fingerprints
    async with m6_session_factory() as session:
        reports = (
            (
                await session.execute(
                    select(DataQualityReport).where(
                        DataQualityReport.fixture_id == fid,
                        DataQualityReport.as_of == t_as_of,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(reports) == 2
        fp_set = {r.policy_fingerprint for r in reports}
        assert q_a.policy_fingerprint in fp_set
        assert q_b.policy_fingerprint in fp_set


async def test_odds_insertion_order_produces_identical_context_hash(
    m6_session_factory: Any,
) -> None:
    """M6.2 §7 & §15.9: Database insertion order of OddsPrice rows does NOT affect
    canonical MatchContext serialization or context_hash.
    """
    from sports_intelligence.context.builder import assemble_match_context_v1
    from sports_intelligence.context.provenance import build_source_manifest
    from sports_intelligence.context.selector import SelectedEvidence, SelectedFixtureInfo
    from sports_intelligence.features.builder import build_features
    from sports_intelligence.quality.engine import evaluate_data_quality

    kickoff = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)
    fix_info = SelectedFixtureInfo(
        fixture_id=uuid.uuid4(),
        league_id=uuid.uuid4(),
        season_id=uuid.uuid4(),
        home_team_id=uuid.uuid4(),
        away_team_id=uuid.uuid4(),
        kickoff_at=kickoff,
        venue="Test Ground",
        round="Round 1",
        status="NS",
        league_slug="test-league",
        league_name="Test League",
        home_team_name="Home",
        away_team_name="Away",
        home_provider_mappings=[],
        away_provider_mappings=[],
        fixture_metadata_snapshot_id=uuid.uuid4(),
        metadata_captured_at=kickoff - timedelta(days=2),
    )
    as_of = kickoff - timedelta(hours=4)
    odds_set_id = uuid.uuid4()
    odds_set = OddsSnapshotSet(
        id=odds_set_id,
        fixture_id=fix_info.fixture_id,
        provider="theoddsapi",
        captured_at=as_of,
        market_whitelist_jsonb=["h2h_1x2"],
    )

    p1 = OddsPrice(
        id=uuid.uuid4(),
        snapshot_set_id=odds_set_id,
        bookmaker="pinnacle",
        market="h2h_1x2",
        selection="home",
        decimal_odds=Decimal("2.10"),
        implied_probability=Decimal("0.4762"),
        no_vig_probability=Decimal("0.4500"),
    )
    p2 = OddsPrice(
        id=uuid.uuid4(),
        snapshot_set_id=odds_set_id,
        bookmaker="bet365",
        market="h2h_1x2",
        selection="home",
        decimal_odds=Decimal("2.15"),
        implied_probability=Decimal("0.4651"),
        no_vig_probability=Decimal("0.4400"),
    )
    p3 = OddsPrice(
        id=uuid.uuid4(),
        snapshot_set_id=odds_set_id,
        bookmaker="betfair",
        market="h2h_1x2",
        selection="draw",
        decimal_odds=Decimal("3.40"),
        implied_probability=Decimal("0.2941"),
        no_vig_probability=Decimal("0.2800"),
    )

    # Order 1: [p1, p2, p3]
    ev1 = SelectedEvidence(
        fixture_id=fix_info.fixture_id,
        forecast_phase=ForecastPhase.MORNING,
        as_of=as_of,
        fixture=fix_info,
        odds_set=odds_set,
        odds_prices=[p1, p2, p3],
    )
    m1 = build_source_manifest(ev1)
    f1 = build_features(ev1)
    q1 = evaluate_data_quality(ev1, f1, m1)
    ctx1 = assemble_match_context_v1(ev1, f1, q1, m1)

    # Order 2: [p3, p1, p2] (reversed/scrambled)
    ev2 = SelectedEvidence(
        fixture_id=fix_info.fixture_id,
        forecast_phase=ForecastPhase.MORNING,
        as_of=as_of,
        fixture=fix_info,
        odds_set=odds_set,
        odds_prices=[p3, p1, p2],
    )
    m2 = build_source_manifest(ev2)
    f2 = build_features(ev2)
    q2 = evaluate_data_quality(ev2, f2, m2)
    ctx2 = assemble_match_context_v1(ev2, f2, q2, m2)

    assert ctx1.canonical_json() == ctx2.canonical_json()
    assert ctx1.market_snapshot.bookmakers == ["bet365", "betfair", "pinnacle"]


async def test_previous_odds_provider_mismatch_yields_no_movement(
    m6_session_factory: Any,
) -> None:
    """M6.2 §8 & §15.10: An earlier odds snapshot set from a DIFFERENT provider
    must not be paired for odds movement calculation.
    """
    kickoff = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)
    ids = await _seed_test_fixture(m6_session_factory, kickoff_at=kickoff)
    fid = ids["fixture_id"]
    t_as_of = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)

    cur_odds_id = uuid.uuid4()
    diff_prov_odds_id = uuid.uuid4()

    async with m6_session_factory() as session:
        # Current odds set: provider "theoddsapi"
        cur_odds = OddsSnapshotSet(
            id=cur_odds_id,
            fixture_id=fid,
            provider="theoddsapi",
            captured_at=t_as_of,
            market_whitelist_jsonb=["h2h_1x2"],
        )
        cur_p = OddsPrice(
            snapshot_set_id=cur_odds_id,
            bookmaker="sportsbook",
            market="h2h_1x2",
            selection="home",
            decimal_odds=Decimal("2.00"),
            implied_probability=Decimal("0.50"),
            no_vig_probability=Decimal("0.48"),
        )
        # Earlier odds set: provider "other_odds_feed" (mismatch!)
        prev_odds = OddsSnapshotSet(
            id=diff_prov_odds_id,
            fixture_id=fid,
            provider="other_odds_feed",
            captured_at=t_as_of - timedelta(hours=3),
            market_whitelist_jsonb=["h2h_1x2"],
        )
        prev_p = OddsPrice(
            snapshot_set_id=diff_prov_odds_id,
            bookmaker="sportsbook",
            market="h2h_1x2",
            selection="home",
            decimal_odds=Decimal("1.80"),
            implied_probability=Decimal("0.55"),
            no_vig_probability=Decimal("0.53"),
        )
        session.add_all([cur_odds, prev_odds])
        await session.flush()
        session.add_all([cur_p, prev_p])
        await session.commit()

    async with m6_session_factory() as session:
        rec, q, f, ctx = await __build_and_persist_match_context(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.MORNING,
            as_of=t_as_of,
        )

    # Provider mismatch must result in no previous odds set selected and movement = None
    assert "prev_odds" not in ctx.source_manifest.sources
    assert ctx.market_snapshot.movement.get("odds_move_home") is None
    assert ctx.market_snapshot.movement.get("odds_move_over25") is None


async def test_provider_mapping_historical_semantics_and_isolation(
    m6_session_factory: Any,
) -> None:
    """M6.2 §11, §15.13, §15.14: ProviderEntityId selection obeys first_seen_at <= as_of
    and requesting a specific provider never falls back to another provider mapping.
    """
    from sports_intelligence.context.selector import select_evidence

    kickoff = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)
    ids = await _seed_test_fixture(m6_session_factory, kickoff_at=kickoff)
    fid = ids["fixture_id"]
    hid = ids["home_team_id"]
    aid = ids["away_team_id"]

    t_as_of = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)

    async with m6_session_factory() as session:
        # Delete existing mappings to have full control
        await session.execute(delete(ProviderEntityId))

        # Home team: mapping for "api_football" seen 5 days before as_of
        p_home_past = ProviderEntityId(
            provider="api_football",
            entity_type="team",
            internal_entity_id=hid,
            external_id="api-home-42",
            first_seen_at=t_as_of - timedelta(days=5),
        )
        # Away team: mapping for "mock" seen in the FUTURE (after as_of)
        p_away_future = ProviderEntityId(
            provider="mock",
            entity_type="team",
            internal_entity_id=aid,
            external_id="mock-away-99",
            first_seen_at=t_as_of + timedelta(hours=2),
        )
        session.add_all([p_home_past, p_away_future])
        await session.commit()

    async with m6_session_factory() as session:
        evidence = await select_evidence(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.MORNING,
            as_of=t_as_of,
        )

    info = evidence.fixture
    # Home team api_football mapping is present
    assert info.get_home_external_id("api_football") == "api-home-42"
    # Requesting a different provider mapping must return None (NO fallback!)
    assert info.get_home_external_id("theoddsapi") is None
    assert info.get_home_external_id("mock") is None

    # Away team mapping was first_seen_at > as_of, so it MUST be excluded at as_of
    assert info.get_away_external_id("mock") is None
    assert info.get_away_external_id() is None


async def test_metadata_team_identity_propagation_and_isolation(
    m6_session_factory: Any,
) -> None:
    """M6.3 §2 & §13.3-5: Metadata snapshot team IDs (A/B) strictly drive all evidence
    selection even after canonical fixture teams are mutated to A/C.
    Availability, lineups, and provider mappings for team C must never be selected.
    """
    kickoff = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)
    ids = await _seed_test_fixture(m6_session_factory, kickoff_at=kickoff, create_metadata=False)
    fid = ids["fixture_id"]
    lid = ids["league_id"]
    sid = ids["season_id"]
    hid = ids["home_team_id"]
    aid_b = ids["away_team_id"]

    t0 = datetime(2026, 8, 20, 10, 0, tzinfo=UTC)
    t_as_of = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)

    async with m6_session_factory() as session:
        # Team C (rogue / later mutated team)
        team_c = Team(name="Team C", country="England")
        session.add(team_c)
        await session.flush()
        aid_c = team_c.id

        # Authoritative metadata snapshot has teams A and B
        meta = FixtureMetadataSnapshot(
            id=uuid.uuid4(),
            fixture_id=fid,
            provider="api_football",
            provider_fixture_id="fix-123",
            captured_at=t0,
            league_id=lid,
            season_id=sid,
            home_team_id=hid,
            away_team_id=aid_b,
            observed_home_team_name="Arsenal",
            observed_away_team_name="Team B",
            kickoff_at=kickoff,
            venue="Emirates Stadium",
            round="Round 1",
            status="NS",
            source_version="v1",
        )
        session.add(meta)

        # Later canonical fixture is mutated to away team C!
        fix = await session.get(Fixture, fid)
        assert fix is not None
        fix.away_team_id = aid_c

        # Availability: team B (historic) vs team C (rogue)
        avail_b = AvailabilitySnapshot(
            provider="mock",
            fixture_id=fid,
            team_id=aid_b,
            captured_at=t_as_of - timedelta(hours=2),
            availability_state="KNOWN_PRESENT",
            players_jsonb=[{"player_name": "Player B", "missing": True}],
            impact_flags_jsonb=[],
            conflicts_jsonb=[],
        )
        avail_c = AvailabilitySnapshot(
            provider="mock",
            fixture_id=fid,
            team_id=aid_c,
            captured_at=t_as_of - timedelta(hours=1),
            availability_state="KNOWN_PRESENT",
            players_jsonb=[{"player_name": "Player C", "missing": True}],
            impact_flags_jsonb=[],
            conflicts_jsonb=[],
        )
        # Lineup: team B vs team C
        lineup_b = LineupSnapshot(
            provider="mock",
            fixture_id=fid,
            team_id=aid_b,
            captured_at=t_as_of - timedelta(hours=2),
            confirmed=True,
            formation="4-4-2",
            players_jsonb=[{"name": "Defender B", "position": "D"}],
            publication_state="CONFIRMED",
        )
        lineup_c = LineupSnapshot(
            provider="mock",
            fixture_id=fid,
            team_id=aid_c,
            captured_at=t_as_of - timedelta(hours=1),
            confirmed=True,
            formation="3-5-2",
            players_jsonb=[{"name": "Defender C", "position": "D"}],
            publication_state="CONFIRMED",
        )
        # Provider mapping: team B vs team C
        map_b = ProviderEntityId(
            provider="api_football",
            entity_type="team",
            internal_entity_id=aid_b,
            external_id="team-b-ext",
            first_seen_at=t0,
        )
        map_c = ProviderEntityId(
            provider="api_football",
            entity_type="team",
            internal_entity_id=aid_c,
            external_id="team-c-ext",
            first_seen_at=t0,
        )
        session.add_all([avail_b, avail_c, lineup_b, lineup_c, map_b, map_c])
        await session.commit()

    async with m6_session_factory() as session:
        rec, q, f, ctx = await _build_test_context(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.PREMATCH,
            as_of=t_as_of,
        )

    # Context must strictly preserve Team B identity, never Team C
    assert ctx.fixture_identity.away_team_id == str(aid_b)
    assert ctx.fixture_identity.away_team_name == "Team B"

    # Availability must be from team B
    assert ctx.availability.away_missing_count == 1
    assert "away_availability" in ctx.source_manifest.sources
    assert ctx.source_manifest.sources["away_availability"].snapshot_id == str(avail_b.id)

    # Lineup must be from team B
    assert ctx.lineups.away_formation == "4-4-2"
    assert "away_lineup" in ctx.source_manifest.sources
    assert ctx.source_manifest.sources["away_lineup"].snapshot_id == str(lineup_b.id)

    # Provider mapping must be for team B, never team C
    away_maps = ctx.fixture_identity.away_provider_mappings
    ext_ids = {m["external_id"] for m in away_maps}
    assert "team-b-ext" in ext_ids
    assert "team-c-ext" not in ext_ids


async def test_different_freshness_policies_create_separate_quality_reports(
    m6_session_factory: Any,
) -> None:
    """M6.3 §5-6, §13.10-11: Reports with identical evidence and weights but different
    freshness policy TTLs produce distinct freshness fingerprints and both persist cleanly.
    """
    kickoff = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)
    ids = await _seed_test_fixture(m6_session_factory, kickoff_at=kickoff)
    fid = ids["fixture_id"]
    t_as_of = datetime(2026, 8, 22, 10, 0, tzinfo=UTC)

    policy = QualityPolicy(weights=QualityWeights(form=0.20))
    s1 = Settings(app_env="mock", freshness_odds_seconds=300)
    s2 = Settings(app_env="mock", freshness_odds_seconds=900)
    fp1 = FreshnessPolicy(s1)
    fp2 = FreshnessPolicy(s2)

    async with m6_session_factory() as session:
        rec1, q1, _, _ = await _build_test_context(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.MORNING,
            as_of=t_as_of,
            policy=policy,
            freshness_policy=fp1,
        )

    async with m6_session_factory() as session:
        rec2, q2, _, _ = await _build_test_context(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.MORNING,
            as_of=t_as_of,
            policy=policy,
            freshness_policy=fp2,
        )

    assert q1.freshness_policy_fingerprint != q2.freshness_policy_fingerprint
    assert q1.freshness_policy_jsonb["freshness_odds_seconds"] == 300
    assert q2.freshness_policy_jsonb["freshness_odds_seconds"] == 900

    # Both coexist in DB
    async with m6_session_factory() as session:
        reports = (
            (
                await session.execute(
                    select(DataQualityReport).where(
                        DataQualityReport.fixture_id == fid,
                        DataQualityReport.as_of == t_as_of,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(reports) == 2
        fp_set = {r.freshness_policy_fingerprint for r in reports}
        assert q1.freshness_policy_fingerprint in fp_set
        assert q2.freshness_policy_fingerprint in fp_set


async def test_freshness_transition_creates_new_context_opportunity_and_dedupes(
    m6_session_factory: Any,
) -> None:
    """M6.3 §8 & §13.12-14: When evidence crosses from fresh to stale, freshness generation
    changes and produces one new context job, while duplicate scans inside same state dedupe.
    """
    from unittest.mock import patch

    from sports_intelligence.collectors.pre_match_scan import PreMatchDecision
    from sports_intelligence.workers.tasks.context import build_match_context_task
    from sports_intelligence.workers.tasks.pre_match import _try_enqueue_context_build

    kickoff = datetime(2026, 8, 22, 20, 0, tzinfo=UTC)
    ids = await _seed_test_fixture(m6_session_factory, kickoff_at=kickoff)
    fid = ids["fixture_id"]

    # Odds captured at 09:00 with TTL = 1 hour (3600s)
    odds_id = uuid.uuid4()
    t_odds = datetime(2026, 8, 22, 9, 0, tzinfo=UTC)
    async with m6_session_factory() as session:
        odds = OddsSnapshotSet(
            id=odds_id,
            fixture_id=fid,
            provider="theoddsapi",
            captured_at=t_odds,
            market_whitelist_jsonb=["h2h_1x2"],
        )
        session.add(odds)
        await session.commit()

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

    enqueued_jobs: list[str] = []

    def mock_apply_async(*args: Any, **kwargs: Any) -> None:
        enqueued_jobs.append(kwargs["args"][0])

    with patch.object(build_match_context_task, "apply_async", mock_apply_async):
        # 1. At 09:30, odds are FRESH (within 1h TTL).
        t_fresh = datetime(2026, 8, 22, 9, 30, tzinfo=UTC)
        await _try_enqueue_context_build(m6_session_factory, decision, as_of=t_fresh)
        assert len(enqueued_jobs) == 1
        job1_id = enqueued_jobs[0]

        # 2. Duplicate scan at 09:40 (still fresh) -> must DEDUPE (no new task)
        t_fresh_dup = datetime(2026, 8, 22, 9, 40, tzinfo=UTC)
        await _try_enqueue_context_build(m6_session_factory, decision, as_of=t_fresh_dup)
        assert len(enqueued_jobs) == 1

        # 3. At 11:30, odds crossed TTL and are now STALE -> new context opportunity!
        t_stale = datetime(2026, 8, 22, 11, 30, tzinfo=UTC)
        await _try_enqueue_context_build(m6_session_factory, decision, as_of=t_stale)
        assert len(enqueued_jobs) == 2
        job2_id = enqueued_jobs[1]
        assert job2_id != job1_id

        # 4. Duplicate scan at 11:45 (still in same stale generation) -> must DEDUPE!
        t_stale_dup = datetime(2026, 8, 22, 11, 45, tzinfo=UTC)
        await _try_enqueue_context_build(m6_session_factory, decision, as_of=t_stale_dup)
        assert len(enqueued_jobs) == 2


async def test_mutable_league_metadata_change_does_not_alter_historical_context_replay(
    m6_session_factory: Any,
) -> None:
    """Historical MatchContext reconstruction must not depend on mutable current League.name/slug.

    Mutating League row after historical as_of must not change historical MatchContext identity,
    source fingerprint, or context hash.
    """
    kickoff = datetime(2026, 8, 22, 15, 0, tzinfo=UTC)
    t0_captured = kickoff - timedelta(days=2)
    as_of = kickoff - timedelta(hours=6)

    ids = await _seed_test_fixture(
        m6_session_factory,
        kickoff_at=kickoff,
        create_metadata=True,
        metadata_captured_at=t0_captured,
    )
    fid = ids["fixture_id"]
    lid = ids["league_id"]

    # Explicitly verify the metadata snapshot at T0 has observed league name and slug
    async with m6_session_factory() as session:
        meta_stmt = select(FixtureMetadataSnapshot).where(FixtureMetadataSnapshot.fixture_id == fid)
        meta_row = (await session.execute(meta_stmt)).scalar_one()
        assert meta_row.observed_league_name == "Premier League"
        assert meta_row.observed_league_slug.startswith("league-")
        original_slug = meta_row.observed_league_slug

    # 1. Build historical context at T0
    policy = QualityPolicy(weights=QualityWeights(form=0.1), min_predict_score=0.65)
    freshness_policy = FreshnessPolicy(Settings(app_env="mock"))
    build_policy = ContextBuildPolicy(
        quality_policy=policy,
        freshness_policy=freshness_policy,
        research_enabled=True,
    )
    async with m6_session_factory() as session:
        ctx1_rec, qual1_rec, feat1_rec, ctx1 = await build_and_persist_match_context(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.MORNING,
            as_of=as_of,
            build_policy=build_policy,
        )
        await session.commit()

    assert ctx1.fixture_identity.league_name == "Premier League"
    assert ctx1.fixture_identity.league_slug == original_slug
    assert (
        feat1_rec.source_manifest_jsonb["sources"]["fixture_metadata"]["details"][
            "observed_league_name"
        ]
        == "Premier League"
    )

    # 2. Mutate mutable canonical League row in database
    async with m6_session_factory() as session:
        await session.execute(
            update(League)
            .where(League.id == lid)
            .values(name="Barclays Premier League", slug="barclays-pl")
        )
        await session.commit()

    # Verify League table was actually updated
    async with m6_session_factory() as session:
        l_updated = await session.get(League, lid)
        assert l_updated is not None
        assert l_updated.name == "Barclays Premier League"
        assert l_updated.slug == "barclays-pl"

    # 3. Rebuild historical context at the exact same as_of
    # Select evidence and build context again
    async with m6_session_factory() as session:
        evidence2 = await select_evidence(
            session,
            fixture_id=fid,
            forecast_phase=ForecastPhase.MORNING,
            as_of=as_of,
        )
        manifest2 = build_source_manifest(evidence2)
        features2 = build_features(evidence2)
        quality2 = evaluate_data_quality(
            evidence2,
            features2,
            manifest2,
            policy=build_policy.quality_policy,
            freshness_policy=build_policy.freshness_policy,
        )
        ctx2 = assemble_match_context_v1(evidence2, features2, quality2, manifest2)

    # 4. Strict assertions: identity, manifest, source_fingerprint, and context_hash MUST MATCH!
    assert ctx2.fixture_identity.league_name == "Premier League"
    assert ctx2.fixture_identity.league_slug == original_slug
    assert manifest2.source_fingerprint == feat1_rec.source_fingerprint
    assert (
        hashlib.sha256(ctx2.canonical_json().encode("utf-8")).hexdigest() == ctx1_rec.context_hash
    )


async def test_provider_mapping_deterministic_selection_and_ordering_across_insertion_orders(
    m6_session_factory: Any,
) -> None:
    """ProviderEntityId query/selection must be deterministic across insertion orders.

    - Multiple mappings for same provider <= as_of deterministically select latest first_seen_at.
    - Historical cutoff first_seen_at <= as_of is preserved (future mappings excluded).
    - List ordering of mappings is deterministic across different insertion orders.
    - Resulting source_manifest, source_fingerprint, and context_hash are identical.
    """
    kickoff = datetime(2026, 8, 22, 15, 0, tzinfo=UTC)
    as_of = kickoff - timedelta(hours=3)

    # We test two fixtures with the same logical team mappings inserted in opposite orders
    # Fixture 1: Insert mappings in order [M_fut, M_old, M_new, M_other]
    # Fixture 2: Insert mappings in order [M_other, M_new, M_old, M_fut]

    ids = await _seed_test_fixture(
        m6_session_factory,
        kickoff_at=kickoff,
        create_metadata=True,
        metadata_captured_at=kickoff - timedelta(days=2),
    )
    fid = ids["fixture_id"]
    hid = ids["home_team_id"]

    fixed_mapping_ids = {
        ("theoddsapi", "999"): uuid.UUID("11111111-0000-0000-0000-000000000001"),
        ("theoddsapi", "100"): uuid.UUID("11111111-0000-0000-0000-000000000002"),
        ("theoddsapi", "200"): uuid.UUID("11111111-0000-0000-0000-000000000003"),
        ("api_football", "300"): uuid.UUID("11111111-0000-0000-0000-000000000004"),
    }

    async def _evaluate_mappings(
        mapping_specs: list[tuple[str, str, datetime]],
    ) -> tuple[str, str]:
        # Reset mappings for this team to evaluate specific insertion order
        async with m6_session_factory() as session:
            await session.execute(
                delete(ProviderEntityId).where(ProviderEntityId.internal_entity_id == hid)
            )
            for prov, ext_id, seen_at in mapping_specs:
                session.add(
                    ProviderEntityId(
                        id=fixed_mapping_ids[(prov, ext_id)],
                        provider=prov,
                        entity_type="team",
                        internal_entity_id=hid,
                        external_id=ext_id,
                        first_seen_at=seen_at,
                    )
                )
            await session.commit()

        async with m6_session_factory() as session:
            ev = await select_evidence(
                session,
                fixture_id=fid,
                forecast_phase=ForecastPhase.PREMATCH,
                as_of=as_of,
            )
            # Verify latest <= as_of is selected for theoddsapi ("200"), future ("999") excluded
            assert ev.fixture.home_provider_external_ids["theoddsapi"] == "200"
            assert ev.fixture.home_provider_external_ids["api_football"] == "300"
            # Verify future mapping is not in the list
            ext_ids_in_list = [m.external_id for m in ev.fixture.home_provider_mappings]
            assert "999" not in ext_ids_in_list
            assert "200" in ext_ids_in_list
            assert "100" in ext_ids_in_list

            man = build_source_manifest(ev)
            feat = build_features(ev)
            qual = evaluate_data_quality(ev, feat, man)
            ctx = assemble_match_context_v1(ev, feat, qual, man)
            chash = hashlib.sha256(ctx.canonical_json().encode("utf-8")).hexdigest()
            return man.source_fingerprint, chash

    spec_order_1 = [
        ("theoddsapi", "999", as_of + timedelta(days=1)),  # future
        ("theoddsapi", "100", as_of - timedelta(days=4)),  # older
        ("theoddsapi", "200", as_of - timedelta(days=1)),  # newer <= as_of
        ("api_football", "300", as_of - timedelta(days=3)),
    ]
    spec_order_2 = [
        ("api_football", "300", as_of - timedelta(days=3)),
        ("theoddsapi", "200", as_of - timedelta(days=1)),  # newer <= as_of
        ("theoddsapi", "100", as_of - timedelta(days=4)),  # older
        ("theoddsapi", "999", as_of + timedelta(days=1)),  # future
    ]

    fp1, hash1 = await _evaluate_mappings(spec_order_1)
    fp2, hash2 = await _evaluate_mappings(spec_order_2)

    # Canonical order guarantees identical fingerprint and context hash
    assert fp1 == fp2
    assert hash1 == hash2


async def test_historical_metadata_unavailable_task_and_refusal_persistence(
    m6_session_factory: Any,
) -> None:
    """Historical context build task raises HistoricalFixtureMetadataUnavailable without traceback,
    marks the Celery job FAILED in the database ledger, and persists zero context records."""
    kickoff = datetime(2026, 8, 22, 15, 0, tzinfo=UTC)
    as_of = kickoff - timedelta(hours=6)

    # Seed fixture WITHOUT metadata snapshot
    ids = await _seed_test_fixture(
        m6_session_factory,
        kickoff_at=kickoff,
        create_metadata=False,
    )
    fid = ids["fixture_id"]
    job_uuid = uuid.uuid4()

    # Pre-create Job record in PENDING status
    async with m6_session_factory() as session:
        job = Job(
            id=job_uuid,
            job_type="context_build",
            status=JobStatus.PENDING.value,
            idempotency_key=f"test_job_{job_uuid.hex}",
            scheduled_for=as_of,
        )
        session.add(job)
        await session.commit()

    # Running task directly raises HistoricalFixtureMetadataUnavailable
    with pytest.raises(HistoricalFixtureMetadataUnavailable):
        await _run_build(
            str(job_uuid),
            str(fid),
            ForecastPhase.MORNING.value,
            as_of.isoformat(),
            session_factory=m6_session_factory,
        )

    # 1. Job must be marked FAILED in jobs table
    async with m6_session_factory() as session:
        job_row = await session.get(Job, job_uuid)
        assert job_row is not None
        assert job_row.status == JobStatus.FAILED.value

        # 2. Attempt recorded in job_attempts
        att_stmt = select(JobAttempt).where(JobAttempt.job_id == job_uuid)
        attempts = (await session.execute(att_stmt)).scalars().all()
        assert len(attempts) == 1
        assert attempts[0].status == JobStatus.FAILED.value
        assert attempts[0].error_class == "HistoricalFixtureMetadataUnavailable"

        # 3. ZERO FeatureSnapshot, DataQualityReport, or MatchContext records persisted
        feat_cnt = (
            await session.execute(
                select(func.count(FeatureSnapshot.id)).where(FeatureSnapshot.fixture_id == fid)
            )
        ).scalar_one()
        qual_cnt = (
            await session.execute(
                select(func.count(DataQualityReport.id)).where(DataQualityReport.fixture_id == fid)
            )
        ).scalar_one()
        ctx_cnt = (
            await session.execute(
                select(func.count(MatchContextRecord.id)).where(
                    MatchContextRecord.fixture_id == fid
                )
            )
        ).scalar_one()

        assert feat_cnt == 0
        assert qual_cnt == 0
        assert ctx_cnt == 0
