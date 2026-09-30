from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from sports_intelligence.context.builder import (
    assemble_match_context_v1,
    compute_build_config_fingerprint,
)
from sports_intelligence.context.models import (
    FixtureIdentitySection,
    MatchContextV1,
)
from sports_intelligence.context.provenance import build_source_manifest
from sports_intelligence.context.selector import SelectedEvidence, SelectedFixtureInfo
from sports_intelligence.core.config import Settings
from sports_intelligence.core.phases import ForecastPhase
from sports_intelligence.db.models import LineupSnapshot
from sports_intelligence.features.builder import build_features
from sports_intelligence.quality.engine import (
    QualityPolicy,
    QualityWeights,
    build_quality_policy,
    evaluate_data_quality,
)


def _base_fixture_info() -> SelectedFixtureInfo:
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
        fixture_metadata_snapshot_id=uuid.uuid4(),
        metadata_captured_at=datetime(2026, 8, 20, 10, 0, tzinfo=UTC),
    )


# --- 1. Settings Quality Config Validation Tests ---


def test_quality_settings_negative_weight_fails() -> None:
    with pytest.raises(ValidationError, match="Quality weight 'form' must be >= 0"):
        Settings(_env_file=None, quality_weight_form=-0.1)


def test_quality_settings_zero_total_weight_fails() -> None:
    with pytest.raises(ValidationError, match="Total quality weight must be > 0"):
        Settings(
            _env_file=None,
            quality_weight_fixture_identity=0.0,
            quality_weight_form=0.0,
            quality_weight_season_stats=0.0,
            quality_weight_availability=0.0,
            quality_weight_odds=0.0,
            quality_weight_research=0.0,
            quality_weight_lineups=0.0,
        )


def test_quality_settings_min_predict_score_range_fails() -> None:
    with pytest.raises(ValidationError, match="quality_min_predict_score must be between 0 and 1"):
        Settings(_env_file=None, quality_min_predict_score=1.5)
    with pytest.raises(ValidationError, match="quality_min_predict_score must be between 0 and 1"):
        Settings(_env_file=None, quality_min_predict_score=-0.1)


def test_quality_settings_band_thresholds_monotonic_fails() -> None:
    with pytest.raises(
        ValidationError,
        match="Quality band thresholds must satisfy 0 <= usable <= good <= excellent <= 1",
    ):
        # usable > good is invalid
        Settings(
            _env_file=None,
            quality_band_usable_min=0.85,
            quality_band_good_min=0.70,
            quality_band_excellent_min=0.90,
        )


def test_quality_settings_staleness_penalties_range_fails() -> None:
    with pytest.raises(ValidationError, match="quality_staleness_penalty must be >= 0"):
        Settings(_env_file=None, quality_staleness_penalty=-0.05)
    with pytest.raises(
        ValidationError, match="quality_max_staleness_penalty must be between 0 and 1"
    ):
        Settings(_env_file=None, quality_max_staleness_penalty=1.2)


# --- 2. QualityPolicy Direct Validation Tests ---


def test_quality_policy_validation_rules() -> None:
    with pytest.raises(ValueError, match="must be >= 0"):
        QualityPolicy(weights=QualityWeights(form=-0.5))

    with pytest.raises(ValueError, match="Total quality weight must be > 0"):
        QualityPolicy(
            weights=QualityWeights(
                fixture_identity=0,
                form=0,
                season_stats=0,
                availability=0,
                odds=0,
                research=0,
                lineups=0,
            )
        )

    with pytest.raises(ValueError, match="min_predict_score must be between 0 and 1"):
        QualityPolicy(min_predict_score=1.1)

    with pytest.raises(ValueError, match="Quality band thresholds must satisfy"):
        QualityPolicy(band_thresholds={"usable_with_warnings": 0.9, "good": 0.8, "excellent": 0.7})

    with pytest.raises(ValueError, match="staleness_penalty must be >= 0"):
        QualityPolicy(staleness_penalty=-0.1)

    with pytest.raises(ValueError, match="max_staleness_penalty must be between 0 and 1"):
        QualityPolicy(max_staleness_penalty=1.5)


# --- 3. Policy Fingerprint & BuildConfig Fingerprint ---


def test_policy_fingerprint_deterministic_and_variant() -> None:
    settings_a = Settings(_env_file=None, quality_weight_form=0.25)
    settings_b = Settings(_env_file=None, quality_weight_form=0.35)

    policy_a = build_quality_policy(settings_a)
    policy_b = build_quality_policy(settings_b)

    fp_a1 = policy_a.policy_fingerprint()
    fp_a2 = policy_a.policy_fingerprint()
    fp_b = policy_b.policy_fingerprint()

    assert fp_a1 == fp_a2
    assert len(fp_a1) == 64
    assert fp_a1 != fp_b


def test_compute_build_config_fingerprint_variance() -> None:
    fp1 = compute_build_config_fingerprint(
        context_schema_version="match_context_v1",
        feature_schema_version="features_v1",
        quality_schema_version="quality_v1",
        policy_fingerprint="fp-policy-a",
        research_enabled=True,
    )
    fp2 = compute_build_config_fingerprint(
        context_schema_version="match_context_v1",
        feature_schema_version="features_v1",
        quality_schema_version="quality_v1",
        policy_fingerprint="fp-policy-b",
        research_enabled=True,
    )
    fp3 = compute_build_config_fingerprint(
        context_schema_version="match_context_v1",
        feature_schema_version="features_v1",
        quality_schema_version="quality_v1",
        policy_fingerprint="fp-policy-a",
        research_enabled=False,
    )

    assert fp1 != fp2
    assert fp1 != fp3
    assert len(fp1) == 64


# --- 4. Strict MatchContext Schema Validation (extra='forbid') ---


def test_malformed_match_context_section_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        FixtureIdentitySection(
            fixture_id=str(uuid.uuid4()),
            league_id=str(uuid.uuid4()),
            home_team_id=str(uuid.uuid4()),
            away_team_id=str(uuid.uuid4()),
            kickoff_at="2026-08-22T15:00:00Z",
            status="NS",
            league_slug="pl",
            league_name="Premier League",
            rogue_field="unexpected",  # forbidden
        )


def test_malformed_top_level_match_context_rejected() -> None:
    fix_info = _base_fixture_info()
    as_of = fix_info.kickoff_at - timedelta(hours=6)
    ev = SelectedEvidence(
        fixture_id=fix_info.fixture_id,
        forecast_phase=ForecastPhase.MORNING,
        as_of=as_of,
        fixture=fix_info,
    )
    manifest = build_source_manifest(ev)
    feat = build_features(ev)
    qual = evaluate_data_quality(ev, feat, manifest)
    ctx = assemble_match_context_v1(ev, feat, qual, manifest)

    ctx_data = ctx.to_dict()
    ctx_data["extra_prediction_section"] = {"should_fail": True}

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        MatchContextV1(**ctx_data)


# --- 5. MORNING Lineup N/A Behavior ---


def test_stale_morning_lineup_zero_quality_effect() -> None:
    fix_info = _base_fixture_info()
    as_of = fix_info.kickoff_at - timedelta(hours=8)

    # 1. Evidence with NO lineup
    ev_no_lineup = SelectedEvidence(
        fixture_id=fix_info.fixture_id,
        forecast_phase=ForecastPhase.MORNING,
        as_of=as_of,
        fixture=fix_info,
    )
    manifest_no = build_source_manifest(ev_no_lineup)
    feat_no = build_features(ev_no_lineup)
    qual_no = evaluate_data_quality(ev_no_lineup, feat_no, manifest_no)

    # 2. Evidence with a 10-day-old stale lineup
    stale_lineup = LineupSnapshot(
        provider="mock",
        fixture_id=fix_info.fixture_id,
        team_id=fix_info.home_team_id,
        captured_at=as_of - timedelta(days=10),
        confirmed=True,
        formation="4-3-3",
        players_jsonb=[],
        publication_state="CONFIRMED",
    )
    ev_with_stale_lineup = SelectedEvidence(
        fixture_id=fix_info.fixture_id,
        forecast_phase=ForecastPhase.MORNING,
        as_of=as_of,
        fixture=fix_info,
        home_lineup=stale_lineup,
    )
    manifest_stale = build_source_manifest(ev_with_stale_lineup)
    feat_stale = build_features(ev_with_stale_lineup)
    qual_stale = evaluate_data_quality(ev_with_stale_lineup, feat_stale, manifest_stale)

    # In MORNING:
    # 1. Stale lineup must NOT enter stale_sources
    assert "home_lineup" not in qual_stale.stale_sources
    # 2. Lineup warning must NOT be added
    assert not any("lineup" in w.lower() for w in qual_stale.warnings)
    # 3. Overall quality score must be identical
    assert qual_stale.overall_score == qual_no.overall_score
    assert qual_stale.quality_band == qual_no.quality_band
