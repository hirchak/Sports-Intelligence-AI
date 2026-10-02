from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from sports_intelligence.evaluation.config import EvaluationConfig, EvaluationFilters
from sports_intelligence.evaluation.settlement import ResultStatus


class EvaluateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    filters: EvaluationFilters = EvaluationFilters()
    config: EvaluationConfig | None = None
    cutoff: datetime | None = None
    period: Literal["7d", "30d", "all"] = "30d"


class ResultView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    fixture_id: UUID
    provider: str
    provider_fixture_id: str
    status: ResultStatus
    regulation_home: int | None
    regulation_away: int | None
    extra_time_home: int | None
    extra_time_away: int | None
    penalties_home: int | None
    penalties_away: int | None
    observed_at: datetime
    version: int
    source_identity: str
    raw_payload_id: UUID | None
    supersedes_id: UUID | None
    created_at: datetime


class MetricView(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    value: float | None
    sample_size: int = Field(ge=0)


class EvaluationGroupView(BaseModel):
    dimensions: dict[str, str]
    metrics: dict[str, MetricView]
    sample_size: int = Field(ge=0)
    calibration: list[dict[str, float | int | None]] = []


class EvaluationSummaryView(BaseModel):
    status: Literal["SUCCEEDED", "not_available"]
    groups: list[EvaluationGroupView]
    sample_size: int = 0
    has_more: bool = False


class ResultDetailView(BaseModel):
    latest: ResultView
    history: list[ResultView]
    history_limit: int
    settlement_version: str


class SettlementView(BaseModel):
    run_id: UUID
    market_prediction_id: UUID
    selection: str
    probability: float
    outcome: Literal["WIN", "LOSS", "PUSH", "VOID", "UNSETTLED"]
    result_id: UUID
    settlement_version: str
    role: str
    variant: str
