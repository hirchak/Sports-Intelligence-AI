from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from sports_intelligence.db.models.base import Base


class FixtureResult(Base):
    __tablename__ = "fixture_results"
    __table_args__ = (
        UniqueConstraint("fixture_id", "version", name="uq_fixture_results_version"),
        Index("ix_fixture_results_fixture_observed", "fixture_id", "observed_at", "version"),
        CheckConstraint("version > 0", name="ck_fixture_results_version"),
        CheckConstraint(
            "status IN ('FINAL','AFTER_EXTRA_TIME','AFTER_PENALTIES','POSTPONED',"
            "'CANCELLED','ABANDONED','UNFINISHED','UNKNOWN')",
            name="ck_fixture_results_status",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fixture_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fixtures.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(32))
    provider_fixture_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    regulation_home: Mapped[int | None] = mapped_column(Integer)
    regulation_away: Mapped[int | None] = mapped_column(Integer)
    extra_time_home: Mapped[int | None] = mapped_column(Integer)
    extra_time_away: Mapped[int | None] = mapped_column(Integer)
    penalties_home: Mapped[int | None] = mapped_column(Integer)
    penalties_away: Mapped[int | None] = mapped_column(Integer)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer)
    source_identity: Mapped[str] = mapped_column(String(64))
    normalized_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB)
    raw_payload_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("raw_provider_payloads.id"))
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fixture_results.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PredictionSettlement(Base):
    __tablename__ = "prediction_settlements"
    __table_args__ = (
        UniqueConstraint(
            "market_prediction_id",
            "fixture_result_id",
            "settlement_version",
            name="uq_prediction_settlements_identity",
        ),
        Index("ix_prediction_settlements_result", "fixture_result_id"),
        CheckConstraint(
            "outcome IN ('WIN','LOSS','PUSH','VOID','UNSETTLED')",
            name="ck_prediction_settlements_outcome",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    market_prediction_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("market_predictions.id", ondelete="CASCADE")
    )
    fixture_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fixture_results.id", ondelete="CASCADE")
    )
    settlement_version: Mapped[str] = mapped_column(String(32))
    outcome: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(String(64))
    settled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CandidateSettlement(Base):
    __tablename__ = "candidate_settlements"
    __table_args__ = (
        UniqueConstraint(
            "ranked_candidate_id",
            "prediction_settlement_id",
            name="uq_candidate_settlements_identity",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ranked_candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ranked_candidates.id", ondelete="CASCADE")
    )
    prediction_settlement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prediction_settlements.id", ondelete="CASCADE")
    )
    net_return: Mapped[float | None] = mapped_column(Float)
    stake: Mapped[int] = mapped_column(Integer, default=1)


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (Index("ix_evaluation_runs_cutoff", "source_cutoff"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    identity: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(32), default="QUEUED")
    source_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    config_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB)
    filters_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB)
    source_manifest_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    error_class: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EvaluationMetric(Base):
    __tablename__ = "evaluation_metrics"
    __table_args__ = (
        UniqueConstraint(
            "evaluation_run_id",
            "dimension_key",
            "metric_name",
            name="uq_evaluation_metrics_identity",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE")
    )
    dimension_key: Mapped[str] = mapped_column(String(64))
    dimensions_jsonb: Mapped[dict[str, str]] = mapped_column(JSONB)
    metric_name: Mapped[str] = mapped_column(String(64))
    metric_value: Mapped[float | None] = mapped_column(Float)
    sample_size: Mapped[int] = mapped_column(Integer)


class CalibrationBucket(Base):
    __tablename__ = "calibration_buckets"
    __table_args__ = (
        UniqueConstraint(
            "evaluation_run_id",
            "dimension_key",
            "bucket_index",
            name="uq_calibration_buckets_identity",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE")
    )
    dimension_key: Mapped[str] = mapped_column(String(64))
    bucket_index: Mapped[int] = mapped_column(Integer)
    lower: Mapped[float] = mapped_column(Float)
    upper: Mapped[float] = mapped_column(Float)
    sample_size: Mapped[int] = mapped_column(Integer)
    mean_probability: Mapped[float | None] = mapped_column(Float)
    event_frequency: Mapped[float | None] = mapped_column(Float)
    calibration_gap: Mapped[float | None] = mapped_column(Float)
