from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from sports_intelligence.context.builder import assemble_match_context_v1
from sports_intelligence.context.provenance import (
    build_feature_provenance,
    build_source_manifest,
)
from sports_intelligence.context.selector import SelectedEvidence, SelectedFixtureInfo
from sports_intelligence.core.phases import ForecastPhase
from sports_intelligence.db.models import (
    FixtureMetadataSnapshot,
    OddsSnapshotSet,
    ResearchClaim,
    ResearchDocument,
    TeamFormSnapshot,
)
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


def test_research_provenance_and_claims_identity() -> None:
    fix_info = _fixture_info()
    as_of = fix_info.kickoff_at - timedelta(hours=4)

    run_id = uuid.uuid4()
    doc_id = uuid.uuid4()
    claim_id = uuid.uuid4()

    doc = ResearchDocument(
        id=doc_id,
        fixture_id=fix_info.fixture_id,
        run_id=run_id,
        url="https://theathletic.com/arsenal-preview",
        domain="theathletic.com",
        title="Arsenal Pre-Match News",
        retrieved_at=as_of,
        content_hash="hash-1234",
        provider="tavily",
    )
    claim = ResearchClaim(
        id=claim_id,
        fixture_id=fix_info.fixture_id,
        document_id=doc_id,
        claim_type="injury",
        claim_text="Saka has a minor hamstring issue and is doubtful.",
        confidence=0.85,
        extracted_at=as_of,
    )
    res_view = FixtureResearchView(
        fixture_id=fix_info.fixture_id,
        status="AVAILABLE",
        run_id=run_id,
        provider="tavily",
        last_captured_at=as_of,
        documents_count=1,
        claims_count=1,
        conflicts_count=0,
        documents=[doc],
        claims=[claim],
    )
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
        research=res_view,
    )
    manifest = build_source_manifest(evidence)
    # Manifest must contain real ResearchRun.id
    res_prov = manifest.sources["research"]
    assert res_prov.snapshot_id == str(run_id)
    assert res_prov.provider == "tavily"
    assert res_prov.details["documents_count"] == 1
    assert str(doc_id) in res_prov.details["document_ids"]
    assert str(claim_id) in res_prov.details["claim_ids"]

    # MatchContext claims must retain document_id and source_reference
    ctx = assemble_match_context_v1(
        evidence,
        build_features(evidence),
        evaluate_data_quality(evidence, build_features(evidence), manifest),
        manifest,
    )
    assert ctx.research_claims["run_id"] == str(run_id)
    assert len(ctx.research_claims["claims"]) == 1
    c_out = ctx.research_claims["claims"][0]
    assert c_out["document_id"] == str(doc_id)
    assert c_out["source_reference"] == "theathletic.com: https://theathletic.com/arsenal-preview"
    assert c_out["confidence"] == 0.85


def test_previous_odds_in_provenance() -> None:
    fix_info = _fixture_info()
    as_of = fix_info.kickoff_at - timedelta(hours=1)

    cur_id = uuid.uuid4()
    prev_id = uuid.uuid4()
    cur_odds = OddsSnapshotSet(
        id=cur_id,
        fixture_id=fix_info.fixture_id,
        provider="theoddsapi",
        captured_at=as_of,
        market_whitelist_jsonb=["h2h_1x2"],
    )
    prev_odds = OddsSnapshotSet(
        id=prev_id,
        fixture_id=fix_info.fixture_id,
        provider="theoddsapi",
        captured_at=as_of - timedelta(hours=3),
        market_whitelist_jsonb=["h2h_1x2"],
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
        home_lineup=None,
        away_lineup=None,
        odds_set=cur_odds,
        prev_odds_set=prev_odds,
    )
    manifest = build_source_manifest(ev)
    assert "odds" in manifest.sources
    assert "prev_odds" in manifest.sources
    assert manifest.sources["odds"].snapshot_id == str(cur_id)
    assert manifest.sources["prev_odds"].snapshot_id == str(prev_id)


def test_feature_provenance_mapping() -> None:
    fix_info = _fixture_info()
    as_of = fix_info.kickoff_at - timedelta(hours=2)

    meta_id = uuid.uuid4()
    meta_snap = FixtureMetadataSnapshot(
        id=meta_id,
        fixture_id=fix_info.fixture_id,
        provider="api_football",
        captured_at=as_of - timedelta(days=1),
        kickoff_at=fix_info.kickoff_at,
        league_id=fix_info.league_id,
        home_team_id=fix_info.home_team_id,
        away_team_id=fix_info.away_team_id,
        status="NS",
    )
    h_form_id = uuid.uuid4()
    h_form = TeamFormSnapshot(
        id=h_form_id,
        team_id=fix_info.home_team_id,
        as_of=as_of - timedelta(hours=5),
        window_size=10,
        scope="overall",
        metrics_jsonb={"outcomes": []},
        source_fingerprint="fp-h-form",
    )
    odds_id = uuid.uuid4()
    prev_odds_id = uuid.uuid4()
    odds = OddsSnapshotSet(
        id=odds_id,
        fixture_id=fix_info.fixture_id,
        provider="theoddsapi",
        captured_at=as_of,
        market_whitelist_jsonb=["h2h_1x2"],
    )
    prev_odds = OddsSnapshotSet(
        id=prev_odds_id,
        fixture_id=fix_info.fixture_id,
        provider="theoddsapi",
        captured_at=as_of - timedelta(hours=2),
        market_whitelist_jsonb=["h2h_1x2"],
    )

    ev = SelectedEvidence(
        fixture_id=fix_info.fixture_id,
        forecast_phase=ForecastPhase.PREMATCH,
        as_of=as_of,
        fixture=fix_info,
        fixture_metadata=meta_snap,
        standings=None,
        home_team_stats=None,
        away_team_stats=None,
        home_form=h_form,
        away_form=None,
        home_availability=None,
        away_availability=None,
        home_lineup=None,
        away_lineup=None,
        odds_set=odds,
        prev_odds_set=prev_odds,
    )
    feat_prov = build_feature_provenance(ev)
    assert feat_prov["fixture_identity"]["snapshot_id"] == str(meta_id)
    assert feat_prov["form"]["home_snapshot_id"] == str(h_form_id)
    assert feat_prov["odds"]["current_snapshot_set_id"] == str(odds_id)
    assert feat_prov["odds"]["previous_snapshot_set_id"] == str(prev_odds_id)
