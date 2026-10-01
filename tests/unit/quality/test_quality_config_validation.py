from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from sports_intelligence.collectors.freshness import FreshnessPolicy
from sports_intelligence.context.builder import (
    assemble_match_context_v1,
    compute_build_config_fingerprint,
)
from sports_intelligence.context.models import (
    DataQualitySection,
    DeterministicFeaturesSection,
    FixtureIdentitySection,
    MatchContextV1,
    SourceManifestSection,
)
from sports_intelligence.context.provenance import build_source_manifest
from sports_intelligence.context.selector import (
    ProviderMappingRecord,
    SelectedEvidence,
    SelectedFixtureInfo,
)
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
        home_provider_mappings=[],
        away_provider_mappings=[],
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
    from sports_intelligence.collectors.freshness import FreshnessPolicy
    from sports_intelligence.context.builder import ContextBuildPolicy
    from sports_intelligence.core.config import Settings
    from sports_intelligence.quality.engine import QualityPolicy, QualityWeights

    s = Settings(app_env="mock")
    qp1 = QualityPolicy(weights=QualityWeights(form=0.1), min_predict_score=0.65)
    fp_base = FreshnessPolicy(settings=s)

    b1 = ContextBuildPolicy(quality_policy=qp1, freshness_policy=fp_base, research_enabled=True)
    fp1 = compute_build_config_fingerprint(b1)

    b2 = ContextBuildPolicy(quality_policy=qp1, freshness_policy=fp_base, research_enabled=True)
    fp2 = compute_build_config_fingerprint(b2)
    assert fp1 == fp2

    # Vary quality policy
    qp3 = QualityPolicy(weights=QualityWeights(form=0.5), min_predict_score=0.65)
    b3 = ContextBuildPolicy(quality_policy=qp3, freshness_policy=fp_base, research_enabled=True)
    fp3 = compute_build_config_fingerprint(b3)
    assert fp1 != fp3

    # Vary research enabled
    b4 = ContextBuildPolicy(quality_policy=qp1, freshness_policy=fp_base, research_enabled=False)
    fp4 = compute_build_config_fingerprint(b4)
    assert fp1 != fp4

    # Vary freshness policy
    s2 = Settings(app_env="mock", freshness_standings_seconds=12345)
    fp_mod = FreshnessPolicy(settings=s2)
    b5 = ContextBuildPolicy(quality_policy=qp1, freshness_policy=fp_mod, research_enabled=True)
    fp5 = compute_build_config_fingerprint(b5)
    assert fp1 != fp5


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


def test_malformed_deterministic_features_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DeterministicFeaturesSection(invalid_feature="bad")  # type: ignore[call-arg]


def test_malformed_data_quality_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        DataQualitySection(
            schema_version="quality_v1",
            forecast_phase="MORNING",
            as_of="2026-08-22T10:00:00Z",
            overall_score=0.85,
            quality_band="usable",
            can_predict=True,
            dimension_scores={},
            critical_missing=[],
            missing_fields=[],
            warnings=[],
            conflicts=[],
            provider_errors=[],
            stale_sources=[],
            source_manifest=SourceManifestSection(source_fingerprint="fp", sources={}),
            extra_quality_field="bad",  # type: ignore[call-arg]
        )


def test_malformed_source_manifest_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SourceManifestSection(
            source_fingerprint="fp",
            sources={},
            unexpected_manifest_field="bad",  # type: ignore[call-arg]
        )


def test_freshness_policy_fingerprint_variance() -> None:
    s1 = Settings(app_env="mock", freshness_odds_seconds=300)
    s2 = Settings(app_env="mock", freshness_odds_seconds=600)
    fp1 = FreshnessPolicy(settings=s1).policy_fingerprint()
    fp2 = FreshnessPolicy(settings=s2).policy_fingerprint()
    assert fp1 != fp2
    assert len(fp1) == 64


def test_canonical_provenance_fingerprint_order_independence() -> None:
    fix_info = _base_fixture_info()
    as_of = fix_info.kickoff_at - timedelta(hours=6)
    ev = SelectedEvidence(
        fixture_id=fix_info.fixture_id,
        forecast_phase=ForecastPhase.MORNING,
        as_of=as_of,
        fixture=fix_info,
    )
    manifest = build_source_manifest(ev)
    fp1 = manifest.source_fingerprint
    manifest2 = build_source_manifest(ev)
    assert fp1 == manifest2.source_fingerprint


def test_provider_mappings_affect_source_fingerprint() -> None:
    fix_info_no_map = _base_fixture_info()
    as_of = fix_info_no_map.kickoff_at - timedelta(hours=6)
    ev_no_map = SelectedEvidence(
        fixture_id=fix_info_no_map.fixture_id,
        forecast_phase=ForecastPhase.MORNING,
        as_of=as_of,
        fixture=fix_info_no_map,
    )
    manifest_no_map = build_source_manifest(ev_no_map)

    fix_info_with_map = SelectedFixtureInfo(
        fixture_id=fix_info_no_map.fixture_id,
        league_id=fix_info_no_map.league_id,
        season_id=fix_info_no_map.season_id,
        home_team_id=fix_info_no_map.home_team_id,
        away_team_id=fix_info_no_map.away_team_id,
        kickoff_at=fix_info_no_map.kickoff_at,
        venue=fix_info_no_map.venue,
        round=fix_info_no_map.round,
        status=fix_info_no_map.status,
        league_slug=fix_info_no_map.league_slug,
        league_name=fix_info_no_map.league_name,
        home_team_name=fix_info_no_map.home_team_name,
        away_team_name=fix_info_no_map.away_team_name,
        home_provider_mappings=[
            ProviderMappingRecord(
                provider="api_football",
                external_id="123",
                mapping_id=uuid.uuid4(),
                first_seen_at=as_of - timedelta(days=1),
            )
        ],
        away_provider_mappings=[],
    )
    ev_with_map = SelectedEvidence(
        fixture_id=fix_info_with_map.fixture_id,
        forecast_phase=ForecastPhase.MORNING,
        as_of=as_of,
        fixture=fix_info_with_map,
    )
    manifest_with_map = build_source_manifest(ev_with_map)
    assert manifest_no_map.source_fingerprint != manifest_with_map.source_fingerprint


def test_research_selected_claim_set_affects_source_fingerprint() -> None:
    fix_info = _base_fixture_info()
    as_of = fix_info.kickoff_at - timedelta(hours=6)
    from sports_intelligence.research.service import (
        FixtureResearchView,
        ResearchClaimView,
        ResearchDocumentView,
    )

    doc = ResearchDocumentView(
        id=uuid.uuid4(),
        url="https://example.com/1",
        title="Title",
        snippet="Snippet",
        domain="example.com",
        retrieved_at=as_of - timedelta(hours=1),
        published_at=as_of - timedelta(hours=2),
        content_hash="hash-1",
        relevance_score=0.9,
        provider="mock",
        metadata={},
    )
    claim1 = ResearchClaimView(
        id=uuid.uuid4(),
        document_id=doc.id,
        claim_type="fitness",
        claim_text="Player X is fit",
        extracted_at=as_of - timedelta(hours=1),
        confidence=0.9,
        team_id=None,
        conflict_flag=False,
        conflicting_claim_id=None,
        extraction_version="v1",
        metadata={},
        created_at=as_of - timedelta(hours=1),
    )
    claim2 = ResearchClaimView(
        id=uuid.uuid4(),
        document_id=doc.id,
        claim_type="injury",
        claim_text="Player Y is injured",
        extracted_at=as_of - timedelta(hours=1),
        confidence=0.95,
        team_id=None,
        conflict_flag=False,
        conflicting_claim_id=None,
        extraction_version="v1",
        metadata={},
        created_at=as_of - timedelta(hours=1),
    )
    rv1 = FixtureResearchView(
        fixture_id=fix_info.fixture_id,
        status="AVAILABLE",
        last_captured_at=as_of - timedelta(hours=1),
        documents_count=1,
        claims_count=1,
        conflicts_count=0,
        run_id=uuid.uuid4(),
        provider="mock",
        documents=[doc],
        claims=[claim1],
    )
    rv2 = FixtureResearchView(
        fixture_id=fix_info.fixture_id,
        status="AVAILABLE",
        last_captured_at=as_of - timedelta(hours=1),
        documents_count=1,
        claims_count=2,
        conflicts_count=0,
        run_id=rv1.run_id,
        provider="mock",
        documents=[doc],
        claims=[claim1, claim2],
    )

    ev1 = SelectedEvidence(
        fixture_id=fix_info.fixture_id,
        forecast_phase=ForecastPhase.MORNING,
        as_of=as_of,
        fixture=fix_info,
        research=rv1,
    )
    ev2 = SelectedEvidence(
        fixture_id=fix_info.fixture_id,
        forecast_phase=ForecastPhase.MORNING,
        as_of=as_of,
        fixture=fix_info,
        research=rv2,
    )
    m1 = build_source_manifest(ev1)
    m2 = build_source_manifest(ev2)
    assert m1.source_fingerprint != m2.source_fingerprint


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
