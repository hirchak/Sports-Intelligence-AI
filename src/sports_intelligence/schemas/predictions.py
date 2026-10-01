from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sports_intelligence.predictions.contracts import Role, Selection, Variant


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    phase: Literal["MORNING", "PREMATCH"] = "MORNING"
    context_id: UUID | None = None
    as_of: datetime | None = None
    role: Role = Role.PRIMARY
    variant: Variant = Variant.WITH_ODDS
    route_override: str | None = Field(default=None, max_length=64)
    rerun: bool = False
    rerun_key: UUID | None = None

    @model_validator(mode="after")
    def consistent(self) -> AnalyzeRequest:
        if self.as_of is not None and self.as_of.tzinfo is None:
            raise ValueError("as_of must include timezone")
        if self.rerun != (self.rerun_key is not None):
            raise ValueError(
                "explicit rerun requires stable rerun_key UUID; ordinary request cannot have one"
            )
        return self


class AnalyzeResponse(BaseModel):
    run_id: UUID
    job_id: UUID
    status: str
    already_queued: bool
    requested_identity: str


class PredictionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    fixture_id: UUID
    match_context_id: UUID
    context_hash: str
    forecast_phase: str
    as_of: datetime
    role: Role
    variant: Variant
    status: str
    outcome: str | None
    actual_provider: str | None
    actual_model: str | None
    created_at: datetime
    completed_at: datetime | None


class ProbabilityRow(BaseModel):
    market: str
    selection: Selection
    model_probability: float


class CandidateRow(BaseModel):
    selection: Selection
    model_probability: float
    captured_odds: float | None
    market_probability: float | None
    edge: float | None
    expected_value: float | None
    rank: int | None
    displayed: bool
    filter_reasons: list[str]
    bookmaker: str | None
    odds_snapshot_set_id: UUID | None
    odds_captured_at: datetime | None


class PredictionDetail(PredictionSummary):
    home_team: str | None
    away_team: str | None
    data_quality: float
    abstain_reason: str | None
    error_code: str | None
    model_config_hash: str | None
    runtime_model_config: dict[str, Any] | None
    requested_model_config: dict[str, Any]
    prompt_name: str
    prompt_version: str
    prompt_hash: str
    prompt_source: str
    requested_identity: str
    semantic_identity: str | None
    requested_route: str
    route_fingerprint: str
    policy: dict[str, Any]
    policy_hash: str
    latency_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    provider_request_id: str | None
    audit: list[str]
    output: dict[str, Any] | None
    probabilities: list[ProbabilityRow]
    candidates: list[CandidateRow]
    baselines: list[dict[str, Any]]
    attempts: list[dict[str, Any]]
