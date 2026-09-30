from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from sports_intelligence.db.models.base import Base


class FeatureSnapshot(Base):
    """Immutable deterministic feature snapshot derived for a fixture and phase."""

    __tablename__ = "feature_snapshots"
    __table_args__ = (
        Index("ix_feature_snapshots_fixture_as_of", "fixture_id", text("as_of DESC")),
        Index("ix_feature_snapshots_fixture_phase", "fixture_id", "forecast_phase"),
        UniqueConstraint(
            "fixture_id",
            "forecast_phase",
            "as_of",
            "schema_version",
            "source_fingerprint",
            name="uq_feature_snapshots_identity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fixture_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fixtures.id", ondelete="CASCADE"), nullable=False
    )
    forecast_phase: Mapped[str] = mapped_column(String(32), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default="features_v1")
    features_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    source_manifest_jsonb: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    feature_provenance_jsonb: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DataQualityReport(Base):
    """Immutable data quality assessment report for a fixture, phase, and point in time."""

    __tablename__ = "data_quality_reports"
    __table_args__ = (
        Index("ix_data_quality_reports_fixture_as_of", "fixture_id", text("as_of DESC")),
        Index("ix_data_quality_reports_fixture_phase", "fixture_id", "forecast_phase"),
        UniqueConstraint(
            "fixture_id",
            "forecast_phase",
            "as_of",
            "schema_version",
            "source_fingerprint",
            "policy_fingerprint",
            name="uq_data_quality_reports_identity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fixture_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fixtures.id", ondelete="CASCADE"), nullable=False
    )
    forecast_phase: Mapped[str] = mapped_column(String(32), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False, default="quality_v1")
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    quality_band: Mapped[str] = mapped_column(String(32), nullable=False)
    can_predict: Mapped[bool] = mapped_column(Boolean, nullable=False)
    dimensions_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    critical_missing_jsonb: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    missing_fields_jsonb: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    warnings_jsonb: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    conflicts_jsonb: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    provider_errors_jsonb: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    stale_sources_jsonb: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    source_manifest_jsonb: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    source_fingerprint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quality_policy_jsonb: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    policy_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MatchContextRecord(Base):
    """Immutable, frozen MatchContext record with SHA-256 canonical hash."""

    __tablename__ = "match_contexts"
    __table_args__ = (
        Index("ix_match_contexts_fixture_as_of", "fixture_id", text("as_of DESC")),
        Index("ix_match_contexts_fixture_phase", "fixture_id", "forecast_phase"),
        Index("ix_match_contexts_hash", "context_hash"),
        UniqueConstraint(
            "fixture_id",
            "forecast_phase",
            "as_of",
            "schema_version",
            "context_hash",
            name="uq_match_contexts_identity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fixture_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fixtures.id", ondelete="CASCADE"), nullable=False
    )
    forecast_phase: Mapped[str] = mapped_column(String(32), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    schema_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="match_context_v1"
    )
    context_jsonb: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    context_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    data_quality_report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_quality_reports.id", ondelete="SET NULL"),
        nullable=True,
    )
    feature_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("feature_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
