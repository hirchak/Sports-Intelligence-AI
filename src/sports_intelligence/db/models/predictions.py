from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from sports_intelligence.db.models.base import Base


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint(
            "prompt_name", "semantic_version", "content_hash", name="uq_prompt_versions_identity"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prompt_name: Mapped[str] = mapped_column(String(64))
    semantic_version: Mapped[str] = mapped_column(String(32))
    source_identity: Mapped[str] = mapped_column(String(255))
    content_hash: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelConfig(Base):
    __tablename__ = "model_configs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(64))
    model_id: Mapped[str] = mapped_column(String(128))
    temperature: Mapped[float | None] = mapped_column(Float)
    max_tokens: Mapped[int] = mapped_column(Integer)
    structured_mode: Mapped[str] = mapped_column(String(32))
    config_hash: Mapped[str] = mapped_column(String(64), unique=True)
    config_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PredictionRun(Base):
    __tablename__ = "prediction_runs"
    __table_args__ = (
        Index("ix_prediction_runs_fixture_started", "fixture_id", text("started_at DESC")),
        Index("ix_prediction_runs_context", "match_context_id"),
        Index("ix_prediction_runs_semantic", "semantic_identity"),
        CheckConstraint(
            "status IN ('QUEUED','RUNNING','SUCCEEDED','ABSTAINED','FAILED')",
            name="ck_prediction_runs_status",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fixture_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fixtures.id", ondelete="CASCADE")
    )
    match_context_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("match_contexts.id", ondelete="CASCADE")
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE")
    )
    context_hash: Mapped[str] = mapped_column(String(64))
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    forecast_phase: Mapped[str] = mapped_column(String(32))
    prompt_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prompt_versions.id")
    )
    requested_model_config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_configs.id")
    )
    model_config_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("model_configs.id")
    )
    role: Mapped[str] = mapped_column(String(32))
    variant: Mapped[str] = mapped_column(String(32))
    task_type: Mapped[str] = mapped_column(String(64))
    requested_route: Mapped[str] = mapped_column(String(64))
    route_fingerprint: Mapped[str] = mapped_column(String(64))
    route_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB)
    policy_hash: Mapped[str] = mapped_column(String(64))
    policy_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB)
    requested_identity: Mapped[str] = mapped_column(String(64))
    semantic_identity: Mapped[str | None] = mapped_column(String(64))
    request_key: Mapped[str] = mapped_column(String(64), unique=True)
    rerun_key: Mapped[str | None] = mapped_column(String(64))
    actual_provider: Mapped[str | None] = mapped_column(String(64))
    actual_model: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="QUEUED")
    outcome: Mapped[str | None] = mapped_column(String(64))
    abstain_reason: Mapped[str | None] = mapped_column(String(400))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    provider_request_id: Mapped[str | None] = mapped_column(String(200))
    error_code: Mapped[str | None] = mapped_column(String(64))
    output_jsonb: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    audit_jsonb: Mapped[list[str]] = mapped_column(JSONB, default=list)


class MarketPrediction(Base):
    __tablename__ = "market_predictions"
    __table_args__ = (
        UniqueConstraint("prediction_run_id", "selection", name="uq_market_predictions_selection"),
        CheckConstraint(
            "model_probability >= 0 AND model_probability <= 1",
            name="ck_market_predictions_probability",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prediction_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prediction_runs.id", ondelete="CASCADE")
    )
    market: Mapped[str] = mapped_column(String(32))
    selection: Mapped[str] = mapped_column(String(32))
    model_probability: Mapped[float] = mapped_column(Float)
    confidence: Mapped[str] = mapped_column(String(32))
    evidence_for_jsonb: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    evidence_against_jsonb: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    risk_flags_jsonb: Mapped[list[str]] = mapped_column(JSONB)


class RankedCandidate(Base):
    __tablename__ = "ranked_candidates"
    __table_args__ = (
        UniqueConstraint(
            "prediction_run_id", "market_prediction_id", name="uq_ranked_candidates_market"
        ),
        Index("ix_ranked_candidates_run_displayed", "prediction_run_id", "displayed"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prediction_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prediction_runs.id", ondelete="CASCADE")
    )
    market_prediction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("market_predictions.id", ondelete="CASCADE")
    )
    odds_snapshot_set_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("odds_snapshot_sets.id")
    )
    odds_captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bookmaker: Mapped[str | None] = mapped_column(String(128))
    captured_odds: Mapped[float | None] = mapped_column(Float)
    market_no_vig_probability: Mapped[float | None] = mapped_column(Float)
    edge: Mapped[float | None] = mapped_column(Float)
    expected_value: Mapped[float | None] = mapped_column(Float)
    rank: Mapped[int | None] = mapped_column(Integer)
    displayed: Mapped[bool] = mapped_column(Boolean)
    filter_reasons_jsonb: Mapped[list[str]] = mapped_column(JSONB)
    policy_hash: Mapped[str] = mapped_column(String(64))


class ProbabilityBaseline(Base):
    __tablename__ = "probability_baselines"
    __table_args__ = (
        UniqueConstraint("prediction_run_id", "name", name="uq_probability_baselines_run_name"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prediction_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prediction_runs.id", ondelete="CASCADE")
    )
    match_context_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("match_contexts.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(32))
    version: Mapped[str] = mapped_column(String(32))
    probabilities_jsonb: Mapped[dict[str, float]] = mapped_column(JSONB)
    inputs_jsonb: Mapped[dict[str, float]] = mapped_column(JSONB)
    limitations_jsonb: Mapped[list[str]] = mapped_column(JSONB)
    unavailable_reason: Mapped[str | None] = mapped_column(String(64))


class LLMCallAttempt(Base):
    __tablename__ = "llm_call_attempts"
    __table_args__ = (
        UniqueConstraint("prediction_run_id", "attempt_number", name="uq_llm_attempts_number"),
        Index(
            "ix_llm_attempts_provider_model_started", "provider", "model", text("started_at DESC")
        ),
        Index("ix_llm_attempts_budget", "started_at", "task_type"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    prediction_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prediction_runs.id", ondelete="CASCADE")
    )
    external_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("external_api_requests.id", ondelete="SET NULL")
    )
    attempt_number: Mapped[int] = mapped_column(Integer)
    task_type: Mapped[str] = mapped_column(String(64))
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    purpose: Mapped[str] = mapped_column(String(32))
    health: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    provider_request_id: Mapped[str | None] = mapped_column(String(200))
    actual_model: Mapped[str | None] = mapped_column(String(128))
    finish_reason: Mapped[str | None] = mapped_column(String(200))
    raw_response_reference: Mapped[str | None] = mapped_column(String(128))
    error_code: Mapped[str | None] = mapped_column(String(64))
    status_code: Mapped[int | None] = mapped_column(Integer)
