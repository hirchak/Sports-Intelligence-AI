from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sports_intelligence.collectors.freshness import FreshnessPolicy
from sports_intelligence.context.models import MatchContextV1
from sports_intelligence.context.provenance import (
    SourceManifest,
    build_feature_provenance,
    build_source_manifest,
)
from sports_intelligence.context.selector import SelectedEvidence, select_evidence
from sports_intelligence.core.phases import ForecastPhase
from sports_intelligence.db.models import (
    DataQualityReport,
    FeatureSnapshot,
    MatchContextRecord,
)
from sports_intelligence.features.builder import DeterministicFeatures, build_features
from sports_intelligence.quality.engine import (
    QualityPolicy,
    QualityReportData,
    evaluate_data_quality,
)


@dataclass(frozen=True)
class ContextBuildPolicy:
    quality_policy: QualityPolicy
    freshness_policy: FreshnessPolicy
    research_enabled: bool
    context_schema_version: str = "match_context_v1"
    feature_schema_version: str = "features_v1"
    quality_schema_version: str = "quality_v1"


def compute_build_config_fingerprint(policy: ContextBuildPolicy) -> str:
    """Compute a deterministic SHA-256 fingerprint of all configuration affecting context build."""
    payload = {
        "context_schema_version": policy.context_schema_version,
        "feature_schema_version": policy.feature_schema_version,
        "quality_schema_version": policy.quality_schema_version,
        "policy_fingerprint": policy.quality_policy.policy_fingerprint(),
        "freshness_policy_fingerprint": policy.freshness_policy.policy_fingerprint(),
        "research_enabled": policy.research_enabled,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def assemble_match_context_v1(
    evidence: SelectedEvidence,
    features: DeterministicFeatures,
    quality: QualityReportData,
    manifest: SourceManifest,
) -> MatchContextV1:
    """Assemble the 13 canonical sections of MatchContext V1."""
    as_of_str = (
        evidence.as_of.astimezone(UTC).isoformat()
        if evidence.as_of.tzinfo
        else evidence.as_of.replace(tzinfo=UTC).isoformat()
    )

    # 1. Fixture Identity
    fix = evidence.fixture
    fixture_identity = {
        "fixture_id": str(fix.fixture_id),
        "league_id": str(fix.league_id),
        "season_id": str(fix.season_id) if fix.season_id else None,
        "home_team_id": str(fix.home_team_id),
        "away_team_id": str(fix.away_team_id),
        "kickoff_at": fix.kickoff_at.isoformat(),
        "venue": fix.venue,
        "round": fix.round,
        "status": fix.status,
        "league_slug": fix.league_slug,
        "league_name": fix.league_name,
        "home_team_name": fix.home_team_name,
        "away_team_name": fix.away_team_name,
        "home_provider_mappings": [
            {
                "provider": m.provider,
                "external_id": m.external_id,
                "mapping_id": str(m.mapping_id),
                "first_seen_at": m.first_seen_at.isoformat(),
            }
            for m in fix.home_provider_mappings
        ],
        "away_provider_mappings": [
            {
                "provider": m.provider,
                "external_id": m.external_id,
                "mapping_id": str(m.mapping_id),
                "first_seen_at": m.first_seen_at.isoformat(),
            }
            for m in fix.away_provider_mappings
        ],
        "fixture_metadata_snapshot_id": (
            str(fix.fixture_metadata_snapshot_id) if fix.fixture_metadata_snapshot_id else None
        ),
        "metadata_captured_at": (
            fix.metadata_captured_at.isoformat() if fix.metadata_captured_at else None
        ),
    }

    # 2. Team Form
    home_outcomes = (
        evidence.home_form.metrics_jsonb.get("outcomes", [])
        if evidence.home_form and isinstance(evidence.home_form.metrics_jsonb, dict)
        else []
    )
    away_outcomes = (
        evidence.away_form.metrics_jsonb.get("outcomes", [])
        if evidence.away_form and isinstance(evidence.away_form.metrics_jsonb, dict)
        else []
    )
    team_form = {
        "home_sample_size": features.home_sample_size,
        "away_sample_size": features.away_sample_size,
        "home_outcomes": home_outcomes,
        "away_outcomes": away_outcomes,
    }

    # 3. Home / Away Context
    home_away_context = {
        "home_split_ppg": features.home_home_split_ppg,
        "away_split_ppg": features.away_away_split_ppg,
    }

    # 4. Season Strength
    season_strength = {
        "home_league_position": features.home_league_position,
        "away_league_position": features.away_league_position,
        "league_position_delta": features.league_position_delta,
        "home_season_points_per_game": features.home_season_points_per_game,
        "away_season_points_per_game": features.away_season_points_per_game,
        "home_season_goals_for_per_game": features.home_season_goals_for_per_game,
        "away_season_goals_for_per_game": features.away_season_goals_for_per_game,
        "home_season_goals_against_per_game": features.home_season_goals_against_per_game,
        "away_season_goals_against_per_game": features.away_season_goals_against_per_game,
    }

    # 5. Schedule / Fatigue
    schedule_fatigue = {
        "home_days_since_last_match": features.home_days_since_last_match,
        "away_days_since_last_match": features.away_days_since_last_match,
        "rest_days_delta": features.rest_days_delta,
        "home_matches_last_7d": features.home_matches_last_7d,
        "away_matches_last_7d": features.away_matches_last_7d,
        "home_matches_last_14d": features.home_matches_last_14d,
        "away_matches_last_14d": features.away_matches_last_14d,
        "fixture_congestion_delta": features.fixture_congestion_delta,
    }

    # 6. Availability
    availability = {
        "home_state": features.home_availability_state,
        "away_state": features.away_availability_state,
        "home_missing_count": features.home_missing_players_count,
        "away_missing_count": features.away_missing_players_count,
        "home_players": (
            evidence.home_availability.players_jsonb if evidence.home_availability else []
        ),
        "away_players": (
            evidence.away_availability.players_jsonb if evidence.away_availability else []
        ),
        "home_conflicts": features.home_availability_conflict_count,
        "away_conflicts": features.away_availability_conflict_count,
    }

    # 7. Lineups
    lineups = {
        "home_confirmed": features.home_lineup_confirmed,
        "away_confirmed": features.away_lineup_confirmed,
        "lineups_both_confirmed": features.lineups_both_confirmed,
        "home_formation": features.home_lineup_formation,
        "away_formation": features.away_lineup_formation,
        "home_publication_state": features.home_lineup_publication_state,
        "away_publication_state": features.away_lineup_publication_state,
        "home_players": (evidence.home_lineup.players_jsonb if evidence.home_lineup else []),
        "away_players": (evidence.away_lineup.players_jsonb if evidence.away_lineup else []),
    }

    # 8. Head-to-Head (secondary context not normalized in V1)
    head_to_head = {
        "available": False,
        "reason": "No normalized head-to-head snapshot in V1; secondary context deferred",
        "matches": [],
    }

    # 9. Structured Research Claims
    claims_list: list[dict[str, Any]] = []
    if evidence.research:
        doc_map = {d.id: d for d in evidence.research.documents}
        for c in evidence.research.claims:
            doc = doc_map.get(c.document_id)
            src_ref = f"{doc.domain}: {doc.url}" if doc else None
            source_obj = (
                {
                    "document_id": str(doc.id),
                    "url": doc.url,
                    "domain": doc.domain,
                    "title": doc.title,
                    "published_at": doc.published_at.isoformat() if doc.published_at else None,
                    "retrieved_at": doc.retrieved_at.isoformat() if doc.retrieved_at else None,
                    "content_hash": doc.content_hash,
                    "provider": doc.provider,
                }
                if doc
                else None
            )
            claims_list.append(
                {
                    "id": str(c.id),
                    "document_id": str(c.document_id) if c.document_id else None,
                    "claim_type": c.claim_type,
                    "claim_text": c.claim_text,
                    "confidence": c.confidence,
                    "team_id": str(c.team_id) if c.team_id else None,
                    "conflict_flag": (
                        bool(c.conflict_flag) if c.conflict_flag is not None else False
                    ),
                    "conflicting_claim_id": (
                        str(c.conflicting_claim_id) if c.conflicting_claim_id else None
                    ),
                    "extracted_at": c.extracted_at.isoformat(),
                    "source_reference": src_ref,
                    "source": source_obj,
                }
            )
    research_claims = {
        "status": evidence.research.status if evidence.research else "NO_RUN",
        "run_id": (
            str(evidence.research.run_id)
            if (evidence.research and evidence.research.run_id)
            else None
        ),
        "provider": evidence.research.provider if evidence.research else None,
        "documents_count": evidence.research.documents_count if evidence.research else 0,
        "claims_count": evidence.research.claims_count if evidence.research else 0,
        "conflicts_count": evidence.research.conflicts_count if evidence.research else 0,
        "claims": claims_list,
    }

    # 10. Market Snapshot
    sorted_prices = sorted(
        evidence.odds_prices,
        key=lambda p: (
            p.market,
            p.selection,
            p.bookmaker or "",
            float(p.line) if p.line is not None else 0.0,
            float(p.decimal_odds),
            str(p.id),
        ),
    )
    prices_list: list[dict[str, Any]] = []
    for p in sorted_prices:
        prices_list.append(
            {
                "market": p.market,
                "selection": p.selection,
                "decimal_odds": float(p.decimal_odds),
                "implied_probability": float(p.implied_probability),
                "no_vig_probability": (
                    float(p.no_vig_probability) if p.no_vig_probability is not None else None
                ),
                "bookmaker": p.bookmaker,
                "line": float(p.line) if p.line is not None else None,
            }
        )
    bookmakers_list = sorted(list({p.bookmaker for p in sorted_prices if p.bookmaker}))
    market_snapshot = {
        "has_odds": evidence.odds_set is not None,
        "bookmakers": bookmakers_list,
        "captured_at": (evidence.odds_set.captured_at.isoformat() if evidence.odds_set else None),
        "prices": prices_list,
        "movement": {
            "odds_move_home": features.odds_move_home,
            "odds_move_over25": features.odds_move_over25,
        },
    }

    # 11. Deterministic Features
    deterministic_features = features.to_dict()

    # 12. Data Quality
    data_quality = quality.to_dict()

    # 13. Source Manifest
    source_manifest = manifest.to_dict()

    return MatchContextV1(
        schema_version="match_context_v1",
        fixture_id=str(evidence.fixture_id),
        forecast_phase=evidence.forecast_phase.value,
        as_of=as_of_str,
        fixture_identity=fixture_identity,
        team_form=team_form,
        home_away_context=home_away_context,
        season_strength=season_strength,
        schedule_fatigue=schedule_fatigue,
        availability=availability,
        lineups=lineups,
        head_to_head=head_to_head,
        research_claims=research_claims,
        market_snapshot=market_snapshot,
        deterministic_features=deterministic_features,
        data_quality=data_quality,
        source_manifest=source_manifest,
    )


async def build_and_persist_match_context(
    session: AsyncSession,
    *,
    fixture_id: uuid.UUID,
    forecast_phase: ForecastPhase,
    as_of: datetime,
    build_policy: ContextBuildPolicy,
) -> tuple[MatchContextRecord, DataQualityReport, FeatureSnapshot, MatchContextV1]:
    """Pure deterministic builder workflow:

    1. select point-in-time evidence strictly <= as_of
    2. build source manifest
    3. build deterministic features
    4. evaluate data quality
    5. assemble MatchContextV1
    6. compute SHA-256 canonical hash
    7. persist DataQualityReport, FeatureSnapshot, and MatchContextRecord idempotently
    """
    as_of_utc = as_of.astimezone(UTC) if as_of.tzinfo else as_of.replace(tzinfo=UTC)

    # Step 1: Select evidence
    evidence = await select_evidence(
        session,
        fixture_id=fixture_id,
        forecast_phase=forecast_phase,
        as_of=as_of_utc,
        research_enabled=build_policy.research_enabled,
    )

    # Step 2: Build source manifest
    manifest = build_source_manifest(evidence)

    # Step 3: Build features
    features = build_features(evidence)

    # Step 4: Evaluate quality
    quality = evaluate_data_quality(
        evidence,
        features,
        manifest,
        policy=build_policy.quality_policy,
        freshness_policy=build_policy.freshness_policy,
    )

    # Step 5: Assemble MatchContext
    context = assemble_match_context_v1(evidence, features, quality, manifest)

    # Step 6: Compute canonical hash
    canonical = context.canonical_json()
    context_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # Step 7: Check idempotency in match_contexts
    existing_stmt = select(MatchContextRecord).where(
        MatchContextRecord.fixture_id == fixture_id,
        MatchContextRecord.forecast_phase == forecast_phase.value,
        MatchContextRecord.as_of == as_of_utc,
        MatchContextRecord.schema_version == context.schema_version,
        MatchContextRecord.context_hash == context_hash,
    )
    existing_record = (await session.execute(existing_stmt)).scalar_one_or_none()
    if existing_record is not None:
        # Load related records
        existing_quality = (
            await session.get(DataQualityReport, existing_record.data_quality_report_id)
            if existing_record.data_quality_report_id
            else None
        )
        existing_features = (
            await session.get(FeatureSnapshot, existing_record.feature_snapshot_id)
            if existing_record.feature_snapshot_id
            else None
        )
        if existing_quality is not None and existing_features is not None:
            return existing_record, existing_quality, existing_features, context

    # Persist DataQualityReport idempotently
    quality_stmt = select(DataQualityReport).where(
        DataQualityReport.fixture_id == fixture_id,
        DataQualityReport.forecast_phase == forecast_phase.value,
        DataQualityReport.as_of == as_of_utc,
        DataQualityReport.schema_version == quality.schema_version,
        DataQualityReport.source_fingerprint == manifest.source_fingerprint,
        DataQualityReport.policy_fingerprint == quality.policy_fingerprint,
        DataQualityReport.freshness_policy_fingerprint == quality.freshness_policy_fingerprint,
    )
    quality_record = (await session.execute(quality_stmt)).scalar_one_or_none()
    if quality_record is None:
        quality_record = DataQualityReport(
            fixture_id=fixture_id,
            forecast_phase=forecast_phase.value,
            as_of=as_of_utc,
            schema_version=quality.schema_version,
            overall_score=quality.overall_score,
            quality_band=quality.quality_band,
            can_predict=quality.can_predict,
            dimensions_jsonb=quality.dimension_scores,
            critical_missing_jsonb=quality.critical_missing,
            missing_fields_jsonb=quality.missing_fields,
            warnings_jsonb=quality.warnings,
            conflicts_jsonb=quality.conflicts,
            provider_errors_jsonb=quality.provider_errors,
            stale_sources_jsonb=quality.stale_sources,
            source_manifest_jsonb=quality.source_manifest,
            source_fingerprint=manifest.source_fingerprint,
            quality_policy_jsonb=quality.quality_policy,
            policy_fingerprint=quality.policy_fingerprint,
            freshness_policy_jsonb=quality.freshness_policy,
            freshness_policy_fingerprint=quality.freshness_policy_fingerprint,
        )
        try:
            async with session.begin_nested():
                session.add(quality_record)
                await session.flush()
        except IntegrityError:
            quality_record = (await session.execute(quality_stmt)).scalar_one()

    # Persist FeatureSnapshot idempotently
    feat_stmt = select(FeatureSnapshot).where(
        FeatureSnapshot.fixture_id == fixture_id,
        FeatureSnapshot.forecast_phase == forecast_phase.value,
        FeatureSnapshot.as_of == as_of_utc,
        FeatureSnapshot.schema_version == features.schema_version,
        FeatureSnapshot.source_fingerprint == manifest.source_fingerprint,
    )
    feature_record = (await session.execute(feat_stmt)).scalar_one_or_none()
    if feature_record is None:
        feature_record = FeatureSnapshot(
            fixture_id=fixture_id,
            forecast_phase=forecast_phase.value,
            as_of=as_of_utc,
            schema_version=features.schema_version,
            features_jsonb=features.to_dict(),
            source_fingerprint=manifest.source_fingerprint,
            source_manifest_jsonb=manifest.to_dict(),
            feature_provenance_jsonb=build_feature_provenance(evidence),
        )
        try:
            async with session.begin_nested():
                session.add(feature_record)
                await session.flush()
        except IntegrityError:
            feature_record = (await session.execute(feat_stmt)).scalar_one()

    # Persist MatchContextRecord idempotently
    context_record = MatchContextRecord(
        fixture_id=fixture_id,
        forecast_phase=forecast_phase.value,
        as_of=as_of_utc,
        schema_version=context.schema_version,
        context_jsonb=context.to_dict(),
        context_hash=context_hash,
        data_quality_report_id=quality_record.id,
        feature_snapshot_id=feature_record.id,
    )
    try:
        async with session.begin_nested():
            session.add(context_record)
            await session.flush()
    except IntegrityError:
        context_record = (await session.execute(existing_stmt)).scalar_one()

    await session.commit()
    await session.refresh(context_record)
    await session.refresh(quality_record)
    await session.refresh(feature_record)

    return context_record, quality_record, feature_record, context
