from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from sports_intelligence.core.phases import ForecastPhase
from sports_intelligence.db.models import (
    DataQualityReport,
    FeatureSnapshot,
    Fixture,
    MatchContextRecord,
)
from sports_intelligence.schemas.context import (
    DataQualityReportOut,
    MatchContextDetailOut,
)

router = APIRouter(tags=["context"])


@router.get("/v1/fixtures/{fixture_id}/quality", response_model=DataQualityReportOut)
async def get_fixture_quality(
    fixture_id: UUID,
    request: Request,
    as_of: Annotated[
        datetime | None,
        Query(description="Point-in-time cutoff for historical quality evaluation"),
    ] = None,
    phase: Annotated[
        ForecastPhase | None,
        Query(description="Forecast phase filter (e.g. MORNING, PREMATCH)"),
    ] = None,
) -> DataQualityReportOut:
    session_factory = request.app.state.session_factory
    if not isinstance(session_factory, async_sessionmaker):
        raise RuntimeError("session factory not configured")

    as_of_utc = (
        as_of.astimezone(UTC)
        if as_of and as_of.tzinfo
        else (as_of.replace(tzinfo=UTC) if as_of else None)
    )

    async with session_factory() as session:
        fixture = await session.get(Fixture, fixture_id)
        if fixture is None:
            raise HTTPException(status_code=404, detail="fixture not found")

        stmt = select(DataQualityReport).where(DataQualityReport.fixture_id == fixture_id)
        if as_of_utc is not None:
            stmt = stmt.where(DataQualityReport.as_of <= as_of_utc)
        if phase is not None:
            stmt = stmt.where(DataQualityReport.forecast_phase == phase.value)
        stmt = stmt.order_by(
            DataQualityReport.as_of.desc(), DataQualityReport.created_at.desc()
        ).limit(1)

        report = (await session.execute(stmt)).scalar_one_or_none()
        if report is None:
            raise HTTPException(status_code=404, detail="quality report not found")

        return DataQualityReportOut.model_validate(report)


@router.get("/v1/fixtures/{fixture_id}/context", response_model=MatchContextDetailOut)
async def get_fixture_context(
    fixture_id: UUID,
    request: Request,
    as_of: Annotated[
        datetime | None,
        Query(description="Point-in-time cutoff for historical context retrieval"),
    ] = None,
    phase: Annotated[
        ForecastPhase | None,
        Query(description="Forecast phase filter (e.g. MORNING, PREMATCH)"),
    ] = None,
) -> MatchContextDetailOut:
    session_factory = request.app.state.session_factory
    if not isinstance(session_factory, async_sessionmaker):
        raise RuntimeError("session factory not configured")

    as_of_utc = (
        as_of.astimezone(UTC)
        if as_of and as_of.tzinfo
        else (as_of.replace(tzinfo=UTC) if as_of else None)
    )

    async with session_factory() as session:
        fixture = await session.get(Fixture, fixture_id)
        if fixture is None:
            raise HTTPException(status_code=404, detail="fixture not found")

        stmt = select(MatchContextRecord).where(MatchContextRecord.fixture_id == fixture_id)
        if as_of_utc is not None:
            stmt = stmt.where(MatchContextRecord.as_of <= as_of_utc)
        if phase is not None:
            stmt = stmt.where(MatchContextRecord.forecast_phase == phase.value)
        stmt = stmt.order_by(
            MatchContextRecord.as_of.desc(), MatchContextRecord.created_at.desc()
        ).limit(1)

        record = (await session.execute(stmt)).scalar_one_or_none()
        if record is None:
            raise HTTPException(status_code=404, detail="match context not found")

        # Load linked quality report and feature snapshot
        quality_rep: DataQualityReport | None = None
        if record.data_quality_report_id:
            quality_rep = await session.get(DataQualityReport, record.data_quality_report_id)

        feature_snap: FeatureSnapshot | None = None
        if record.feature_snapshot_id:
            feature_snap = await session.get(FeatureSnapshot, record.feature_snapshot_id)

        # Extract compact source timing summary
        ctx_data = record.context_jsonb or {}
        manifest_data = ctx_data.get("source_manifest", {}).get("sources", {})
        source_timing: dict[str, str | None] = {}
        for cat, rec in manifest_data.items():
            if isinstance(rec, dict):
                source_timing[cat] = rec.get("captured_at")

        overall_score = quality_rep.overall_score if quality_rep else 0.0
        quality_band = quality_rep.quality_band if quality_rep else "unknown"
        can_predict = quality_rep.can_predict if quality_rep else False
        critical_missing = quality_rep.critical_missing_jsonb if quality_rep else []
        warnings = quality_rep.warnings_jsonb if quality_rep else []
        feat_version = feature_snap.schema_version if feature_snap else "unknown"

        return MatchContextDetailOut(
            id=record.id,
            fixture_id=record.fixture_id,
            forecast_phase=record.forecast_phase,
            as_of=record.as_of,
            schema_version=record.schema_version,
            feature_schema_version=feat_version,
            context_hash=record.context_hash,
            overall_score=overall_score,
            quality_band=quality_band,
            can_predict=can_predict,
            critical_missing=critical_missing,
            warnings=warnings,
            source_timing=source_timing,
            created_at=record.created_at,
            context=ctx_data,
        )
