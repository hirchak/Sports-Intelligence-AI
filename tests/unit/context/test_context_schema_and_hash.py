from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from sports_intelligence.context.builder import assemble_match_context_v1
from sports_intelligence.context.provenance import build_source_manifest
from sports_intelligence.context.selector import SelectedEvidence, SelectedFixtureInfo
from sports_intelligence.core.phases import ForecastPhase
from sports_intelligence.features.builder import build_features
from sports_intelligence.quality.engine import evaluate_data_quality


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


def test_match_context_contains_all_13_ordered_sections() -> None:
    fix_info = _fixture_info()
    as_of = fix_info.kickoff_at - timedelta(hours=6)

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
    quality = evaluate_data_quality(evidence, features, manifest)
    context = assemble_match_context_v1(evidence, features, quality, manifest)

    ctx_dict = context.to_dict()

    # Ordered sections 1–13
    expected_sections = [
        "fixture_identity",
        "team_form",
        "home_away_context",
        "season_strength",
        "schedule_fatigue",
        "availability",
        "lineups",
        "head_to_head",
        "research_claims",
        "market_snapshot",
        "deterministic_features",
        "data_quality",
        "source_manifest",
    ]
    for sec in expected_sections:
        assert sec in ctx_dict

    # Prohibitions: No prediction probabilities, no edge, no betting candidate, no score/result
    assert "prediction" not in ctx_dict
    assert "model_probabilities" not in ctx_dict
    assert "edge" not in ctx_dict
    assert "recommendation" not in ctx_dict
    assert "final_score" not in ctx_dict


def test_canonical_json_and_sha256_hash_stability() -> None:
    fix_info = _fixture_info()
    as_of = fix_info.kickoff_at - timedelta(hours=6)

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
    quality = evaluate_data_quality(evidence, features, manifest)
    ctx1 = assemble_match_context_v1(evidence, features, quality, manifest)
    ctx2 = assemble_match_context_v1(evidence, features, quality, manifest)

    hash1 = hashlib.sha256(ctx1.canonical_json().encode("utf-8")).hexdigest()
    hash2 = hashlib.sha256(ctx2.canonical_json().encode("utf-8")).hexdigest()

    assert hash1 == hash2
    assert len(hash1) == 64

    # Modifying phase or as_of changes the hash
    evidence_mod = SelectedEvidence(
        fixture_id=fix_info.fixture_id,
        forecast_phase=ForecastPhase.PREMATCH,  # changed phase
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
    manifest_mod = build_source_manifest(evidence_mod)
    features_mod = build_features(evidence_mod)
    quality_mod = evaluate_data_quality(evidence_mod, features_mod, manifest_mod)
    ctx_mod = assemble_match_context_v1(evidence_mod, features_mod, quality_mod, manifest_mod)
    hash_mod = hashlib.sha256(ctx_mod.canonical_json().encode("utf-8")).hexdigest()

    assert hash_mod != hash1
