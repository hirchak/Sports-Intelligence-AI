from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sports_intelligence.context.provenance import build_source_manifest
from sports_intelligence.context.selector import SelectedEvidence, SelectedFixtureInfo
from sports_intelligence.core.phases import ForecastPhase, ResearchState
from sports_intelligence.db.models import (
    AvailabilitySnapshot,
    LineupSnapshot,
    OddsPrice,
    OddsSnapshotSet,
)
from sports_intelligence.features.builder import build_features
from sports_intelligence.quality.engine import QualityWeights, evaluate_data_quality
from sports_intelligence.research.service import FixtureResearchView


def _fixture_info() -> SelectedFixtureInfo:
    return SelectedFixtureInfo(
        fixture_id=uuid.uuid4(),
        league_id=uuid.uuid4(),
        season_id=uuid.uuid4(),
        home_team_id=uuid.uuid4(),
        away_team_id=uuid.uuid4(),
        kickoff_at=datetime(2026, 8, 22, 15, 0, tzinfo=UTC),
        venue="Emirates Stadium",
        round="Regular Season - 1",
        status="NS",
        league_slug="premier-league",
        league_name="Premier League",
        home_team_name="Arsenal",
        away_team_name="Chelsea",
        home_provider_mappings=[],
        away_provider_mappings=[],
    )


def test_quality_engine_morning_excludes_lineups_from_denominator() -> None:
    fix_info = _fixture_info()
    as_of = fix_info.kickoff_at - timedelta(hours=8)

    evidence = SelectedEvidence(
        fixture_id=fix_info.fixture_id,
        forecast_phase=ForecastPhase.MORNING,
        as_of=as_of,
        fixture=fix_info,
        standings=None,
        home_team_stats=None,
        away_team_stats=None,
        home_form=None,
        away_form=None,
        home_availability=None,
        away_availability=None,
        home_lineup=None,
        away_lineup=None,
        odds_set=None,
    )

    manifest = build_source_manifest(evidence)
    features = build_features(evidence)
    report = evaluate_data_quality(evidence, features, manifest)

    # In MORNING phase, lineups dimension score is not penalized for missing lineups
    assert report.forecast_phase == "MORNING"
    assert "lineups" in report.dimension_scores
    # Active weights in evaluation did not count lineup missingness against total score


def test_quality_engine_prematch_evaluates_confirmed_lineups() -> None:
    fix_info = _fixture_info()
    as_of = fix_info.kickoff_at - timedelta(minutes=45)

    home_lineup = LineupSnapshot(
        provider="api_football",
        fixture_id=fix_info.fixture_id,
        team_id=fix_info.home_team_id,
        captured_at=as_of,
        confirmed=True,
        formation="4-3-3",
        players_jsonb=[],
        publication_state="CONFIRMED",
    )
    away_lineup = LineupSnapshot(
        provider="api_football",
        fixture_id=fix_info.fixture_id,
        team_id=fix_info.away_team_id,
        captured_at=as_of,
        confirmed=True,
        formation="4-2-3-1",
        players_jsonb=[],
        publication_state="CONFIRMED",
    )

    evidence = SelectedEvidence(
        fixture_id=fix_info.fixture_id,
        forecast_phase=ForecastPhase.PREMATCH,
        as_of=as_of,
        fixture=fix_info,
        standings=None,
        home_team_stats=None,
        away_team_stats=None,
        home_form=None,
        away_form=None,
        home_availability=None,
        away_availability=None,
        home_lineup=home_lineup,
        away_lineup=away_lineup,
        odds_set=None,
    )

    manifest = build_source_manifest(evidence)
    features = build_features(evidence)
    report = evaluate_data_quality(evidence, features, manifest)

    assert report.forecast_phase == "PREMATCH"
    assert report.dimension_scores["lineups"] == 1.0


def test_quality_engine_research_states_and_conflict_penalties() -> None:
    fix_info = _fixture_info()
    as_of = fix_info.kickoff_at - timedelta(hours=4)

    # Research with provider error
    res_error = FixtureResearchView(
        fixture_id=fix_info.fixture_id,
        status=ResearchState.PROVIDER_ERROR.value,
        last_captured_at=as_of,
        documents_count=0,
        claims_count=0,
        conflicts_count=0,
    )

    evidence_error = SelectedEvidence(
        fixture_id=fix_info.fixture_id,
        forecast_phase=ForecastPhase.MORNING,
        as_of=as_of,
        fixture=fix_info,
        standings=None,
        home_team_stats=None,
        away_team_stats=None,
        home_form=None,
        away_form=None,
        home_availability=None,
        away_availability=None,
        home_lineup=None,
        away_lineup=None,
        odds_set=None,
        research=res_error,
    )
    rep_error = evaluate_data_quality(
        evidence_error,
        build_features(evidence_error),
        build_source_manifest(evidence_error),
    )
    assert rep_error.dimension_scores["research"] == 0.20
    assert any(err["status"] == "PROVIDER_ERROR" for err in rep_error.provider_errors)

    # Research with conflicts
    res_conflicts = FixtureResearchView(
        fixture_id=fix_info.fixture_id,
        status=ResearchState.AVAILABLE.value,
        last_captured_at=as_of,
        documents_count=5,
        claims_count=4,
        conflicts_count=2,
    )
    evidence_conflicts = SelectedEvidence(
        fixture_id=fix_info.fixture_id,
        forecast_phase=ForecastPhase.MORNING,
        as_of=as_of,
        fixture=fix_info,
        standings=None,
        home_team_stats=None,
        away_team_stats=None,
        home_form=None,
        away_form=None,
        home_availability=None,
        away_availability=None,
        home_lineup=None,
        away_lineup=None,
        odds_set=None,
        research=res_conflicts,
    )
    rep_conflicts = evaluate_data_quality(
        evidence_conflicts,
        build_features(evidence_conflicts),
        build_source_manifest(evidence_conflicts),
    )
    assert len(rep_conflicts.conflicts) > 0


def test_quality_bands_and_can_predict_threshold() -> None:
    fix_info = _fixture_info()
    as_of = fix_info.kickoff_at - timedelta(hours=2)

    # Empty evidence -> should produce abstain band and can_predict=False
    evidence_empty = SelectedEvidence(
        fixture_id=fix_info.fixture_id,
        forecast_phase=ForecastPhase.PREMATCH,
        as_of=as_of,
        fixture=fix_info,
        standings=None,
        home_team_stats=None,
        away_team_stats=None,
        home_form=None,
        away_form=None,
        home_availability=None,
        away_availability=None,
        home_lineup=None,
        away_lineup=None,
        odds_set=None,
    )
    rep_empty = evaluate_data_quality(
        evidence_empty,
        build_features(evidence_empty),
        build_source_manifest(evidence_empty),
    )
    assert rep_empty.overall_score < 0.65
    assert rep_empty.quality_band == "abstain"
    assert rep_empty.can_predict is False
    assert "both_odds_and_form_missing" in rep_empty.critical_missing


def test_stale_odds_penalty_and_warning() -> None:
    fix_info = _fixture_info()
    as_of = fix_info.kickoff_at - timedelta(minutes=30)  # PREMATCH

    set_fresh_id = uuid.uuid4()
    odds_fresh = OddsSnapshotSet(
        id=set_fresh_id,
        fixture_id=fix_info.fixture_id,
        provider="theoddsapi",
        captured_at=as_of - timedelta(minutes=15),  # 15m old (< 30m TTL)
        market_whitelist_jsonb=["h2h_1x2"],
    )
    prices_fresh = [
        OddsPrice(
            snapshot_set_id=set_fresh_id,
            bookmaker="bet365",
            market="h2h_1x2",
            selection="home",
            decimal_odds=Decimal("2.10"),
            implied_probability=Decimal("0.476190"),
            no_vig_probability=Decimal("0.450000"),
        ),
        OddsPrice(
            snapshot_set_id=set_fresh_id,
            bookmaker="bet365",
            market="h2h_1x2",
            selection="draw",
            decimal_odds=Decimal("3.40"),
            implied_probability=Decimal("0.294118"),
            no_vig_probability=Decimal("0.280000"),
        ),
        OddsPrice(
            snapshot_set_id=set_fresh_id,
            bookmaker="bet365",
            market="h2h_1x2",
            selection="away",
            decimal_odds=Decimal("3.50"),
            implied_probability=Decimal("0.285714"),
            no_vig_probability=Decimal("0.270000"),
        ),
    ]
    ev_fresh = SelectedEvidence(
        fixture_id=fix_info.fixture_id,
        forecast_phase=ForecastPhase.PREMATCH,
        as_of=as_of,
        fixture=fix_info,
        standings=None,
        home_team_stats=None,
        away_team_stats=None,
        home_form=None,
        away_form=None,
        home_availability=None,
        away_availability=None,
        home_lineup=None,
        away_lineup=None,
        odds_set=odds_fresh,
        odds_prices=prices_fresh,
    )
    rep_fresh = evaluate_data_quality(
        ev_fresh, build_features(ev_fresh), build_source_manifest(ev_fresh)
    )
    assert "odds" not in rep_fresh.stale_sources
    assert rep_fresh.dimension_scores["odds"] == 0.85  # 1X2 present, secondary not

    # Stale odds: 4 hours old in PREMATCH (TTL is 30m)
    set_stale_id = uuid.uuid4()
    odds_stale = OddsSnapshotSet(
        id=set_stale_id,
        fixture_id=fix_info.fixture_id,
        provider="theoddsapi",
        captured_at=as_of - timedelta(hours=4),
        market_whitelist_jsonb=["h2h_1x2"],
    )
    prices_stale = [
        OddsPrice(
            snapshot_set_id=set_stale_id,
            bookmaker="bet365",
            market="h2h_1x2",
            selection="home",
            decimal_odds=Decimal("2.10"),
            implied_probability=Decimal("0.476190"),
            no_vig_probability=Decimal("0.450000"),
        ),
        OddsPrice(
            snapshot_set_id=set_stale_id,
            bookmaker="bet365",
            market="h2h_1x2",
            selection="draw",
            decimal_odds=Decimal("3.40"),
            implied_probability=Decimal("0.294118"),
            no_vig_probability=Decimal("0.280000"),
        ),
        OddsPrice(
            snapshot_set_id=set_stale_id,
            bookmaker="bet365",
            market="h2h_1x2",
            selection="away",
            decimal_odds=Decimal("3.50"),
            implied_probability=Decimal("0.285714"),
            no_vig_probability=Decimal("0.270000"),
        ),
    ]
    ev_stale = SelectedEvidence(
        fixture_id=fix_info.fixture_id,
        forecast_phase=ForecastPhase.PREMATCH,
        as_of=as_of,
        fixture=fix_info,
        standings=None,
        home_team_stats=None,
        away_team_stats=None,
        home_form=None,
        away_form=None,
        home_availability=None,
        away_availability=None,
        home_lineup=None,
        away_lineup=None,
        odds_set=odds_stale,
        odds_prices=prices_stale,
    )
    rep_stale = evaluate_data_quality(
        ev_stale, build_features(ev_stale), build_source_manifest(ev_stale)
    )
    assert "odds" in rep_stale.stale_sources
    assert rep_stale.overall_score < rep_fresh.overall_score
    assert any("freshness ttl" in w.lower() for w in rep_stale.warnings)


def test_stale_availability_penalty() -> None:
    fix_info = _fixture_info()
    as_of = fix_info.kickoff_at - timedelta(hours=1)  # PREMATCH

    # Stale availability: 6 hours old in PREMATCH (TTL is 3 hours)
    home_avail = AvailabilitySnapshot(
        provider="api_football",
        fixture_id=fix_info.fixture_id,
        team_id=fix_info.home_team_id,
        captured_at=as_of - timedelta(hours=6),
        availability_state="KNOWN_PRESENT",
        players_jsonb=[],
        impact_flags_jsonb=[],
        conflicts_jsonb=[],
    )
    evidence = SelectedEvidence(
        fixture_id=fix_info.fixture_id,
        forecast_phase=ForecastPhase.PREMATCH,
        as_of=as_of,
        fixture=fix_info,
        standings=None,
        home_team_stats=None,
        away_team_stats=None,
        home_form=None,
        away_form=None,
        home_availability=home_avail,
        away_availability=None,
        home_lineup=None,
        away_lineup=None,
        odds_set=None,
    )
    report = evaluate_data_quality(
        evidence, build_features(evidence), build_source_manifest(evidence)
    )
    assert "home_availability" in report.stale_sources
    assert any("freshness ttl" in w.lower() for w in report.warnings)


def test_canonical_lineup_publication_states() -> None:
    fix_info = _fixture_info()
    as_of = fix_info.kickoff_at - timedelta(minutes=45)

    states_scores = [
        ("CONFIRMED", 1.0),
        ("NOT_YET_PUBLISHED", 0.40),
        ("UNSUPPORTED", 0.50),
        ("PROVIDER_ERROR", 0.20),
    ]
    for state, expected_score in states_scores:
        home_lineup = LineupSnapshot(
            provider="api_football",
            fixture_id=fix_info.fixture_id,
            team_id=fix_info.home_team_id,
            captured_at=as_of,
            confirmed=(state == "CONFIRMED"),
            publication_state=state,
            formation="4-3-3",
            players_jsonb=[],
        )
        away_lineup = LineupSnapshot(
            provider="api_football",
            fixture_id=fix_info.fixture_id,
            team_id=fix_info.away_team_id,
            captured_at=as_of,
            confirmed=(state == "CONFIRMED"),
            publication_state=state,
            formation="4-3-3",
            players_jsonb=[],
        )
        ev = SelectedEvidence(
            fixture_id=fix_info.fixture_id,
            forecast_phase=ForecastPhase.PREMATCH,
            as_of=as_of,
            fixture=fix_info,
            standings=None,
            home_team_stats=None,
            away_team_stats=None,
            home_form=None,
            away_form=None,
            home_availability=None,
            away_availability=None,
            home_lineup=home_lineup,
            away_lineup=away_lineup,
            odds_set=None,
        )
        rep = evaluate_data_quality(ev, build_features(ev), build_source_manifest(ev))
        assert rep.dimension_scores["lineups"] == expected_score
        if state == "PROVIDER_ERROR":
            assert any(err["source"] == "lineups" for err in rep.provider_errors)


def test_research_never_ran_vs_no_useful_results() -> None:
    fix_info = _fixture_info()
    as_of = fix_info.kickoff_at - timedelta(hours=3)

    # 1. Research run_id is None with status NO_USEFUL_RESULTS (never collected)
    res_never_ran = FixtureResearchView(
        fixture_id=fix_info.fixture_id,
        status="NO_USEFUL_RESULTS",
        run_id=None,
        last_captured_at=None,
        documents_count=0,
        claims_count=0,
        conflicts_count=0,
    )
    ev_never_ran = SelectedEvidence(
        fixture_id=fix_info.fixture_id,
        forecast_phase=ForecastPhase.MORNING,
        as_of=as_of,
        fixture=fix_info,
        standings=None,
        home_team_stats=None,
        away_team_stats=None,
        home_form=None,
        away_form=None,
        home_availability=None,
        away_availability=None,
        home_lineup=None,
        away_lineup=None,
        odds_set=None,
        research=res_never_ran,
    )
    rep_never_ran = evaluate_data_quality(
        ev_never_ran, build_features(ev_never_ran), build_source_manifest(ev_never_ran)
    )
    assert rep_never_ran.dimension_scores["research"] == 0.50
    assert any("No research run has been collected" in w for w in rep_never_ran.warnings)

    # 2. Legitimate run that produced NO_USEFUL_RESULTS
    res_legit = FixtureResearchView(
        fixture_id=fix_info.fixture_id,
        status="NO_USEFUL_RESULTS",
        run_id=uuid.uuid4(),
        last_captured_at=as_of,
        documents_count=0,
        claims_count=0,
        conflicts_count=0,
    )
    ev_legit = SelectedEvidence(
        fixture_id=fix_info.fixture_id,
        forecast_phase=ForecastPhase.MORNING,
        as_of=as_of,
        fixture=fix_info,
        standings=None,
        home_team_stats=None,
        away_team_stats=None,
        home_form=None,
        away_form=None,
        home_availability=None,
        away_availability=None,
        home_lineup=None,
        away_lineup=None,
        odds_set=None,
        research=res_legit,
    )
    rep_legit = evaluate_data_quality(
        ev_legit, build_features(ev_legit), build_source_manifest(ev_legit)
    )
    assert rep_legit.dimension_scores["research"] == 0.85
    assert not any("No research run has been collected" in w for w in rep_legit.warnings)


def test_quality_policy_persistence_and_custom_weights() -> None:
    fix_info = _fixture_info()
    as_of = fix_info.kickoff_at - timedelta(hours=3)

    custom_weights = QualityWeights(
        odds=0.50,
        form=0.50,
        fixture_identity=0.0,
        season_stats=0.0,
        availability=0.0,
        lineups=0.0,
        research=0.0,
    )
    ev = SelectedEvidence(
        fixture_id=fix_info.fixture_id,
        forecast_phase=ForecastPhase.MORNING,
        as_of=as_of,
        fixture=fix_info,
        standings=None,
        home_team_stats=None,
        away_team_stats=None,
        home_form=None,
        away_form=None,
        home_availability=None,
        away_availability=None,
        home_lineup=None,
        away_lineup=None,
        odds_set=None,
    )
    rep = evaluate_data_quality(
        ev,
        build_features(ev),
        build_source_manifest(ev),
        weights=custom_weights,
        min_predict_score=0.70,
    )
    assert rep.quality_policy["weights"]["odds"] == 0.50
    assert rep.quality_policy["weights"]["form"] == 0.50
    assert rep.quality_policy["min_predict_score"] == 0.70
    assert rep.quality_policy["policy_version"] == "quality_policy_v1"
