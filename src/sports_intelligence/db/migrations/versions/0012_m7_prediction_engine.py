"""m7 prediction engine identities probabilities ranking telemetry

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-01 17:00:21.425926

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_configs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model_id", sa.String(length=128), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=False),
        sa.Column("structured_mode", sa.String(length=32), nullable=False),
        sa.Column("config_hash", sa.String(length=64), nullable=False),
        sa.Column("config_jsonb", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("config_hash"),
    )
    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("prompt_name", sa.String(length=64), nullable=False),
        sa.Column("semantic_version", sa.String(length=32), nullable=False),
        sa.Column("source_identity", sa.String(length=255), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "prompt_name", "semantic_version", "content_hash", name="uq_prompt_versions_identity"
        ),
    )
    op.create_table(
        "prediction_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("fixture_id", sa.UUID(), nullable=False),
        sa.Column("match_context_id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("context_hash", sa.String(length=64), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_phase", sa.String(length=32), nullable=False),
        sa.Column("prompt_version_id", sa.UUID(), nullable=False),
        sa.Column("requested_model_config_id", sa.UUID(), nullable=False),
        sa.Column("model_config_id", sa.UUID(), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("variant", sa.String(length=32), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("requested_route", sa.String(length=64), nullable=False),
        sa.Column("route_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("route_jsonb", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("policy_hash", sa.String(length=64), nullable=False),
        sa.Column("policy_jsonb", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("requested_identity", sa.String(length=64), nullable=False),
        sa.Column("semantic_identity", sa.String(length=64), nullable=True),
        sa.Column("request_key", sa.String(length=64), nullable=False),
        sa.Column("rerun_key", sa.String(length=64), nullable=True),
        sa.Column("actual_provider", sa.String(length=64), nullable=True),
        sa.Column("actual_model", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.String(length=64), nullable=True),
        sa.Column("abstain_reason", sa.String(length=400), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("provider_request_id", sa.String(length=200), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("output_jsonb", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("audit_jsonb", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "status IN ('QUEUED','RUNNING','SUCCEEDED','ABSTAINED','FAILED')",
            name="ck_prediction_runs_status",
        ),
        sa.ForeignKeyConstraint(["fixture_id"], ["fixtures.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["match_context_id"], ["match_contexts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["model_config_id"],
            ["model_configs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["prompt_version_id"],
            ["prompt_versions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["requested_model_config_id"],
            ["model_configs.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_key"),
    )
    op.create_index(
        "ix_prediction_runs_context", "prediction_runs", ["match_context_id"], unique=False
    )
    op.create_index(
        "ix_prediction_runs_fixture_started",
        "prediction_runs",
        ["fixture_id", sa.literal_column("started_at DESC")],
        unique=False,
    )
    op.create_index(
        "ix_prediction_runs_semantic", "prediction_runs", ["semantic_identity"], unique=False
    )
    op.create_table(
        "llm_call_attempts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("prediction_run_id", sa.UUID(), nullable=False),
        sa.Column("external_request_id", sa.UUID(), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("health", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("provider_request_id", sa.String(length=200), nullable=True),
        sa.Column("actual_model", sa.String(length=128), nullable=True),
        sa.Column("finish_reason", sa.String(length=200), nullable=True),
        sa.Column("raw_response_reference", sa.String(length=128), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["external_request_id"], ["external_api_requests.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["prediction_run_id"], ["prediction_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prediction_run_id", "attempt_number", name="uq_llm_attempts_number"),
    )
    op.create_index(
        "ix_llm_attempts_budget", "llm_call_attempts", ["started_at", "task_type"], unique=False
    )
    op.create_index(
        "ix_llm_attempts_provider_model_started",
        "llm_call_attempts",
        ["provider", "model", sa.literal_column("started_at DESC")],
        unique=False,
    )
    op.create_table(
        "market_predictions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("prediction_run_id", sa.UUID(), nullable=False),
        sa.Column("market", sa.String(length=32), nullable=False),
        sa.Column("selection", sa.String(length=32), nullable=False),
        sa.Column("model_probability", sa.Float(), nullable=False),
        sa.Column("confidence", sa.String(length=32), nullable=False),
        sa.Column("evidence_for_jsonb", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "evidence_against_jsonb", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("risk_flags_jsonb", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "model_probability >= 0 AND model_probability <= 1",
            name="ck_market_predictions_probability",
        ),
        sa.ForeignKeyConstraint(["prediction_run_id"], ["prediction_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "prediction_run_id", "selection", name="uq_market_predictions_selection"
        ),
    )
    op.create_table(
        "probability_baselines",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("prediction_run_id", sa.UUID(), nullable=False),
        sa.Column("match_context_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=32), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("probabilities_jsonb", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("inputs_jsonb", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("limitations_jsonb", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("unavailable_reason", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["match_context_id"], ["match_contexts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["prediction_run_id"], ["prediction_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("prediction_run_id", "name", name="uq_probability_baselines_run_name"),
    )
    op.create_table(
        "ranked_candidates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("prediction_run_id", sa.UUID(), nullable=False),
        sa.Column("market_prediction_id", sa.UUID(), nullable=False),
        sa.Column("odds_snapshot_set_id", sa.UUID(), nullable=True),
        sa.Column("odds_captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bookmaker", sa.String(length=128), nullable=True),
        sa.Column("captured_odds", sa.Float(), nullable=True),
        sa.Column("market_no_vig_probability", sa.Float(), nullable=True),
        sa.Column("edge", sa.Float(), nullable=True),
        sa.Column("expected_value", sa.Float(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=True),
        sa.Column("displayed", sa.Boolean(), nullable=False),
        sa.Column("filter_reasons_jsonb", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("policy_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["market_prediction_id"], ["market_predictions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["odds_snapshot_set_id"],
            ["odds_snapshot_sets.id"],
        ),
        sa.ForeignKeyConstraint(["prediction_run_id"], ["prediction_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "prediction_run_id", "market_prediction_id", name="uq_ranked_candidates_market"
        ),
    )
    op.create_index(
        "ix_ranked_candidates_run_displayed",
        "ranked_candidates",
        ["prediction_run_id", "displayed"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ranked_candidates_run_displayed", table_name="ranked_candidates")
    op.drop_table("ranked_candidates")
    op.drop_table("probability_baselines")
    op.drop_table("market_predictions")
    op.drop_index("ix_llm_attempts_provider_model_started", table_name="llm_call_attempts")
    op.drop_index("ix_llm_attempts_budget", table_name="llm_call_attempts")
    op.drop_table("llm_call_attempts")
    op.drop_index("ix_prediction_runs_semantic", table_name="prediction_runs")
    op.drop_index("ix_prediction_runs_fixture_started", table_name="prediction_runs")
    op.drop_index("ix_prediction_runs_context", table_name="prediction_runs")
    op.drop_table("prediction_runs")
    op.drop_table("prompt_versions")
    op.drop_table("model_configs")
