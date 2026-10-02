from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sports_intelligence.context.models import MatchContextV1
from sports_intelligence.db.models import (
    Base,
    DataQualityReport,
    FeatureSnapshot,
    Fixture,
    FixtureResult,
    MatchContextRecord,
    PredictionRun,
)
from sports_intelligence.evaluation.results import digest, latest_results_query
from sports_intelligence.experiments.contracts import ExperimentDefinition
from sports_intelligence.predictions.service import read_prediction, verify_context

SNAPSHOT_TABLES = {
    "fixture_metadata_snapshots",
    "standings_snapshots",
    "team_statistics_snapshots",
    "team_form_snapshots",
    "availability_snapshots",
    "lineup_snapshots",
    "odds_snapshot_sets",
    "research_runs",
    "research_documents",
    "research_claims",
}


def check_times(context: MatchContextV1) -> None:
    boundary = datetime.fromisoformat(context.as_of)
    if boundary.tzinfo is None or boundary >= datetime.fromisoformat(
        context.fixture_identity.kickoff_at
    ):
        raise ValueError("not_prematch_context")
    times = [context.fixture_identity.metadata_captured_at, context.market_snapshot.captured_at]
    times += [s.captured_at for s in context.source_manifest.sources.values()]
    for claim in context.research_claims.claims:
        times.append(claim.extracted_at)
        if claim.source:
            times += [claim.source.retrieved_at, claim.source.published_at]
    for value in times:
        if value:
            observed = datetime.fromisoformat(value)
            if observed.tzinfo is None or observed > boundary:
                raise ValueError("future_evidence_forbidden")


async def verify_frozen(session: AsyncSession, record: MatchContextRecord) -> MatchContextV1:
    context = verify_context(record)
    check_times(context)
    if not record.feature_snapshot_id or not record.data_quality_report_id:
        raise ValueError("missing_feature_or_quality_evidence")
    feature = await session.get(FeatureSnapshot, record.feature_snapshot_id)
    quality = await session.get(DataQualityReport, record.data_quality_report_id)
    if feature is None or quality is None:
        raise ValueError("missing_feature_or_quality_evidence")
    if (
        feature.fixture_id != record.fixture_id
        or quality.fixture_id != record.fixture_id
        or feature.as_of != record.as_of
        or quality.as_of != record.as_of
        or feature.forecast_phase != record.forecast_phase
        or quality.forecast_phase != record.forecast_phase
        or feature.schema_version != context.deterministic_features.schema_version
        or feature.features_jsonb != context.deterministic_features.model_dump()
        or quality.overall_score != context.data_quality.overall_score
        or quality.can_predict != context.data_quality.can_predict
    ):
        raise ValueError("frozen_feature_quality_mismatch")
    if context.market_snapshot.has_odds:
        odds = context.source_manifest.sources.get("odds")
        if odds is None or not odds.snapshot_id:
            raise ValueError("missing_odds_evidence_identity")
    for source in context.source_manifest.sources.values():
        if not source.snapshot_id:
            continue  # Explicit missingness is retained in the frozen quality report.
        if source.table not in SNAPSHOT_TABLES:
            raise ValueError("non_historical_evidence_reference")
        table = Base.metadata.tables[source.table]
        row = (
            (await session.execute(select(table).where(table.c.id == UUID(source.snapshot_id))))
            .mappings()
            .first()
        )
        if row is None:
            raise ValueError("missing_referenced_evidence")
        if row.get("fixture_id") is not None and row["fixture_id"] != record.fixture_id:
            raise ValueError("evidence_fixture_identity_mismatch")
        for field in ("retrieved_at", "published_at", "extracted_at"):
            if row.get(field) and row[field] > record.as_of:
                raise ValueError("future_evidence_forbidden")
        captured = row.get("captured_at") or row.get("as_of") or row.get("retrieved_at")
        if captured and captured > record.as_of:
            raise ValueError("future_evidence_forbidden")
        if (
            source.captured_at
            and captured
            and datetime.fromisoformat(source.captured_at) != captured
        ):
            raise ValueError("source_time_identity_mismatch")
    return context


def lineage(record: MatchContextRecord, context: MatchContextV1) -> dict[str, Any]:
    return {
        "context_id": str(record.id),
        "context_hash": record.context_hash,
        "as_of": record.as_of.isoformat(),
        "phase": record.forecast_phase,
        "feature_id": str(record.feature_snapshot_id),
        "feature_version": context.deterministic_features.schema_version,
        "quality_id": str(record.data_quality_report_id),
        "source_manifest": context.source_manifest.model_dump(mode="json"),
    }


async def plan_replay(
    session: AsyncSession,
    definition: ExperimentDefinition,
    *,
    cutoff: datetime | None = None,
) -> dict[str, Any]:
    cutoff = cutoff or datetime.now(UTC)
    pop = definition.population
    query = select(MatchContextRecord).where(
        MatchContextRecord.as_of >= pop.start,
        MatchContextRecord.as_of < pop.end,
        MatchContextRecord.created_at <= cutoff,
        MatchContextRecord.forecast_phase.in_(
            {definition.control.phase, definition.treatment.phase}
        ),
    )
    if pop.context_ids:
        query = query.where(MatchContextRecord.id.in_(pop.context_ids))
    if pop.fixture_ids:
        query = query.where(MatchContextRecord.fixture_id.in_(pop.fixture_ids))
    # Cap database reads, and report the cap. No hidden provider backfill or mutable joins.
    records = list(
        (
            await session.scalars(
                query.order_by(
                    MatchContextRecord.fixture_id,
                    MatchContextRecord.forecast_phase,
                    MatchContextRecord.as_of.desc(),
                    MatchContextRecord.id,
                ).limit(10001)
            )
        ).all()
    )
    if len(records) > 10000:
        raise ValueError("historical_plan_limit_exceeded_narrow_scope")
    chosen: dict[tuple[UUID, str], MatchContextRecord] = {}
    for candidate_record in records:
        league = candidate_record.context_jsonb.get("fixture_identity", {}).get("league_id")
        if pop.league_ids and league not in {str(x) for x in pop.league_ids}:
            continue
        if (
            pop.context_ids
            and (candidate_record.fixture_id, candidate_record.forecast_phase) in chosen
        ):
            raise ValueError("ambiguous_context_scope_per_fixture_phase")
        chosen.setdefault(
            (candidate_record.fixture_id, candidate_record.forecast_phase), candidate_record
        )
    # Automatic denominator is historical frozen contexts, never current fixture inventory.
    requested = set(pop.fixture_ids) if pop.fixture_ids else {fid for fid, _ in chosen}
    population_basis = (
        "explicit_fixture_ids"
        if pop.fixture_ids
        else "explicit_context_ids"
        if pop.context_ids
        else "frozen_match_contexts"
    )
    if len(requested) > 1000:
        raise ValueError("historical_plan_limit_exceeded_narrow_scope")
    existing = set(
        (await session.scalars(select(Fixture.id).where(Fixture.id.in_(requested)))).all()
    )
    results = {
        r.fixture_id: r
        for r in (
            await session.scalars(
                select(FixtureResult).where(
                    FixtureResult.id.in_(latest_results_query(cutoff)),
                    FixtureResult.fixture_id.in_(requested),
                )
            )
        ).all()
    }
    manifest = []
    reasons: Counter[str] = Counter()
    eligible = 0
    for fid in sorted(requested, key=str):
        item: dict[str, Any] = {
            "fixture_id": str(fid),
            "fixture_exists": fid in existing,
            "status": "ELIGIBLE",
            "reason": None,
            "control": None,
            "treatment": None,
            "result_id": str(results[fid].id) if fid in results else None,
        }
        for name in ("control", "treatment"):
            record = chosen.get((fid, getattr(definition, name).phase))
            try:
                if record is None:
                    raise ValueError("missing_frozen_context")
                context = await verify_frozen(session, record)
                item[name] = lineage(record, context)
                arm_request = getattr(definition, name)
                if arm_request.source != "replay":
                    role = "PRIMARY" if arm_request.source == "historical_primary" else "CHALLENGER"
                    historical = await session.scalar(
                        select(PredictionRun)
                        .where(
                            PredictionRun.match_context_id == record.id,
                            PredictionRun.context_hash == record.context_hash,
                            PredictionRun.role == role,
                            PredictionRun.variant == arm_request.variant.value,
                            PredictionRun.completed_at <= cutoff,
                            PredictionRun.status.in_(("SUCCEEDED", "ABSTAINED", "FAILED")),
                        )
                        .order_by(PredictionRun.created_at, PredictionRun.id)
                        .limit(1)
                    )
                    if historical is None:
                        raise ValueError("missing_historical_prediction")
                    detail = await read_prediction(session, historical.id)
                    assert detail is not None
                    item[name]["historical_prediction_id"] = str(historical.id)
                    item[name]["historical_prediction_hash"] = digest(detail)
            except ValueError as exc:
                item["status"], item["reason"] = (
                    "NOT_REPLAYABLE",
                    (str(exc) if len(str(exc)) <= 64 else "invalid_frozen_context_contract"),
                )
                break
        if item["status"] == "ELIGIBLE":
            if eligible >= definition.max_fixtures:
                item["status"], item["reason"] = "EXCLUDED", "max_fixtures"
            else:
                eligible += 1
        if item["reason"]:
            reasons[item["reason"]] += 1
        manifest.append(item)
    missing_contexts = set(pop.context_ids) - {r.id for r in records}
    for cid in sorted(missing_contexts, key=str):
        manifest.append(
            {
                "fixture_id": None,
                "fixture_exists": False,
                "requested_context_id": str(cid),
                "status": "NOT_REPLAYABLE",
                "reason": "context_outside_scope_or_missing",
                "control": None,
                "treatment": None,
                "result_id": None,
            }
        )
        reasons["context_outside_scope_or_missing"] += 1
    return {
        "status": "READY" if eligible else "INSUFFICIENT_HISTORICAL_EVIDENCE",
        "source_cutoff": cutoff.isoformat(),
        "manifest": manifest,
        "counts": {
            "population_basis": population_basis,
            "requested": len(manifest),
            "eligible": eligible,
            "non_replayable": sum(x["status"] == "NOT_REPLAYABLE" for x in manifest),
            "excluded": sum(x["status"] == "EXCLUDED" for x in manifest),
            "reasons": dict(reasons),
        },
    }
