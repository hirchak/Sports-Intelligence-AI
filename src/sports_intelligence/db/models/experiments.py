from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
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


class Experiment(Base):
    __tablename__ = "experiments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','READY','QUEUED','RUNNING','SUCCEEDED','FAILED',"
            "'CANCELLED','INSUFFICIENT_DATA')",
            name="ck_experiment_status",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    definition_hash: Mapped[str] = mapped_column(String(64), unique=True)
    definition_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB)
    name: Mapped[str] = mapped_column(String(200))
    created_by: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="READY")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExperimentArm(Base):
    __tablename__ = "experiment_arms"
    __table_args__ = (UniqueConstraint("experiment_id", "name", name="uq_experiment_arm"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    experiment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("experiments.id"))
    name: Mapped[str] = mapped_column(String(32))
    identity_hash: Mapped[str] = mapped_column(String(64))
    frozen_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB)


class ExperimentRun(Base):
    __tablename__ = "experiment_runs"
    __table_args__ = (Index("ix_experiment_runs_experiment", "experiment_id", "created_at"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    experiment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("experiments.id"))
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id"))
    identity_hash: Mapped[str] = mapped_column(String(64), unique=True)
    manifest_hash: Mapped[str] = mapped_column(String(64))
    manifest_jsonb: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    counts_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB)
    audit_jsonb: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    rerun_key: Mapped[str | None] = mapped_column(String(64))
    live_opt_in: Mapped[bool] = mapped_column(default=False)
    source_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="QUEUED")
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExperimentCase(Base):
    __tablename__ = "experiment_cases"
    __table_args__ = (UniqueConstraint("run_id", "ordinal", name="uq_experiment_case"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("experiment_runs.id"))
    ordinal: Mapped[int] = mapped_column(Integer)
    fixture_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fixtures.id"))
    control_context_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("match_contexts.id"))
    treatment_context_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("match_contexts.id"))
    result_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fixture_results.id"))
    status: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(String(64))
    lineage_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB)


class ExperimentPrediction(Base):
    __tablename__ = "experiment_predictions"
    __table_args__ = (
        UniqueConstraint("case_id", "arm_id", name="uq_experiment_prediction"),
        CheckConstraint(
            "status IN ('QUEUED','RUNNING','SUCCEEDED','ABSTAINED','FAILED')",
            name="ck_experiment_prediction_status",
        ),
        Index("ix_experiment_predictions_status", "status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("experiment_cases.id"))
    arm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("experiment_arms.id"))
    status: Mapped[str] = mapped_column(String(32), default="QUEUED")
    output_jsonb: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    probabilities_jsonb: Mapped[dict[str, float]] = mapped_column(JSONB, default=dict)
    candidates_jsonb: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    baselines_jsonb: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    actual_identity_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    audit_jsonb: Mapped[list[str]] = mapped_column(JSONB, default=list)
    reason: Mapped[str | None] = mapped_column(String(64))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExperimentCall(Base):
    __tablename__ = "experiment_calls"
    __table_args__ = (Index("ix_experiment_calls_run_arm", "run_id", "arm_id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("experiment_runs.id"))
    arm_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("experiment_arms.id"))
    prediction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("experiment_predictions.id"))
    provider: Mapped[str] = mapped_column(String(64))
    model: Mapped[str] = mapped_column(String(128))
    purpose: Mapped[str] = mapped_column(String(32))
    result_jsonb: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(64))
    external_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("external_api_requests.id")
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExperimentComparison(Base):
    __tablename__ = "experiment_comparisons"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("experiment_runs.id"), unique=True)
    evaluation_version: Mapped[str] = mapped_column(String(32))
    summary_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImprovementProposal(Base):
    __tablename__ = "improvement_proposals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PROPOSED','APPROVED_FOR_EXPERIMENT','EXPERIMENT_RUNNING',"
            "'REJECTED','PROMOTED','ROLLED_BACK')",
            name="ck_proposal_status",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    evidence_hash: Mapped[str] = mapped_column(String(64), unique=True)
    comparison_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("experiment_comparisons.id"))
    content_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB)
    evidence_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB)
    analyst_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB)
    sample_size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="PROPOSED")
    experiment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("experiments.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImprovementProposalEvent(Base):
    __tablename__ = "improvement_proposal_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proposal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("improvement_proposals.id"))
    from_status: Mapped[str] = mapped_column(String(32))
    to_status: Mapped[str] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ImprovementAnalysis(Base):
    __tablename__ = "improvement_analyses"
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id"), primary_key=True)
    frozen_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_jsonb: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
