"""M8 acceptance on isolated Docker Postgres/Redis; all data is synthetic."""

from __future__ import annotations

import asyncio
import copy
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import test_m7_predictions as m7
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import delete, func, select

from sports_intelligence.api.app import create_app
from sports_intelligence.collectors.locks import CoalesceLockManager
from sports_intelligence.collectors.quota import QuotaManager
from sports_intelligence.db.models import (
    CandidateSettlement,
    EvaluationMetric,
    EvaluationRun,
    ExternalApiRequest,
    FixtureResult,
    Job,
    LineupSnapshot,
    MarketPrediction,
    MatchContextRecord,
    OddsSnapshotSet,
    PredictionRun,
    PredictionSettlement,
    ProbabilityBaseline,
    ProviderEntityId,
    RankedCandidate,
)
from sports_intelligence.evaluation.config import EvaluationConfig, EvaluationFilters
from sports_intelligence.evaluation.results import collect_date, persist_result, settle_result
from sports_intelligence.evaluation.service import request_evaluation
from sports_intelligence.evaluation.settlement import ResultObservation, ResultStatus
from sports_intelligence.providers.errors import ProviderResponseError, ProviderTimeoutError
from sports_intelligence.providers.sports.mock import MockSportsDataProvider
from sports_intelligence.workers.tasks.evaluation import (
    enqueue_result_date,
    evaluate_task,
    result_date_task,
    run_evaluation_job,
)

factory = m7.factory
record = m7.record
request = m7.request
execute = m7.execute
enqueued = m7.enqueued

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="test services required"),
]


@pytest.fixture(autouse=True)
async def clear_evaluation(factory):
    async with factory() as s:
        await s.execute(delete(EvaluationRun))
        await s.execute(delete(FixtureResult))
        await s.execute(delete(Job).where(Job.job_type.in_(["results", "evaluate"])))
        await s.commit()


async def result_and_settle(factory, record, h=2, a=1, status=ResultStatus.FINAL, observed=None):
    observation = ResultObservation(
        provider_fixture_id=42,
        provider_status="FT",
        status=status,
        regulation_home=h,
        regulation_away=a,
        observed_at=observed or datetime.now(UTC),
    )
    async with factory() as s, s.begin():
        result, fresh = await persist_result(s, record.fixture_id, "mock", observation)
        count = await settle_result(s, result.id)
    return result, fresh, count


async def evaluate(factory, settings, filters=None, config=None, cutoff=None):
    async with factory() as s:
        run, fresh = await request_evaluation(
            s,
            config=config or EvaluationConfig(),
            filters=filters or EvaluationFilters(),
            cutoff=cutoff or datetime.now(UTC),
        )
        await s.commit()
    await run_evaluation_job(str(run.job_id), str(run.id), settings=settings, factory=factory)
    async with factory() as s:
        metrics = list(
            (
                await s.scalars(
                    select(EvaluationMetric).where(EvaluationMetric.evaluation_run_id == run.id)
                )
            ).all()
        )
        persisted = await s.get(EvaluationRun, run.id)
    return persisted, metrics, fresh


def summary(metrics, **dimensions):
    dims = {"role": "PRIMARY", "variant": "LLM_WITH_ODDS", "baseline": "llm", **dimensions}
    return {
        m.metric_name: (m.metric_value, m.sample_size)
        for m in metrics
        if m.dimensions_jsonb == dims
    }


async def test_all_probabilities_and_displayed_candidates_independently_evaluated(
    factory, record, service_settings
):
    run, _ = await request(factory, record, service_settings)
    _, detail = await execute(factory, run, service_settings)
    result, fresh, count = await result_and_settle(factory, record)
    assert fresh and count == 12
    async with factory() as s, s.begin():
        assert await settle_result(s, result.id) == 0
        assert await s.scalar(select(func.count()).select_from(PredictionSettlement)) == 12
        cs = list((await s.scalars(select(CandidateSettlement))).all())
        assert len(cs) == sum(c.displayed for c in detail.candidates)
    er, metrics, _ = await evaluate(factory, service_settings)
    values = summary(metrics)
    assert er.sample_size == 12 and values["binary_brier"][1] == 12
    assert values["multiclass_1x2_brier_sum"][1] == 1
    assert values["displayed_candidates"][0] == len(cs)
    assert values["forecast_coverage"] == (1, 1)
    assert values["mean_input_tokens"] == (None, 0)  # Mock does not report usage.
    assert er.config_jsonb["epsilon"] == 1e-15
    assert str(run.id) in er.source_manifest_jsonb["prediction_runs"]
    assert summary(metrics, baseline="market")["binary_brier"][1] > 0
    assert summary(metrics, baseline="statistical")["binary_brier"][1] == 12


async def test_result_correction_and_retries_preserve_history(factory, record, service_settings):
    run, _ = await request(factory, record, service_settings)
    await execute(factory, run, service_settings)
    first, _, count = await result_and_settle(factory, record, 1, 0)
    assert count == 12
    before, old_metrics, _ = await evaluate(factory, service_settings)
    duplicate, fresh, count = await result_and_settle(factory, record, 1, 0)
    assert not fresh and count == 0 and duplicate.id == first.id
    second, _, count = await result_and_settle(factory, record, 0, 1)
    assert second.version == 2 and second.supersedes_id == first.id and count == 12
    third, _, count = await result_and_settle(factory, record, 1, 0)
    assert third.version == 3 and count == 12  # A→B→A remains auditable.
    er, new_metrics, _ = await evaluate(factory, service_settings)
    assert er.source_manifest_jsonb["fixture_results"] == [str(third.id)]
    replay, replay_metrics, fresh = await evaluate(
        factory, service_settings, cutoff=before.source_cutoff
    )
    assert not fresh and replay.id == before.id
    assert [(m.id, m.metric_value) for m in replay_metrics] == [
        (m.id, m.metric_value) for m in old_metrics
    ]
    assert summary(new_metrics)["binary_brier"] == summary(old_metrics)["binary_brier"]
    async with factory() as s:
        assert await s.scalar(select(func.count()).select_from(PredictionSettlement)) == 36


async def test_concurrent_result_persistence_and_settlement_no_duplicates(
    factory, record, service_settings
):
    run, _ = await request(factory, record, service_settings)
    await execute(factory, run, service_settings)
    observation = ResultObservation(
        provider_fixture_id=42,
        provider_status="FT",
        status="FINAL",
        regulation_home=0,
        regulation_away=0,
        observed_at=datetime.now(UTC),
    )

    async def one():
        async with factory() as s, s.begin():
            r, _ = await persist_result(s, record.fixture_id, "mock", observation)
            n = await settle_result(s, r.id)
            return r.id, n

    rows = await asyncio.gather(*[one() for _ in range(4)])
    assert len({r for r, _ in rows}) == 1 and sum(n for _, n in rows) == 12


async def test_roles_variants_and_missing_baselines_separate(factory, record, service_settings):
    for role, variant in [
        ("PRIMARY", "LLM_WITH_ODDS"),
        ("CHALLENGER", "LLM_WITH_ODDS"),
        ("PRIMARY", "LLM_WITHOUT_ODDS"),
        ("CHALLENGER", "LLM_WITHOUT_ODDS"),
    ]:
        from sports_intelligence.predictions.contracts import Role, Variant

        run, _ = await request(
            factory, record, service_settings, role=Role(role), variant=Variant(variant)
        )
        await execute(factory, run, service_settings)
    await result_and_settle(factory, record)
    er, metrics, _ = await evaluate(factory, service_settings)
    for role in ("PRIMARY", "CHALLENGER"):
        for variant in ("LLM_WITH_ODDS", "LLM_WITHOUT_ODDS"):
            assert summary(metrics, role=role, variant=variant)["binary_brier"][1] == 12
    assert er.sample_size == 48
    async with factory() as s, s.begin():
        baseline = await s.scalar(
            select(ProbabilityBaseline).where(ProbabilityBaseline.name == "statistical").limit(1)
        )
        baseline.probabilities_jsonb = {
            "HOME": 0.5
        }  # Deliberately missing historical probabilities.
    _, metrics, _ = await evaluate(factory, service_settings)
    assert (
        sum(
            m.sample_size
            for m in metrics
            if len(m.dimensions_jsonb) == 3
            and m.dimensions_jsonb["baseline"] == "statistical"
            and m.metric_name == "binary_brier"
        )
        == 37
    )


async def test_no_bet_abstain_failure_and_empty_results(factory, record, service_settings):
    from m7_fakes import ScriptedProvider, valid_output
    from sports_intelligence.context.models import MatchContextV1

    run, _ = await request(factory, record, service_settings)
    await execute(factory, run, service_settings)
    # NO_BET: no display candidates, but all twelve probabilities retained.
    async with factory() as s, s.begin():
        r = await s.get(PredictionRun, run.id)
        r.outcome = "NO_BET"
        for c in (await s.scalars(select(RankedCandidate))).all():
            c.displayed = False
    ctx = MatchContextV1.model_validate(record.context_jsonb)
    abstaining = valid_output(ctx, record.context_hash)
    abstaining.update(
        abstain=True, abstain_reason="synthetic insufficient data", probabilities=None
    )
    abstain, _ = await request(factory, record, service_settings, rerun_key=str(uuid.uuid4()))
    await execute(factory, abstain, service_settings, ScriptedProvider([abstaining]))
    failed, _ = await request(factory, record, service_settings, rerun_key=str(uuid.uuid4()))
    async with factory() as s, s.begin():
        r = await s.get(PredictionRun, failed.id)
        r.status, r.completed_at = "FAILED", datetime.now(UTC)
    await result_and_settle(factory, record)
    _, metrics, _ = await evaluate(factory, service_settings)
    v = summary(metrics)
    assert v["binary_brier"][1] == 12
    assert v["forecast_coverage"] == (0.5, 2)
    assert v["abstention_rate"] == (0.5, 2)
    assert v["failed_prediction_runs"] == (1, 1)
    assert v["displayed_candidates"] == (0, 0)
    async with factory() as s:
        assert await s.scalar(select(func.count()).select_from(MarketPrediction)) == 12


async def test_future_data_and_results_never_mutate_m7(factory, record, service_settings):
    run, _ = await request(factory, record, service_settings)
    _, detail = await execute(factory, run, service_settings)
    original_context = copy.deepcopy(record.context_jsonb)
    async with factory() as s, s.begin():
        s.add(
            OddsSnapshotSet(
                fixture_id=record.fixture_id,
                provider="future",
                captured_at=record.as_of + timedelta(hours=5),
                market_whitelist_jsonb=["h2h_1x2"],
            )
        )
        s.add(
            LineupSnapshot(
                fixture_id=record.fixture_id,
                team_id=uuid.UUID(record.context_jsonb["fixture_identity"]["home_team_id"]),
                provider="future",
                captured_at=record.as_of + timedelta(hours=5),
                confirmed=True,
                players_jsonb=[{"forbidden": True}],
                publication_state="CONFIRMED",
            )
        )
    cutoff = datetime.now(UTC)
    await result_and_settle(factory, record)
    _, prior_metrics, _ = await evaluate(factory, service_settings, cutoff=cutoff)
    assert summary(prior_metrics)["binary_brier"][1] == 0
    await evaluate(factory, service_settings)
    from sports_intelligence.predictions.service import read_prediction

    async with factory() as s:
        assert (await s.get(MatchContextRecord, record.id)).context_jsonb == original_context
        assert (await s.get(MatchContextRecord, record.id)).context_hash == record.context_hash
        from sports_intelligence.schemas.predictions import PredictionDetail

        assert PredictionDetail.model_validate(await read_prediction(s, run.id)) == detail


async def test_evaluation_config_identity_api_and_worker_retry(
    factory, record, service_settings, monkeypatch
):
    run, _ = await request(factory, record, service_settings)
    await execute(factory, run, service_settings)
    await result_and_settle(factory, record)
    cutoff = datetime.now(UTC)
    first, _, fresh = await evaluate(factory, service_settings, cutoff=cutoff)
    second, _, fresh2 = await evaluate(factory, service_settings, cutoff=cutoff)
    third, _, _ = await evaluate(
        factory, service_settings, cutoff=cutoff, config=EvaluationConfig(epsilon=1e-6)
    )
    assert fresh and not fresh2 and first.id == second.id != third.id
    queued = []
    monkeypatch.setattr(evaluate_task, "apply_async", lambda **kw: queued.append(kw))
    with TestClient(create_app(service_settings)) as client:
        response = client.get("/v1/evaluations/summary?period=all")
        assert response.status_code == 200
        payload = response.json()
        assert len(payload["groups"]) == 1 and payload["groups"][0]["sample_size"] == 12
        assert client.get("/v1/evaluations/summary?period=all&group_by=market").json()["groups"]
        assert (
            client.get("/v1/evaluations/summary?period=all&market=1x2").json()["groups"][0][
                "sample_size"
            ]
            == 3
        )
        assert client.get("/v1/results").json()
        assert (
            client.get(f"/v1/results/{record.fixture_id}").json()["latest"]["provider_fixture_id"]
            == "42"
        )
        assert len(client.get(f"/v1/results/{record.fixture_id}/settlements").json()) == 12
        assert client.get("/v1/results?limit=1000").status_code == 422
        assert client.get("/v1/evaluations/summary?role=bad").status_code == 422
        assert (
            client.post("/v1/jobs/evaluate", json={"cutoff": "2099-01-01T00:00:00Z"}).status_code
            == 422
        )
        body = {"cutoff": cutoff.isoformat(), "period": "all"}
        a = client.post("/v1/jobs/evaluate", json=body)
        b = client.post("/v1/jobs/evaluate", json=body)
        assert a.status_code == b.status_code == 202
        assert a.json()["evaluation_id"] == b.json()["evaluation_id"]
    assert len(queued) == 1


async def test_batch_collection_quota_raw_provenance_retry_cache_and_mapping(
    factory, record, service_settings, monkeypatch
):
    run, _ = await request(factory, record, service_settings)
    await execute(factory, run, service_settings)
    service_settings = service_settings.model_copy(
        update={"sports_provider": "mock_m8_" + uuid.uuid4().hex[:8]}
    )
    async with factory() as s, s.begin():
        s.add(
            ProviderEntityId(
                provider=service_settings.sports_provider,
                entity_type="fixture",
                external_id="42",
                internal_entity_id=record.fixture_id,
            )
        )
    day = record.as_of.date()
    payload = {
        "response": [
            {
                "fixture": {"id": 42, "status": {"short": "FT"}},
                "score": {"fulltime": {"home": 2, "away": 1}},
            }
        ]
    }
    provider = MockSportsDataProvider(
        responses={day.isoformat(): payload}, provider_name=service_settings.sports_provider
    )
    original = provider.get_results_by_date
    calls = []

    async def failing_once(d):
        calls.append(d)
        if len(calls) == 1:
            raise ProviderTimeoutError("synthetic timeout")
        return await original(d)

    provider.get_results_by_date = failing_once

    async def no_sleep(_):
        pass

    monkeypatch.setattr("sports_intelligence.evaluation.results.asyncio.sleep", no_sleep)
    redis = Redis.from_url(service_settings.redis_url)
    try:
        await redis.flushdb()
        kwargs = dict(
            factory=factory,
            provider=provider,
            quota=QuotaManager(service_settings, factory, redis),
            locks=CoalesceLockManager(redis, service_settings),
            settings=service_settings,
            day=day,
        )
        first = await collect_date(**kwargs)
        assert first == {"observed": 1, "created": 1, "settled": 12} and len(calls) == 2
        assert (await collect_date(**kwargs))["created"] == 0 and len(calls) == 2
        async with factory() as s:
            result = await s.scalar(select(FixtureResult))
            assert (
                result.raw_payload_id
                and result.provider == service_settings.sports_provider
                and result.provider_fixture_id == "42"
            )
            ledger = list(
                (
                    await s.scalars(
                        select(ExternalApiRequest).where(
                            ExternalApiRequest.endpoint_category == "results"
                        )
                    )
                ).all()
            )
            assert len(ledger) >= 2 and any(
                row.error_class == "ProviderTimeoutError" for row in ledger
            )
    finally:
        await redis.aclose()


async def test_invalid_provider_contract_does_not_settle(factory, record, service_settings):
    service_settings = service_settings.model_copy(
        update={"sports_provider": "mock_m8_" + uuid.uuid4().hex[:8]}
    )
    async with factory() as s, s.begin():
        s.add(
            ProviderEntityId(
                provider=service_settings.sports_provider,
                entity_type="fixture",
                external_id="42",
                internal_entity_id=record.fixture_id,
            )
        )
    day = record.as_of.date()
    provider = MockSportsDataProvider(
        provider_name=service_settings.sports_provider,
        responses={
            day.isoformat(): {
                "response": [
                    {
                        "fixture": {"id": 42, "status": {"short": "FT"}},
                        "score": {"fulltime": {"home": -1, "away": 0}},
                    }
                ]
            }
        },
    )
    redis = Redis.from_url(service_settings.redis_url)
    try:
        await redis.flushdb()
        with pytest.raises(ProviderResponseError):
            await collect_date(
                factory=factory,
                provider=provider,
                quota=QuotaManager(service_settings, factory, redis),
                locks=CoalesceLockManager(redis, service_settings),
                settings=service_settings,
                day=day,
            )
        async with factory() as s:
            assert await s.scalar(select(func.count()).select_from(FixtureResult)) == 0
            assert await s.scalar(select(func.count()).select_from(PredictionSettlement)) == 0
    finally:
        await redis.aclose()


async def test_scheduler_same_slot_deduplicates_job(factory, service_settings, monkeypatch):
    calls = []
    monkeypatch.setattr(result_date_task, "apply_async", lambda **kw: calls.append(kw))
    now = datetime.now(UTC)
    a = await enqueue_result_date(factory, service_settings, now.date(), now=now)
    b = await enqueue_result_date(factory, service_settings, now.date(), now=now)
    assert a and not b and len(calls) == 1
    assert set(calls[0]["kwargs"]) == {"job_id", "day_iso", "provider_name", "force"}


async def test_explicit_closing_snapshot_proxy_uses_same_book_and_no_future(
    factory, record, service_settings
):
    from sports_intelligence.db.models import OddsPrice

    run, _ = await request(factory, record, service_settings)
    await execute(factory, run, service_settings)
    async with factory() as s, s.begin():
        candidate = await s.scalar(
            select(RankedCandidate).where(RankedCandidate.displayed.is_(True)).limit(1)
        )
        prediction = await s.get(MarketPrediction, candidate.market_prediction_id)
        # This synthetic fixture displays a supported 1X2 or totals price.
        from sports_intelligence.predictions.contracts import Selection

        mapping = {
            "HOME": ("h2h_1x2", "home"),
            "DRAW": ("h2h_1x2", "draw"),
            "AWAY": ("h2h_1x2", "away"),
            "OVER_1_5": ("ou_15", "over"),
            "UNDER_1_5": ("ou_15", "under"),
        }
        if prediction.selection not in mapping:
            candidate.displayed = False
            candidate = await s.scalar(
                select(RankedCandidate)
                .join(MarketPrediction, MarketPrediction.id == RankedCandidate.market_prediction_id)
                .where(MarketPrediction.selection == Selection.HOME.value)
            )
            candidate.displayed = True
            prediction = await s.get(MarketPrediction, candidate.market_prediction_id)
        market, selection = mapping[prediction.selection]
        snapshot = OddsSnapshotSet(
            fixture_id=record.fixture_id,
            provider="synthetic-closing",
            captured_at=record.as_of + timedelta(hours=5),
            market_whitelist_jsonb=[market],
        )
        s.add(snapshot)
        await s.flush()
        s.add(
            OddsPrice(
                snapshot_set_id=snapshot.id,
                bookmaker=candidate.bookmaker,
                market=market,
                selection=selection,
                decimal_odds=2.0,
                implied_probability=0.5,
            )
        )
        expected = candidate.captured_odds / 2 - 1
    await result_and_settle(factory, record)
    _, missing, _ = await evaluate(factory, service_settings)
    assert summary(missing)["closing_line_price_proxy"] == (None, 0)
    _, with_closing, _ = await evaluate(
        factory, service_settings, config=EvaluationConfig(closing_snapshot_ids=(snapshot.id,))
    )
    value, n = summary(with_closing)["closing_line_price_proxy"]
    assert n == 1 and value == pytest.approx(expected)


async def test_combined_filters_use_persisted_scoped_evaluation(factory, record, service_settings):
    run, _ = await request(factory, record, service_settings)
    await execute(factory, run, service_settings)
    await result_and_settle(factory, record)
    league = uuid.UUID(record.context_jsonb["fixture_identity"]["league_id"])
    er, metrics, _ = await evaluate(
        factory, service_settings, filters=EvaluationFilters(league=league, market="1x2")
    )
    assert summary(metrics)["binary_brier"][1] == 3
    # No misleading run-level coverage when a market-specific denominator is unavailable.
    assert "forecast_coverage" not in summary(metrics)
    with TestClient(create_app(service_settings)) as client:
        response = client.get(f"/v1/evaluations/summary?period=all&league={league}&market=1x2")
        assert response.status_code == 200 and response.json()["groups"][0]["sample_size"] == 3
        assert response.json()["evaluation_id"] == str(er.id)


async def test_empty_evaluation_and_result_absence(factory, service_settings):
    er, metrics, _ = await evaluate(factory, service_settings)
    assert er.sample_size == 0 and not metrics and er.status == "SUCCEEDED"
    with TestClient(create_app(service_settings)) as client:
        assert client.get(f"/v1/results/{uuid.uuid4()}").status_code == 404
        assert client.get("/v1/results?start=2026-01-01T00:00:00").status_code == 422


async def test_result_worker_failed_contract_audits_job_and_attempt(
    factory, record, service_settings, monkeypatch
):
    from sports_intelligence.db.models import JobAttempt
    from sports_intelligence.pipelines.discover_fixtures import create_or_get_job
    from sports_intelligence.workers.tasks.evaluation import run_result_job

    provider_name = "mock_m8_" + uuid.uuid4().hex[:8]
    settings = service_settings.model_copy(update={"sports_provider": provider_name})
    day = record.as_of.date()
    async with factory() as s:
        s.add(
            ProviderEntityId(
                provider=provider_name,
                entity_type="fixture",
                external_id="42",
                internal_entity_id=record.fixture_id,
            )
        )
        job, _ = await create_or_get_job(
            s, "results", "m8-error-" + uuid.uuid4().hex, datetime.now(UTC)
        )
        await s.commit()
    provider = MockSportsDataProvider(
        responses={
            day.isoformat(): {
                "response": [
                    {
                        "fixture": {"id": 42, "status": {"short": "FT"}},
                        "score": {"fulltime": {"home": -1, "away": 0}},
                    }
                ]
            }
        },
        provider_name=provider_name,
    )
    redis = Redis.from_url(settings.redis_url)
    try:
        await redis.flushdb()
        with pytest.raises(ProviderResponseError):
            await run_result_job(
                str(job.id),
                day.isoformat(),
                provider_name,
                settings=settings,
                factory=factory,
                provider=provider,
                redis=redis,
            )
        async with factory() as s:
            assert (await s.get(Job, job.id)).status == "FAILED"
            attempt = await s.scalar(select(JobAttempt).where(JobAttempt.job_id == job.id))
            assert (
                attempt.error_class == "ProviderResponseError"
                and attempt.error_message_redacted is None
            )
            assert await s.scalar(select(func.count()).select_from(PredictionSettlement)) == 0
    finally:
        await redis.aclose()


async def test_display_coverage_counts_unsettled_candidates_before_results(
    factory, record, service_settings
):
    run, _ = await request(factory, record, service_settings)
    _, detail = await execute(factory, run, service_settings)
    _, metrics, _ = await evaluate(factory, service_settings)
    values = summary(metrics)
    assert values["binary_brier"] == (None, 0)
    assert values["displayed_candidates"][0] == sum(c.displayed for c in detail.candidates)
    assert values["candidate_display_coverage"] == (1, 1)
    assert values["candidate_hit_rate"] == (None, 0)
    assert values["research_roi_fixed_unit"] == (None, 0)
