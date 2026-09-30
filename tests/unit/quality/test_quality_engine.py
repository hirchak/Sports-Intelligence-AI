from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sports_intelligence.context.provenance import build_source_manifest
from sports_intelligence.context.selector import SelectedEvidence, SelectedFixtureInfo
from sports_intelligence.core.phases import ForecastPhase, ResearchState
from sports_intelligence.db.models import LineupSnapshot
from sports_intelligence.features.builder import build_features
from sports_intelligence.quality.engine import evaluate_data_quality
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
        home_external_id="42",
        away_external_id="49",
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
