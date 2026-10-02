from __future__ import annotations

import copy
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from m7_fakes import make_context
from sports_intelligence.context.models import MatchContextV1
from sports_intelligence.core.config import Settings
from sports_intelligence.experiments.contracts import (
    AnalystOutput,
    ExperimentDefinition,
    Population,
    transition,
)
from sports_intelligence.experiments.planner import check_times
from sports_intelligence.predictions.contracts import Variant
from sports_intelligence.predictions.projection import project_context
from sports_intelligence.replay import parser
from sports_intelligence.workers.celery_app import create_celery_app


@pytest.mark.parametrize(
    "current,target",
    [
        ("PROPOSED", "APPROVED_FOR_EXPERIMENT"),
        ("PROPOSED", "REJECTED"),
        ("APPROVED_FOR_EXPERIMENT", "EXPERIMENT_RUNNING"),
        ("EXPERIMENT_RUNNING", "PROMOTED"),
        ("PROMOTED", "ROLLED_BACK"),
    ],
)
def test_valid_human_state_transitions(current, target):
    transition(current, target, proposal=True)


@pytest.mark.parametrize(
    "current,target",
    [
        ("PROPOSED", "PROMOTED"),
        ("PROPOSED", "ROLLED_BACK"),
        ("REJECTED", "PROMOTED"),
        ("ROLLED_BACK", "PROPOSED"),
        ("APPROVED_FOR_EXPERIMENT", "PROMOTED"),
    ],
)
def test_invalid_human_state_transitions(current, target):
    with pytest.raises(ValueError):
        transition(current, target, proposal=True)


@pytest.mark.parametrize(
    "current,target",
    [
        ("READY", "QUEUED"),
        ("QUEUED", "RUNNING"),
        ("RUNNING", "SUCCEEDED"),
        ("RUNNING", "FAILED"),
        ("RUNNING", "INSUFFICIENT_DATA"),
    ],
)
def test_experiment_states(current, target):
    transition(current, target)


@pytest.mark.parametrize(
    "current,target", [("READY", "SUCCEEDED"), ("SUCCEEDED", "RUNNING"), ("CANCELLED", "RUNNING")]
)
def test_invalid_experiment_states(current, target):
    with pytest.raises(ValueError):
        transition(current, target)


@pytest.mark.parametrize("path", ["market_snapshot", "metadata", "lineup", "research"])
def test_future_times_refused(path):
    context = make_context()
    data = copy.deepcopy(context.model_dump())
    future = context.fixture_identity.kickoff_at
    if path == "market_snapshot":
        data["market_snapshot"]["captured_at"] = future
    elif path == "metadata":
        data["fixture_identity"]["metadata_captured_at"] = future
    else:
        data["source_manifest"]["sources"][path] = {
            "category": path,
            "table": "lineup_snapshots",
            "captured_at": future,
        }
    with pytest.raises(ValueError, match="future_evidence"):
        check_times(MatchContextV1.model_validate(data))


def test_odds_projections_deterministic_and_do_not_mutate():
    context = make_context()
    original = context.canonical_json()
    without = project_context(context, Variant.WITHOUT_ODDS)
    assert without == project_context(context, Variant.WITHOUT_ODDS)
    assert context.canonical_json() == original
    assert without != project_context(context, Variant.WITH_ODDS)
    assert "market_snapshot" not in without


@pytest.mark.parametrize(
    "field,value",
    [
        ("sample_size", 999),
        ("metrics", {"brier": 0}),
        ("status", "PROMOTED"),
        ("title", "Brier improved by 99%"),
    ],
)
async def test_analyst_cannot_supply_measurements_or_status(field, value):
    from sports_intelligence.predictions.config import ModelSpec
    from sports_intelligence.providers.llm.mock import MockLLMProvider

    result = await MockLLMProvider().generate_structured(
        task_type="improvement_analysis",
        config=ModelSpec(provider="mock", model="analyst"),
        system_prompt="",
        payload={},
        output_schema=AnalystOutput,
        request_id="synthetic",
    )
    data = dict(result.parsed_output)
    data[field] = value
    with pytest.raises(ValidationError):
        AnalystOutput.model_validate(data)


@pytest.mark.parametrize(
    "limit,value",
    [("max_fixtures", 0), ("max_llm_calls", -1), ("batch_size", 100), ("min_paired_fixtures", 0)],
)
def test_bounded_definition(limit, value):
    pop = Population(start=datetime(2026, 8, 1, tzinfo=UTC), end=datetime(2026, 9, 1, tzinfo=UTC))
    with pytest.raises(ValidationError):
        ExperimentDefinition(
            name="Synthetic", hypothesis="Synthetic", population=pop, **{limit: value}
        )


def test_cli_plans_by_default_and_accepts_safe_options():
    args = parser().parse_args(
        [
            "--experiment",
            "synthetic.json",
            "--from",
            "2026-08-01",
            "--to",
            "2026-08-31",
            "--mock",
            "--max-calls",
            "4",
        ]
    )
    assert not args.execute and args.mock and args.max_calls == 4


def test_schedule_disabled_by_default_and_correct_queues():
    default = create_celery_app(Settings(_env_file=None))
    assert "improvements.weekly" not in default.conf.beat_schedule
    enabled = create_celery_app(Settings(_env_file=None, improvement_schedule_enabled=True))
    assert (
        enabled.conf.beat_schedule["improvements.weekly"]["task"] == "experiment.improvement_scan"
    )
    assert enabled.conf.task_routes["experiment.compare"]["queue"] == "evaluation"
    assert enabled.conf.task_routes["experiment.replay_batch"]["queue"] == "llm"
