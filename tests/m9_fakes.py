"""Explicitly synthetic frozen M9 records; never forecasting evidence."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta

from m7_fakes import make_context
from sports_intelligence.context.models import MatchContextV1
from sports_intelligence.db.models import (
    DataQualityReport,
    FeatureSnapshot,
    Fixture,
    FixtureMetadataSnapshot,
    League,
    MatchContextRecord,
    OddsSnapshotSet,
    Team,
)
from sports_intelligence.experiments.contracts import ExperimentDefinition, Population


async def frozen_record(factory, *, phase="MORNING", has_odds=True):
    context = make_context()
    data = context.model_dump()
    as_of = datetime.fromisoformat(context.as_of)
    kickoff = as_of + timedelta(hours=6)
    async with factory() as session:
        league = League(
            slug="m9-" + uuid.uuid4().hex[:10], name="Synthetic frozen league", enabled=True
        )
        home, away = Team(name="Synthetic Home"), Team(name="Synthetic Away")
        session.add_all([league, home, away])
        await session.flush()
        fixture = Fixture(
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=kickoff,
            status="NS",
        )
        session.add(fixture)
        await session.flush()
        metadata = FixtureMetadataSnapshot(
            fixture_id=fixture.id,
            provider="mock",
            captured_at=as_of,
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            observed_home_team_name=home.name,
            observed_away_team_name=away.name,
            observed_league_name=league.name,
            observed_league_slug=league.slug,
            kickoff_at=kickoff,
            status="NS",
        )
        odds = OddsSnapshotSet(
            fixture_id=fixture.id, provider="mock", captured_at=as_of, market_whitelist_jsonb=[]
        )
        session.add_all([metadata, odds])
        await session.flush()
        data["fixture_id"] = data["fixture_identity"]["fixture_id"] = str(fixture.id)
        data["forecast_phase"] = data["data_quality"]["forecast_phase"] = phase
        data["fixture_identity"].update(
            league_id=str(league.id),
            league_slug=league.slug,
            league_name=league.name,
            home_team_id=str(home.id),
            away_team_id=str(away.id),
            fixture_metadata_snapshot_id=str(metadata.id),
            metadata_captured_at=as_of.isoformat(),
        )
        data["source_manifest"]["sources"] = {
            "fixture_metadata": {
                "category": "fixture_metadata",
                "table": "fixture_metadata_snapshots",
                "snapshot_id": str(metadata.id),
                "provider": "mock",
                "captured_at": as_of.isoformat(),
            }
        }
        if has_odds:
            data["source_manifest"]["sources"]["odds"] = {
                "category": "odds",
                "table": "odds_snapshot_sets",
                "snapshot_id": str(odds.id),
                "provider": "mock",
                "captured_at": as_of.isoformat(),
            }
        else:
            data["market_snapshot"].update(has_odds=False, prices=[], captured_at=None)
        data["data_quality"]["source_manifest"] = data["source_manifest"]
        context = MatchContextV1.model_validate(data)
        feature = FeatureSnapshot(
            fixture_id=fixture.id,
            forecast_phase=phase,
            as_of=as_of,
            schema_version=context.deterministic_features.schema_version,
            features_jsonb=context.deterministic_features.model_dump(),
            source_fingerprint="synthetic",
            source_manifest_jsonb=data["source_manifest"],
        )
        q = context.data_quality
        quality = DataQualityReport(
            fixture_id=fixture.id,
            forecast_phase=phase,
            as_of=as_of,
            schema_version=q.schema_version,
            overall_score=q.overall_score,
            quality_band=q.quality_band,
            can_predict=q.can_predict,
            dimensions_jsonb=q.dimension_scores,
            source_manifest_jsonb=data["source_manifest"],
            source_fingerprint="synthetic",
        )
        session.add_all([feature, quality])
        await session.flush()
        rec = MatchContextRecord(
            fixture_id=fixture.id,
            forecast_phase=phase,
            as_of=as_of,
            schema_version="match_context_v1",
            context_jsonb=data,
            context_hash=hashlib.sha256(context.canonical_json().encode()).hexdigest(),
            feature_snapshot_id=feature.id,
            data_quality_report_id=quality.id,
        )
        session.add(rec)
        await session.commit()
        return rec


def definition(record, **overrides):
    return ExperimentDefinition(
        name="Synthetic M9 experiment",
        hypothesis="Test plumbing only.",
        population=Population(
            start=record.as_of - timedelta(days=1),
            end=record.as_of + timedelta(days=1),
            fixture_ids=(record.fixture_id,),
        ),
        **overrides,
    )
