from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from sports_intelligence.predictions.contracts import Role, Selection, StrictModel, Variant


class EvaluationConfig(StrictModel):
    version: Literal["evaluation_v1"] = "evaluation_v1"
    settlement_version: Literal["regulation_v1"] = "regulation_v1"
    metric_version: Literal["metrics_v1"] = "metrics_v1"
    epsilon: Annotated[float, Field(ge=2.220446049250313e-16, lt=0.01, allow_inf_nan=False)] = 1e-15
    calibration_boundaries: Annotated[tuple[float, ...], Field(min_length=2, max_length=101)] = (
        tuple(i / 10 for i in range(11))
    )
    odds_boundaries: Annotated[tuple[float, ...], Field(min_length=2, max_length=101)] = (
        1.0,
        1.5,
        2.0,
        3.0,
        5.0,
    )
    research_stake: Literal[1] = 1
    closing_snapshot_ids: Annotated[tuple[UUID, ...], Field(max_length=1000)] = ()

    @model_validator(mode="after")
    def boundaries(self) -> EvaluationConfig:
        import math

        for values in (self.calibration_boundaries, self.odds_boundaries):
            if len(values) < 2 or not all(math.isfinite(v) for v in values):
                raise ValueError("invalid bucket boundaries")
            if any(a >= b for a, b in zip(values, values[1:], strict=False)):
                raise ValueError("bucket boundaries must increase")
        if self.calibration_boundaries[0] != 0 or self.calibration_boundaries[-1] != 1:
            raise ValueError("calibration must cover [0,1]")
        if self.odds_boundaries[0] != 1:
            raise ValueError("odds buckets must start at 1")
        return self


class EvaluationFilters(StrictModel):
    start: datetime | None = None
    end: datetime | None = None
    league: UUID | None = None
    market: Literal["1x2", "double_chance", "ou_15", "ou_25", "btts"] | None = None
    selection: Selection | None = None
    model_config_id: UUID | None = None
    provider: str | None = None
    model: str | None = None
    prompt: str | None = None
    role: Role | None = None
    variant: Variant | None = None
    phase: Literal["MORNING", "PREMATCH"] | None = None
    data_quality: str | None = None
    confidence: Literal["low", "medium", "high"] | None = None
    baseline_version: str | None = None
    odds_bucket: str | None = None
    baseline: Literal["llm", "market", "statistical"] | None = None

    @field_validator("start", "end")
    @classmethod
    def aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("UTC-aware period required")
        return value.astimezone(UTC) if value else None

    @model_validator(mode="after")
    def period(self) -> EvaluationFilters:
        if self.start and self.end and self.start >= self.end:
            raise ValueError("start must precede end")
        return self
