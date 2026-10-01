from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, computed_field


class DataQualityReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fixture_id: UUID
    forecast_phase: str
    as_of: datetime
    schema_version: str
    overall_score: float
    quality_band: str
    can_predict: bool
    dimensions_jsonb: dict[str, float]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def dimension_scores(self) -> dict[str, float]:
        return self.dimensions_jsonb

    critical_missing_jsonb: list[str]
    missing_fields_jsonb: list[dict[str, Any]]
    warnings_jsonb: list[str]
    conflicts_jsonb: list[dict[str, Any]]
    provider_errors_jsonb: list[dict[str, Any]]
    stale_sources_jsonb: list[str]
    created_at: datetime


class MatchContextSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    fixture_id: UUID
    forecast_phase: str
    as_of: datetime
    schema_version: str
    feature_schema_version: str
    context_hash: str
    overall_score: float
    quality_band: str
    can_predict: bool
    critical_missing: list[str]
    warnings: list[str]
    source_timing: dict[str, str | None]
    created_at: datetime


class MatchContextDetailOut(MatchContextSummaryOut):
    context: dict[str, Any]
