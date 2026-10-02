"""M9 keyless acceptance on real isolated Compose Postgres/Redis."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update

from m7_fakes import ScriptedProvider, valid_output
from m9_fakes import definition, frozen_record
from sports_intelligence.api.app import create_app
from sports_intelligence.context.models import MatchContextV1
from sports_intelligence.db.models import (
    Base,
    Experiment,
    ExperimentCall,
    ExperimentCase,
    ExperimentComparison,
    ExperimentPrediction,
    ExperimentRun,
    Fixture,
    FixtureResult,
    ImprovementProposal,
    ImprovementProposalEvent,
    Job,
    League,
    LineupSnapshot,
    MatchContextRecord,
    OddsSnapshotSet,
    PredictionRun,
    ResearchDocument,
    Team,
)
from sports_intelligence.db.session import create_engine, create_session_factory
from sports_intelligence.evaluation.results import persist_result
from sports_intelligence.evaluation.settlement import ResultObservation, ResultStatus
from sports_intelligence.experiments.analyst import (
    approve_experiment,
    generate_proposal,
    human_transition,
    request_analysis,
)
from sports_intelligence.experiments.comparison import compare_run
from sports_intelligence.experiments.contracts import (
    ApproveRequest,
    ArmRequest,
    HumanAction,
    RunRequest,
)
from sports_intelligence.experiments.planner import plan_replay
from sports_intelligence.experiments.runner import run_batch
from sports_intelligence.experiments.service import create_experiment, request_run
from sports_intelligence.predictions.contracts import Variant
from sports_intelligence.predictions.service import request_prediction
from sports_intelligence.providers.llm.base import LLMError
from sports_intelligence.workers.tasks.llm import run_prediction_job

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="test DB required"),
]


@pytest.fixture
async def factory(service_settings):
    engine = create_engine(service_settings.database_url)
    factory = create_session_factory(engine)

    async def cleanup():
        async with factory() as s, s.begin():
            names = {
                "experiments",
                "experiment_arms",
                "experiment_runs",
                "experiment_cases",
                "experiment_predictions",
                "experiment_calls",
                "experiment_comparisons",
                "improvement_proposals",
                "improvement_proposal_events",
                "improvement_analyses",
            }
            for table in reversed(Base.metadata.sorted_tables):
                if table.name in names:
                    await s.execute(delete(table))
            await s.execute(
                delete(Job).where(Job.job_type.in_(("experiment", "improvement_analysis")))
            )

    await cleanup()
    try:
        yield factory
    finally:
        await cleanup()
        await engine.dispose()


@pytest.fixture
async def record(factory):
    return await frozen_record(factory)


async def with_result(factory, record):
    async with factory() as s, s.begin():
        result, _ = await persist_result(
            s,
            record.fixture_id,
            "mock",
            ResultObservation(
                provider_fixture_id=42,
                provider_status="FT",
                status=ResultStatus.FINAL,
                regulation_home=2,
                regulation_away=1,
                observed_at=datetime.fromisoformat(
                    record.context_jsonb["fixture_identity"]["kickoff_at"]
                )
                + timedelta(hours=3),
            ),
        )
        return result


async def queue(factory, settings, definition):
    async with factory() as s:
        experiment, _ = await create_experiment(s, definition, settings)
        run, created = await request_run(s, experiment, RunRequest(), settings)
        await s.commit()
        return experiment, run, created


async def complete(factory, settings, run, provider=None):
    while True:
        result = await run_batch(factory, run.id, settings, provider)
        if result["status"] != "MORE":
            break
    async with factory() as s:
        comparison = await compare_run(s, run.id)
        await s.commit()
        return comparison


async def test_frozen_replay_pairing_m8_metrics_and_unchanged_production(
    factory, record, service_settings
):
    await with_result(factory, record)
    async with factory() as s:
        original, _ = await request_prediction(s, record=record, settings=service_settings)
        await s.commit()
    await run_prediction_job(
        str(original.job_id), str(original.id), settings=service_settings, session_factory=factory
    )
    async with factory() as s:
        before = (await s.get(PredictionRun, original.id)).output_jsonb
    experiment, run, created = await queue(factory, service_settings, definition(record))
    comparison = await complete(factory, service_settings, run)
    summary = comparison.summary_jsonb
    assert created and summary["counts"]["paired"] == 1
    assert summary["counts"]["predicted"] == summary["counts"]["evaluated"] == 2
    assert summary["interpretation"] == "INSUFFICIENT_SAMPLE"
    assert summary["groups"]["control"]["metrics"]["binary_brier"]["sample_size"] == 12
    assert summary["paired_deltas"]["binary_brier"]["treatment_minus_control"] == 0
    assert summary["groups"]["statistical"]["metrics"]["binary_brier"]["sample_size"] == 12
    assert summary["groups"]["market"]["metrics"]["binary_brier"]["sample_size"] < 12
    async with factory() as s:
        assert (await s.get(PredictionRun, original.id)).output_jsonb == before
        rec = await s.get(MatchContextRecord, record.id)
        assert rec.context_hash == record.context_hash and rec.context_jsonb == record.context_jsonb
        cases = (
            await s.scalars(select(ExperimentCase).where(ExperimentCase.run_id == run.id))
        ).all()
        assert cases[0].control_context_id == cases[0].treatment_context_id == record.id
        predictions = (await s.scalars(select(ExperimentPrediction))).all()
        assert {p.actual_identity_jsonb["context_hash"] for p in predictions} == {
            record.context_hash
        }
        assert {p.actual_identity_jsonb["feature_version"] for p in predictions} == {"features_v1"}
    with TestClient(create_app(service_settings)) as client:
        primary = client.get("/v1/predictions").json()
        assert all(p["id"] not in {str(p.id) for p in predictions} for p in primary)
        assert (
            client.get(f"/v1/experiments/{experiment.id}").json()["runs"][0]["comparison"][
                "counts"
            ]["paired"]
            == 1
        )


async def test_queue_worker_and_comparison_concurrent_idempotency(
    factory, record, service_settings
):
    await with_result(factory, record)
    experiment, run, _ = await queue(factory, service_settings, definition(record))

    async def again():
        async with factory() as s:
            result, created = await request_run(s, experiment, RunRequest(), service_settings)
            await s.commit()
            return result.id, created

    requests = await asyncio.gather(again(), again())
    assert requests == [(run.id, False), (run.id, False)]
    results = await asyncio.gather(
        run_batch(factory, run.id, service_settings), run_batch(factory, run.id, service_settings)
    )
    assert any(r["status"] == "reused" for r in results)
    comparison = await complete(factory, service_settings, run)
    async with factory() as s:
        assert await s.scalar(select(func.count()).select_from(ExperimentCall)) == 2
        assert (await compare_run(s, run.id)).id == comparison.id
        rerun, created = await request_run(
            s, experiment, RunRequest(rerun_key=uuid.uuid4()), service_settings
        )
        assert created and rerun.id != run.id and rerun.manifest_hash == run.manifest_hash
        await s.commit()


@pytest.mark.parametrize("failure", ["timeout", "malformed", "abstain"])
async def test_treatment_failure_keeps_full_control_metrics(
    factory, record, service_settings, failure
):
    await with_result(factory, record)
    ctx = MatchContextV1.model_validate(record.context_jsonb)
    output = valid_output(ctx, record.context_hash)
    if failure == "abstain":
        output.update(abstain=True, abstain_reason="Synthetic abstention", probabilities=None)
    provider = ScriptedProvider(
        [LLMError("timeout")]
        if failure == "timeout"
        else [output]
        if failure == "abstain"
        else [{}, {}]
    )

    def factory_for(spec):
        if "challenger" in spec.model:
            return provider
        from sports_intelligence.providers.llm.mock import MockLLMProvider

        return MockLLMProvider()

    _, run, _ = await queue(factory, service_settings, definition(record))
    summary = (await complete(factory, service_settings, run, factory_for)).summary_jsonb
    assert summary["counts"]["paired"] == 0
    assert summary["groups"]["control"]["metrics"]["binary_brier"]["sample_size"] == 12
    assert summary["groups"]["paired_control"]["metrics"]["binary_brier"]["sample_size"] == 0
    if failure == "abstain":
        assert summary["counts"]["abstained_treatment"] == 1
    else:
        assert summary["counts"]["failed_treatment"] == 1


async def test_transient_retry_counted_and_completed_case_never_called_again(
    factory, record, service_settings
):
    await with_result(factory, record)
    ctx = MatchContextV1.model_validate(record.context_jsonb)
    providers = {}

    def build(spec):
        providers[spec.model] = ScriptedProvider(
            [LLMError("timeout", retryable=True), valid_output(ctx, record.context_hash)]
        )
        return providers[spec.model]

    _, run, _ = await queue(factory, service_settings, definition(record))
    await complete(factory, service_settings, run, build)
    await run_batch(factory, run.id, service_settings, build)
    assert all(len(p.calls) == 2 for p in providers.values())
    async with factory() as s:
        assert await s.scalar(select(func.count()).select_from(ExperimentCall)) == 4


@pytest.mark.parametrize("calls", [0, 1])
async def test_budget_exhaustion_visible(factory, record, service_settings, calls):
    await with_result(factory, record)
    _, run, _ = await queue(factory, service_settings, definition(record, max_llm_calls=calls))
    summary = (await complete(factory, service_settings, run)).summary_jsonb
    assert (
        summary["counts"]["paired"] == 0
        and summary["counts"]["failed_control"] + summary["counts"]["failed_treatment"] >= 1
    )
    assert any("budget_exhausted" in reason for reason in summary["counts"]["reasons"])
    async with factory() as s:
        assert await s.scalar(select(func.count()).select_from(ExperimentCall)) == calls


async def test_missing_result_visible_and_no_fake_measurements(factory, record, service_settings):
    _, run, _ = await queue(factory, service_settings, definition(record))
    summary = (await complete(factory, service_settings, run)).summary_jsonb
    assert summary["counts"]["missing_result"] == 1 and summary["counts"]["paired"] == 0
    assert summary["groups"]["control"]["metrics"]["binary_brier"] == {
        "value": None,
        "sample_size": 0,
    }
    assert summary["groups"]["control"]["metrics"]["forecast_coverage"]["value"] == 1


async def test_missing_context_no_calls_and_explicit_unavailable(factory, record, service_settings):
    d = definition(
        record, control=ArmRequest(phase="PREMATCH"), treatment=ArmRequest(phase="PREMATCH")
    )
    async with factory() as s:
        plan = await plan_replay(s, d)
        assert plan["status"] == "INSUFFICIENT_HISTORICAL_EVIDENCE"
        assert plan["counts"]["requested"] == plan["counts"]["non_replayable"] == 1
    _, run, _ = await queue(factory, service_settings, d)
    summary = (await complete(factory, service_settings, run)).summary_jsonb
    assert summary["counts"]["executed"] == 0 and summary["counts"]["paired"] == 0
    async with factory() as s:
        assert await s.scalar(select(func.count()).select_from(ExperimentCall)) == 0


async def test_later_mutable_rows_and_result_never_enter_prediction_payload(
    factory, record, service_settings
):
    await with_result(factory, record)
    future = record.as_of + timedelta(hours=5)
    async with factory() as s, s.begin():
        fx = await s.get(Fixture, record.fixture_id)
        s.add(
            LineupSnapshot(
                fixture_id=fx.id,
                team_id=fx.home_team_id,
                provider="mock",
                captured_at=future,
                confirmed=True,
                publication_state="CONFIRMED",
                players_jsonb=[{"name": "FORBIDDEN_LATE_LINEUP"}],
                formation="FORBIDDEN",
            )
        )
        s.add(
            OddsSnapshotSet(
                fixture_id=fx.id,
                provider="mock",
                captured_at=future,
                market_whitelist_jsonb=["FORBIDDEN_ODDS"],
            )
        )
        s.add(
            ResearchDocument(
                fixture_id=fx.id,
                url="https://synthetic.invalid/late",
                domain="synthetic.invalid",
                title="FORBIDDEN_RESEARCH",
                retrieved_at=future,
                published_at=future,
                content_hash=uuid.uuid4().hex,
                provider="mock",
                relevance_score=1,
            )
        )
        await s.execute(
            update(Team).where(Team.id == fx.home_team_id).values(name="FORBIDDEN_CURRENT_TEAM")
        )
        await s.execute(
            update(League).where(League.id == fx.league_id).values(name="FORBIDDEN_CURRENT_LEAGUE")
        )
        await s.execute(update(Fixture).where(Fixture.id == fx.id).values(status="FT"))
    ctx = MatchContextV1.model_validate(record.context_jsonb)
    providers = []

    def build(spec):
        provider = ScriptedProvider([valid_output(ctx, record.context_hash)])
        providers.append(provider)
        return provider

    _, run, _ = await queue(factory, service_settings, definition(record))
    await complete(factory, service_settings, run, build)
    for p in providers:
        assert p.calls[0]["context"] == ctx.model_dump(mode="json")
        assert "FORBIDDEN" not in str(p.calls[0]) and "regulation_home" not in str(p.calls[0])


@pytest.mark.parametrize("field", ["odds", "lineup", "research", "feature", "missing_feature"])
async def test_corrupt_or_future_frozen_evidence_not_replayable(factory, record, field):
    async with factory() as s, s.begin():
        rec = await s.get(MatchContextRecord, record.id)
        data = copy.deepcopy(rec.context_jsonb)
        if field == "missing_feature":
            rec.feature_snapshot_id = None
        elif field == "feature":
            data["deterministic_features"]["schema_version"] = "invented"
        else:
            data["source_manifest"]["sources"][field] = {
                "table": "lineup_snapshots",
                "category": field,
                "captured_at": (record.as_of + timedelta(hours=1)).isoformat(),
            }
        ctx = MatchContextV1.model_validate(data)
        rec.context_jsonb = data
        rec.context_hash = hashlib.sha256(ctx.canonical_json().encode()).hexdigest()
    async with factory() as s:
        plan = await plan_replay(s, definition(record))
        assert plan["counts"]["eligible"] == 0 and plan["counts"]["non_replayable"] == 1


@pytest.mark.parametrize(
    "minimum,interpretation", [(1, "MEASURED_ONLY"), (2, "INSUFFICIENT_SAMPLE")]
)
async def test_minimum_uses_fixture_pairs_not_market_rows(
    factory, record, service_settings, minimum, interpretation
):
    await with_result(factory, record)
    _, run, _ = await queue(
        factory, service_settings, definition(record, min_paired_fixtures=minimum)
    )
    summary = (await complete(factory, service_settings, run)).summary_jsonb
    assert summary["interpretation"] == interpretation and summary["counts"]["paired"] == 1


async def test_without_odds_and_prompt_identity_unchanged_on_disk_change(
    factory, record, service_settings, tmp_path
):
    await with_result(factory, record)
    prompt = tmp_path / "1.2.3.txt"
    prompt.write_text(Path(service_settings.prediction_prompt_path).read_text())
    settings = service_settings.model_copy(update={"prediction_prompt_path": str(prompt)})
    _, run, _ = await queue(
        factory,
        settings,
        definition(
            record,
            treatment=ArmRequest(route="prediction_challenger", variant=Variant.WITHOUT_ODDS),
        ),
    )
    prompt.write_text("FORBIDDEN_NEW_PROMPT")
    providers = []
    ctx = MatchContextV1.model_validate(record.context_jsonb)

    def build(spec):
        p = ScriptedProvider(
            [valid_output(ctx, record.context_hash)], actual_model="actual-mock-model"
        )
        providers.append(p)
        return p

    summary = (await complete(factory, settings, run, build)).summary_jsonb
    assert any("masks research" in s for s in summary["limitations"])
    assert any("market_snapshot" not in p.calls[0]["context"] for p in providers)
    async with factory() as s:
        outputs = (await s.scalars(select(ExperimentPrediction))).all()
        assert {p.actual_identity_jsonb["prompt_version"] for p in outputs} == {"1.2.3"}
        assert {p.actual_identity_jsonb["model"] for p in outputs} == {"actual-mock-model"}


async def proposal(factory, record, settings):
    await with_result(factory, record)
    experiment, run, _ = await queue(factory, settings, definition(record))
    comparison = await complete(factory, settings, run)
    async with factory() as s:
        job, created = await request_analysis(s, comparison, settings)
        await s.commit()
    result = await generate_proposal(factory, job.id, settings)
    assert created and result["status"] == "SUCCEEDED"
    async with factory() as s:
        p = await s.get(ImprovementProposal, uuid.UUID(result["proposal_id"]))
    return p, comparison, job, experiment


async def test_analyst_dedup_concurrency_evidence_and_human_lifecycle(
    factory, record, service_settings
):
    p, comparison, job, experiment = await proposal(factory, record, service_settings)
    assert p.sample_size == 1 and p.evidence_jsonb["groups"] == comparison.summary_jsonb["groups"]
    assert p.analyst_jsonb["actual_model"] == "mock-analyst-v1"
    results = await asyncio.gather(
        generate_proposal(factory, job.id, service_settings),
        generate_proposal(factory, job.id, service_settings),
    )
    assert all(r["status"] == "reused" for r in results)
    async with factory() as s:
        duplicate, created = await request_analysis(s, comparison, service_settings)
        assert not created and duplicate.id == job.id
        action = ApproveRequest(actor="synthetic-owner", reason="Authorize research only")
        p = await approve_experiment(s, p, action, service_settings)
        assert p.status == "APPROVED_FOR_EXPERIMENT" and p.experiment_id
        await approve_experiment(s, p, action, service_settings)
        assert await s.scalar(select(func.count()).select_from(ImprovementProposalEvent)) == 1
        assert (
            await s.scalar(select(func.count()).select_from(ExperimentRun)) == 1
        )  # approval queues nothing
        with pytest.raises(ValueError):
            await human_transition(s, p, "PROMOTED", HumanAction(actor="owner", reason="invalid"))
        p = await human_transition(s, p, "REJECTED", HumanAction(actor="owner", reason="reject"))
        assert p.status == "REJECTED"
        await s.commit()


async def test_api_telegram_e2e_and_no_production_file_mutations(
    factory, record, service_settings, monkeypatch
):
    from sports_intelligence.bot.backend_client import BackendClient
    from sports_intelligence.bot.context import AppContext
    from sports_intelligence.bot.experiments import experiment_callback, improvements_command
    from sports_intelligence.workers.tasks.experiments import (
        improvement_analysis_task,
        replay_batch_task,
    )
    from telegram_fakes import FakeTransport, make_callback, make_message

    paths = [Path(service_settings.prediction_prompt_path), Path(service_settings.llm_routes_path)]
    before = [p.read_bytes() for p in paths]
    await with_result(factory, record)
    calls = []
    monkeypatch.setattr(replay_batch_task, "apply_async", lambda **kw: calls.append(kw))
    monkeypatch.setattr(improvement_analysis_task, "apply_async", lambda **kw: calls.append(kw))
    with TestClient(create_app(service_settings)) as client:
        eid = client.post(
            "/v1/experiments", json=definition(record).model_dump(mode="json")
        ).json()["id"]
        first = client.post(f"/v1/experiments/{eid}/run", json={})
        assert first.status_code == 202 and len(calls) == 1
        second = client.post(f"/v1/experiments/{eid}/run", json={})
        assert second.json()["already_queued"] and len(calls) == 1
        async with factory() as s:
            run = await s.get(ExperimentRun, uuid.UUID(first.json()["run_id"]))
        await complete(factory, service_settings, run)
        analysis = client.post(f"/v1/experiments/runs/{run.id}/analyze", json={})
        assert analysis.status_code == 202
        result = await generate_proposal(
            factory, uuid.UUID(analysis.json()["job_id"]), service_settings
        )
        pid = result["proposal_id"]
        transport = FakeTransport()

        def relay(request):
            import json

            r = client.request(
                request.method,
                request.url.path,
                params=dict(request.url.params),
                json=json.loads(request.content) if request.content else None,
            )
            return httpx.Response(r.status_code, json=r.json())

        async with httpx.AsyncClient(transport=httpx.MockTransport(relay)) as http:
            ctx = AppContext(
                transport=transport,
                backend=BackendClient("https://synthetic.invalid", client=http),
                settings=service_settings,
                allowed_user_ids=frozenset({1}),
            )
            await improvements_command(make_message("/improvements"), ctx)
            await experiment_callback(make_callback(f"m9:proposal:{pid}"), ctx)
            await experiment_callback(make_callback(f"m9:approve:{pid}"), ctx)
        assert "Выборка: 1" in transport.sent[0]["text"]
        assert "APPROVED_FOR_EXPERIMENT" in transport.edited[-1]["text"]
        assert (
            client.post(
                f"/v1/improvements/{pid}/reject", json={"actor": "owner", "reason": "Reject"}
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/v1/improvements/{pid}/approve-experiment",
                json={"actor": "owner", "reason": "Invalid"},
            ).status_code
            == 409
        )
        assert client.get(f"/v1/improvements/{pid}").json()["human_actions"]
        assert len(calls) == 2  # replay + analyst, no automatic execution/promotion
    assert [p.read_bytes() for p in paths] == before


async def test_bounded_batches_and_max_fixture_exclusions(factory, record, service_settings):
    second = await frozen_record(factory)
    third = await frozen_record(factory)
    for rec in (record, second, third):
        await with_result(factory, rec)
    data = definition(record, max_fixtures=2, batch_size=1).model_dump(mode="json")
    data["population"]["fixture_ids"] = [str(r.fixture_id) for r in (record, second, third)]
    from sports_intelligence.experiments.contracts import ExperimentDefinition

    _, run, _ = await queue(factory, service_settings, ExperimentDefinition.model_validate(data))
    assert run.counts_jsonb["requested"] == 3 and run.counts_jsonb["eligible"] == 2
    assert run.counts_jsonb["reasons"] == {"max_fixtures": 1}
    first = await run_batch(factory, run.id, service_settings)
    assert first["status"] == "MORE"
    async with factory() as s:
        assert await s.scalar(select(func.count()).select_from(ExperimentCall)) == 2
    summary = (await complete(factory, service_settings, run)).summary_jsonb
    assert summary["counts"]["paired"] == 2 and summary["counts"]["excluded"] == 1


async def test_missing_market_baseline_has_zero_n(factory, service_settings):
    rec = await frozen_record(factory, has_odds=False)
    await with_result(factory, rec)
    _, run, _ = await queue(factory, service_settings, definition(rec))
    summary = (await complete(factory, service_settings, run)).summary_jsonb
    assert summary["groups"]["market"]["metrics"]["binary_brier"] == {
        "value": None,
        "sample_size": 0,
    }
    assert summary["groups"]["market"]["metrics"]["missing_baseline_probabilities"]["value"] == 12


@pytest.mark.parametrize(
    "field,value",
    [
        ("sample_size", 9999),
        ("metrics", {"brier": 0}),
        ("status", "PROMOTED"),
        ("title", "Measured improvement of 99 percent"),
    ],
)
async def test_malformed_analyst_output_rejected_and_facts_protected(
    factory, record, service_settings, monkeypatch, field, value
):
    from dataclasses import replace

    from sports_intelligence.experiments import analyst
    from sports_intelligence.providers.llm.mock import MockLLMProvider

    await with_result(factory, record)
    _, run, _ = await queue(factory, service_settings, definition(record))
    comparison = await complete(factory, service_settings, run)
    async with factory() as s:
        job, _ = await request_analysis(s, comparison, service_settings)
        await s.commit()

    class BadAnalyst(MockLLMProvider):
        async def generate_structured(self, **kwargs):
            result = await super().generate_structured(**kwargs)
            return replace(result, parsed_output={**result.parsed_output, field: value})

    monkeypatch.setattr(analyst, "build_llm_provider", lambda *a, **kw: BadAnalyst())
    result = await generate_proposal(factory, job.id, service_settings)
    assert result["status"] == "FAILED"
    async with factory() as s:
        assert (await s.get(Job, job.id)).status == "FAILED"
        assert await s.scalar(select(func.count()).select_from(ImprovementProposal)) == 0
        assert (
            await s.get(ExperimentComparison, comparison.id)
        ).summary_jsonb == comparison.summary_jsonb


async def test_concurrent_initial_analyst_worker_makes_one_call(
    factory, record, service_settings, monkeypatch
):
    from sports_intelligence.experiments import analyst
    from sports_intelligence.providers.llm.mock import MockLLMProvider

    await with_result(factory, record)
    _, run, _ = await queue(factory, service_settings, definition(record))
    comparison = await complete(factory, service_settings, run)
    async with factory() as s:
        job, _ = await request_analysis(s, comparison, service_settings)
        await s.commit()
    calls = []

    class SlowAnalyst(MockLLMProvider):
        async def generate_structured(self, **kwargs):
            calls.append(kwargs)
            await asyncio.sleep(0.05)
            return await super().generate_structured(**kwargs)

    monkeypatch.setattr(analyst, "build_llm_provider", lambda *a, **kw: SlowAnalyst())
    results = await asyncio.gather(
        generate_proposal(factory, job.id, service_settings),
        generate_proposal(factory, job.id, service_settings),
    )
    assert sorted(r["status"] for r in results) == ["SUCCEEDED", "reused"] and len(calls) == 1
    assert "context" not in calls[0]["payload"]


async def test_analyst_budget_refuses_calls(factory, record, service_settings):
    await with_result(factory, record)
    _, run, _ = await queue(factory, service_settings, definition(record))
    comparison = await complete(factory, service_settings, run)
    async with factory() as s:
        job, _ = await request_analysis(s, comparison, service_settings)
        await s.commit()
    result = await generate_proposal(
        factory, job.id, service_settings.model_copy(update={"improvement_max_calls_per_day": 0})
    )
    assert result["status"] == "FAILED"
    async with factory() as s:
        assert await s.scalar(select(func.count()).select_from(ImprovementProposal)) == 0


async def test_immutable_definitions_manifest_and_comparisons_in_database(
    factory, record, service_settings
):
    from sqlalchemy.exc import IntegrityError

    await with_result(factory, record)
    experiment, run, _ = await queue(factory, service_settings, definition(record))
    comparison = await complete(factory, service_settings, run)
    for model, identity, values in (
        (Experiment, experiment.id, {"name": "FORBIDDEN"}),
        (ExperimentRun, run.id, {"manifest_jsonb": []}),
        (ExperimentComparison, comparison.id, {"summary_jsonb": {}}),
    ):
        async with factory() as s:
            with pytest.raises(IntegrityError, match="immutable M9"):
                await s.execute(update(model).where(model.id == identity).values(**values))
            await s.rollback()


async def test_interrupted_case_claim_requires_inspection_and_never_repeats_call(
    factory, record, service_settings
):
    _, run, _ = await queue(factory, service_settings, definition(record))
    async with factory() as s, s.begin():
        output = await s.scalar(
            select(ExperimentPrediction).join(ExperimentCase).where(ExperimentCase.run_id == run.id)
        )
        output.status = "RUNNING"
    result = await run_batch(factory, run.id, service_settings)
    assert result["status"] == "NEEDS_INSPECTION"
    async with factory() as s:
        assert (
            await s.get(ExperimentRun, run.id)
        ).error_code == "interrupted_case_requires_inspection"
    assert (await run_batch(factory, run.id, service_settings))["status"] == "FAILED"


async def test_phase_comparison_reports_information_difference(factory, record, service_settings):
    # Same fixture, distinct original contexts; add a separately frozen PREMATCH identity.
    from sports_intelligence.db.models import DataQualityReport, FeatureSnapshot

    async with factory() as s, s.begin():
        feature = await s.get(FeatureSnapshot, record.feature_snapshot_id)
        quality = await s.get(DataQualityReport, record.data_quality_report_id)
        f = FeatureSnapshot(
            fixture_id=record.fixture_id,
            forecast_phase="PREMATCH",
            as_of=record.as_of,
            schema_version=feature.schema_version,
            features_jsonb=feature.features_jsonb,
            source_fingerprint=uuid.uuid4().hex,
        )
        q = DataQualityReport(
            fixture_id=record.fixture_id,
            forecast_phase="PREMATCH",
            as_of=record.as_of,
            schema_version=quality.schema_version,
            overall_score=quality.overall_score,
            quality_band=quality.quality_band,
            can_predict=True,
            dimensions_jsonb=quality.dimensions_jsonb,
        )
        s.add_all([f, q])
        await s.flush()
        data = copy.deepcopy(record.context_jsonb)
        data["forecast_phase"] = data["data_quality"]["forecast_phase"] = "PREMATCH"
        ctx = MatchContextV1.model_validate(data)
        s.add(
            MatchContextRecord(
                fixture_id=record.fixture_id,
                forecast_phase="PREMATCH",
                as_of=record.as_of,
                schema_version=record.schema_version,
                context_jsonb=data,
                context_hash=hashlib.sha256(ctx.canonical_json().encode()).hexdigest(),
                feature_snapshot_id=f.id,
                data_quality_report_id=q.id,
            )
        )
    await with_result(factory, record)
    d = definition(record, treatment=ArmRequest(route="prediction_challenger", phase="PREMATCH"))
    _, run, _ = await queue(factory, service_settings, d)
    summary = (await complete(factory, service_settings, run)).summary_jsonb
    assert summary["counts"]["paired"] == 1
    assert any("observational" in x for x in summary["limitations"])


@pytest.mark.parametrize("source", ["historical_primary", "historical_challenger"])
async def test_historical_forecast_arm_reuses_exact_identity_without_new_call(
    factory, record, service_settings, source
):
    from sports_intelligence.predictions.contracts import Role

    await with_result(factory, record)
    role = Role.PRIMARY if source == "historical_primary" else Role.CHALLENGER
    async with factory() as s:
        original, _ = await request_prediction(
            s, record=record, settings=service_settings, role=role
        )
        await s.commit()
    await run_prediction_job(
        str(original.job_id), str(original.id), settings=service_settings, session_factory=factory
    )
    _, run, _ = await queue(
        factory, service_settings, definition(record, control=ArmRequest(source=source))
    )
    summary = (await complete(factory, service_settings, run)).summary_jsonb
    assert summary["counts"]["paired"] == 1
    async with factory() as s:
        assert await s.scalar(select(func.count()).select_from(ExperimentCall)) == 1
        predictions = (await s.scalars(select(ExperimentPrediction))).all()
        historical = next(
            p for p in predictions if p.actual_identity_jsonb.get("historical_prediction_id")
        )
        assert historical.actual_identity_jsonb["historical_prediction_id"] == str(original.id)
        assert historical.actual_identity_jsonb["source"] == source
        assert (await s.get(PredictionRun, original.id)).context_hash == record.context_hash


async def test_missing_historical_forecast_does_not_fabricate_replay(factory, record):
    async with factory() as s:
        plan = await plan_replay(
            s, definition(record, control=ArmRequest(source="historical_challenger"))
        )
    assert plan["status"] == "INSUFFICIENT_HISTORICAL_EVIDENCE"
    assert plan["counts"]["reasons"] == {"missing_historical_prediction": 1}


async def test_cli_keyless_plan_never_enqueues(
    factory, record, service_settings, tmp_path, monkeypatch
):
    import sports_intelligence.replay as cli

    monkeypatch.setattr(cli, "get_settings", lambda: service_settings)
    path = tmp_path / "experiment.json"
    import json

    path.write_text(json.dumps(definition(record).model_dump(mode="json")))
    result = await cli.replay(
        cli.parser().parse_args(["--experiment", str(path), "--execute", "--dry-run", "--mock"])
    )
    assert result["status"] == "READY" and result["estimated_initial_calls"] == 2
    async with factory() as s:
        assert await s.scalar(select(func.count()).select_from(ExperimentRun)) == 0


async def test_real_m2_m8_pipeline_extends_to_m9_keyless_e2e(
    factory, service_settings, tmp_path, monkeypatch, *, include_research=False
):
    from test_m8_e2e import test_m8_full_keyless_result_worker_to_evaluation_api_telegram

    from sports_intelligence.experiments import planner
    from sports_intelligence.workers.tasks.llm import predict_match_task

    enqueued = []
    monkeypatch.setattr(predict_match_task, "apply_async", lambda **kw: enqueued.append(kw))
    from sports_intelligence.db.models import EvaluationRun

    async with factory() as session, session.begin():
        # Match the accepted E2E's isolated test fixtures; no stale test runs to catch up.
        await session.execute(delete(PredictionRun))
        await session.execute(delete(EvaluationRun))
        await session.execute(delete(FixtureResult))
    # Run the accepted genuine collectors/features/prediction/evaluation pipeline, using only mocks.
    await test_m8_full_keyless_result_worker_to_evaluation_api_telegram(
        factory,
        service_settings,
        tmp_path,
        enqueued,
        monkeypatch,
        include_research=include_research,
    )
    async with factory() as s:
        rec = await s.scalar(
            select(MatchContextRecord).order_by(MatchContextRecord.created_at.desc()).limit(1)
        )
        result = await s.scalar(
            select(FixtureResult).where(FixtureResult.fixture_id == rec.fixture_id)
        )
    later = result.observed_at + timedelta(hours=1)

    class LaterClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return later if tz else later.replace(tzinfo=None)

    monkeypatch.setattr(planner, "datetime", LaterClock)
    experiment, run, _ = await queue(factory, service_settings, definition(rec))
    comparison = await complete(factory, service_settings, run)
    assert comparison.summary_jsonb["counts"]["paired"] == 1
    async with factory() as s:
        job, _ = await request_analysis(s, comparison, service_settings)
        await s.commit()
    generated = await generate_proposal(factory, job.id, service_settings)
    assert generated["status"] == "SUCCEEDED"


async def test_approved_experiment_run_and_audit_promotion_never_apply_production(
    factory, record, service_settings
):
    p, _, _, _ = await proposal(factory, record, service_settings)
    async with factory() as s:
        p = await approve_experiment(
            s, p, ApproveRequest(actor="owner", reason="Research only"), service_settings
        )
        experiment = await s.get(Experiment, p.experiment_id)
        run, _ = await request_run(s, experiment, RunRequest(), service_settings)
        assert p.status == "EXPERIMENT_RUNNING"
        await s.commit()
    await complete(factory, service_settings, run)
    before = Path(service_settings.llm_routes_path).read_bytes()
    with TestClient(create_app(service_settings)) as client:
        response = client.post(
            f"/v1/improvements/{p.id}/record-decision",
            json={"actor": "owner", "reason": "Record decision only", "status": "PROMOTED"},
        )
        assert response.status_code == 200 and response.json()["production_applied"] is False
        response = client.post(
            f"/v1/improvements/{p.id}/record-decision",
            json={"actor": "owner", "reason": "Record rollback only", "status": "ROLLED_BACK"},
        )
        assert response.status_code == 200 and response.json()["production_applied"] is False
    assert Path(service_settings.llm_routes_path).read_bytes() == before


@pytest.mark.parametrize("live_opt_in,enabled", [(False, False), (True, False), (False, True)])
async def test_live_routes_require_all_explicit_gates(
    factory, record, service_settings, tmp_path, live_opt_in, enabled
):
    import yaml

    data = yaml.safe_load(Path(service_settings.llm_routes_path).read_text())
    data["routes"]["prediction_challenger"]["primary"]["provider"] = "openai"
    data["routes"]["prediction_challenger"]["primary"]["model"] = "configured-offline-model"
    path = tmp_path / "llm.yaml"
    path.write_text(yaml.safe_dump(data))
    settings = service_settings.model_copy(
        update={"llm_routes_path": str(path), "experiment_live_enabled": enabled}
    )
    async with factory() as s:
        experiment, _ = await create_experiment(s, definition(record), settings)
        with pytest.raises(ValueError, match="live_experiment_not_authorized"):
            await request_run(s, experiment, RunRequest(live_opt_in=live_opt_in), settings)


async def test_exact_context_scope_and_missing_identity_are_visible(
    factory, record, service_settings
):
    from sports_intelligence.experiments.contracts import ExperimentDefinition

    data = definition(record).model_dump(mode="json")
    data["population"]["fixture_ids"] = []
    absent = uuid.uuid4()
    data["population"]["context_ids"] = [str(record.id), str(absent)]
    d = ExperimentDefinition.model_validate(data)
    async with factory() as s:
        plan = await plan_replay(s, d)
    assert plan["counts"]["requested"] == 2 and plan["counts"]["eligible"] == 1
    assert plan["counts"]["reasons"] == {"context_outside_scope_or_missing": 1}
    _, run, _ = await queue(factory, service_settings, d)
    summary = (await complete(factory, service_settings, run)).summary_jsonb
    assert summary["counts"]["non_replayable"] == 1
    assert run.manifest_jsonb[0]["control"]["context_id"] == str(record.id)


async def test_no_requested_historical_period_returns_insufficient_not_fake_replay(
    factory, record, service_settings
):
    from sports_intelligence.experiments.contracts import ExperimentDefinition

    data = definition(record).model_dump(mode="json")
    data["population"].update(
        fixture_ids=[], start="2000-01-01T00:00:00Z", end="2000-01-02T00:00:00Z"
    )
    d = ExperimentDefinition.model_validate(data)
    async with factory() as s:
        plan = await plan_replay(s, d)
    assert plan["status"] == "INSUFFICIENT_HISTORICAL_EVIDENCE" and plan["counts"]["requested"] == 0
    _, run, _ = await queue(factory, service_settings, d)
    summary = (await complete(factory, service_settings, run)).summary_jsonb
    assert summary["counts"]["executed"] == 0 and summary["interpretation"] == "INSUFFICIENT_SAMPLE"


def test_actual_celery_wrappers_use_ids_queues_and_persist_attempts(service_settings, monkeypatch):
    from sports_intelligence.db.models import JobAttempt
    from sports_intelligence.workers.tasks import experiments as tasks

    async def setup():
        engine = create_engine(service_settings.database_url)
        factory = create_session_factory(engine)
        try:
            # Use the isolated factory's M9 cleanup without affecting runtime databases.
            async with factory() as s, s.begin():
                for table in reversed(Base.metadata.sorted_tables):
                    if table.name.startswith("experiment") or table.name.startswith("improvement"):
                        await s.execute(delete(table))
            rec = await frozen_record(factory)
            await with_result(factory, rec)
            experiment, run, _ = await queue(factory, service_settings, definition(rec))
            return experiment.id, run.id, run.job_id
        finally:
            await engine.dispose()

    eid, rid, jid = asyncio.run(setup())
    monkeypatch.setattr(tasks, "get_settings", lambda: service_settings)
    dispatched = []
    monkeypatch.setattr(
        tasks.compare_experiment_task, "apply_async", lambda **kw: dispatched.append(kw)
    )
    result = tasks.replay_batch_task(str(rid))
    assert result["status"] == "EVALUATION_READY"
    assert dispatched == [{"args": [str(rid)], "queue": "evaluation"}]
    assert tasks.compare_experiment_task(str(rid))["comparison_id"]

    async def inspect_and_cleanup():
        engine = create_engine(service_settings.database_url)
        try:
            async with create_session_factory(engine)() as s, s.begin():
                attempts = (
                    await s.scalars(select(JobAttempt).where(JobAttempt.job_id == jid))
                ).all()
                assert len(attempts) == 2 and all(a.status == "SUCCEEDED" for a in attempts)
                for table in reversed(Base.metadata.sorted_tables):
                    if table.name.startswith("experiment") or table.name.startswith("improvement"):
                        await s.execute(delete(table))
        finally:
            await engine.dispose()

    asyncio.run(inspect_and_cleanup())


@pytest.mark.parametrize(
    "timing,known", [("legitimate", True), ("after_kickoff", False), ("before_capture", False)]
)
async def test_closing_proxy_from_explicit_archived_snapshots_stays_out_of_prediction(
    factory, record, service_settings, timing, known
):
    from decimal import Decimal

    from sports_intelligence.db.models import OddsPrice
    from sports_intelligence.evaluation.config import EvaluationConfig

    await with_result(factory, record)
    captured = record.as_of + (
        timedelta(hours=1)
        if timing == "legitimate"
        else timedelta(hours=7)
        if timing == "after_kickoff"
        else -timedelta(hours=1)
    )
    async with factory() as s, s.begin():
        snapshot = OddsSnapshotSet(
            fixture_id=record.fixture_id,
            provider="mock",
            captured_at=captured,
            market_whitelist_jsonb=["ou_15"],
        )
        s.add(snapshot)
        await s.flush()
        s.add(
            OddsPrice(
                snapshot_set_id=snapshot.id,
                bookmaker="synthetic",
                market="ou_15",
                selection="over",
                line=Decimal("1.5"),
                decimal_odds=Decimal("1.3"),
                implied_probability=Decimal("0.769230769"),
            )
        )
    ctx = MatchContextV1.model_validate(record.context_jsonb)
    providers = []

    def build(spec):
        p = ScriptedProvider([valid_output(ctx, record.context_hash)])
        providers.append(p)
        return p

    _, run, _ = await queue(
        factory,
        service_settings,
        definition(record, evaluation=EvaluationConfig(closing_snapshot_ids=(snapshot.id,))),
    )
    summary = (await complete(factory, service_settings, run, build)).summary_jsonb
    metric = summary["groups"]["control"]["metrics"]["closing_line_price_proxy"]
    if known:
        assert metric["sample_size"] == 1 and metric["value"] == pytest.approx(1.5 / 1.3 - 1)
    else:
        assert metric == {"value": None, "sample_size": 0}
    assert str(snapshot.id) in summary["closing_snapshot_ids"]
    for p in providers:
        assert (
            p.calls[0]["context"]["market_snapshot"]
            == ctx.model_dump(mode="json")["market_snapshot"]
        )
        assert str(snapshot.id) not in str(p.calls[0])


async def test_full_length_valid_abstention_reason_is_preserved(factory, record, service_settings):
    await with_result(factory, record)
    context = MatchContextV1.model_validate(record.context_jsonb)
    text = "Synthetic missing evidence. " * 12
    output = valid_output(context, record.context_hash)
    output.update(abstain=True, abstain_reason=text, probabilities=None)
    providers = []

    def build(spec):
        p = ScriptedProvider([output])
        providers.append(p)
        return p

    _, run, _ = await queue(factory, service_settings, definition(record))
    summary = (await complete(factory, service_settings, run, build)).summary_jsonb
    assert summary["counts"]["abstained_control"] == summary["counts"]["abstained_treatment"] == 1
    async with factory() as s:
        predictions = (await s.scalars(select(ExperimentPrediction))).all()
        assert all(
            p.status == "ABSTAINED" and p.output_jsonb["abstain_reason"] == text
            for p in predictions
        )
        assert all(p.reason == "model_abstention" for p in predictions)
