"""M7 acceptance with dedicated Postgres/Redis; all forecasts explicitly synthetic."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update

from m7_fakes import ScriptedProvider, make_context, valid_output
from sports_intelligence.api.app import create_app
from sports_intelligence.context.models import MatchContextV1
from sports_intelligence.db.models import (
    Fixture,
    Job,
    JobAttempt,
    League,
    LineupSnapshot,
    MatchContextRecord,
    ModelConfig,
    OddsSnapshotSet,
    PredictionRun,
    PromptVersion,
    Team,
)
from sports_intelligence.db.session import create_engine, create_session_factory
from sports_intelligence.predictions.contracts import Role, Selection, Variant
from sports_intelligence.predictions.service import (
    automatic_prediction,
    enqueue_prediction,
    read_prediction,
    request_prediction,
)
from sports_intelligence.providers.llm.base import LLMError
from sports_intelligence.schemas.predictions import PredictionDetail
from sports_intelligence.workers.tasks.llm import predict_match_task, run_prediction_job

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (os.environ.get("TEST_DATABASE_URL") and os.environ.get("TEST_REDIS_URL")),
        reason="test services required",
    ),
]


@pytest.fixture
async def factory(service_settings):
    engine = create_engine(service_settings.database_url)
    sf = create_session_factory(engine)

    async def clean():
        async with sf() as session:
            await session.execute(delete(PredictionRun))
            await session.execute(delete(ModelConfig))
            await session.execute(delete(PromptVersion))
            await session.execute(delete(Job).where(Job.job_type == "prediction"))
            await session.commit()

    await clean()
    try:
        yield sf
    finally:
        await clean()
        await engine.dispose()


@pytest.fixture
async def record(factory):
    context = make_context()
    as_of = datetime.fromisoformat(context.as_of)
    async with factory() as session:
        league = League(slug="m7-" + uuid.uuid4().hex[:12], name="Synthetic M7", enabled=True)
        home, away = Team(name="Synthetic Home"), Team(name="Synthetic Away")
        session.add_all([league, home, away])
        await session.flush()
        fixture = Fixture(
            league_id=league.id,
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=as_of + timedelta(hours=6),
            status="NS",
        )
        session.add(fixture)
        await session.flush()
        odds = OddsSnapshotSet(
            fixture_id=fixture.id,
            provider="mock",
            captured_at=as_of,
            market_whitelist_jsonb=["h2h", "ou_15"],
        )
        session.add(odds)
        await session.flush()
        data = context.model_dump()
        data["fixture_id"] = data["fixture_identity"]["fixture_id"] = str(fixture.id)
        data["fixture_identity"].update(
            league_id=str(league.id), home_team_id=str(home.id), away_team_id=str(away.id)
        )
        data["source_manifest"]["sources"]["odds"] = {
            "category": "odds",
            "table": "odds_snapshot_sets",
            "snapshot_id": str(odds.id),
            "provider": "mock",
            "captured_at": as_of.isoformat(),
        }
        data["data_quality"]["source_manifest"] = data["source_manifest"]
        context = MatchContextV1.model_validate(data)
        rec = MatchContextRecord(
            fixture_id=fixture.id,
            forecast_phase="MORNING",
            as_of=as_of,
            schema_version="match_context_v1",
            context_jsonb=context.model_dump(),
            context_hash=hashlib.sha256(context.canonical_json().encode()).hexdigest(),
        )
        session.add(rec)
        await session.commit()
        return rec


@pytest.fixture
def enqueued(monkeypatch):
    calls = []
    monkeypatch.setattr(predict_match_task, "apply_async", lambda **kw: calls.append(kw))
    return calls


async def request(factory, record, settings, **kwargs):
    async with factory() as session:
        run, created = await request_prediction(session, record=record, settings=settings, **kwargs)
        await session.commit()
        return run, created


async def execute(factory, run, settings, provider=None):
    result = await run_prediction_job(
        str(run.job_id),
        str(run.id),
        settings=settings,
        session_factory=factory,
        provider_factory=(lambda _: provider) if provider else None,
    )
    async with factory() as session:
        detail = await read_prediction(session, run.id)
    return result, PredictionDetail.model_validate(detail)


async def test_complete_probability_persistence_identity_and_odds_boundary(
    factory, record, service_settings
):
    run, created = await request(factory, record, service_settings)
    result, detail = await execute(factory, run, service_settings)
    assert created and result["status"] == "SUCCEEDED"
    assert detail.context_hash == record.context_hash and detail.match_context_id == record.id
    assert len(detail.probabilities) == len(detail.candidates) == 12
    assert {p.selection for p in detail.probabilities} == set(Selection)
    assert detail.prompt_hash and detail.model_config_hash and detail.semantic_identity
    assert detail.actual_provider == "mock" and detail.actual_model == "mock-v1"
    assert all(c.odds_captured_at == record.as_of for c in detail.candidates)
    assert all(
        c.odds_snapshot_set_id
        == uuid.UUID(record.context_jsonb["source_manifest"]["sources"]["odds"]["snapshot_id"])
        for c in detail.candidates
    )
    assert {b["name"] for b in detail.baselines} == {"market", "statistical"}
    async with factory() as session:
        assert (await session.get(Job, run.job_id)).status == "SUCCEEDED"
        assert (
            await session.scalar(
                select(func.count()).select_from(JobAttempt).where(JobAttempt.job_id == run.job_id)
            )
            == 1
        )
        assert (
            await session.get(MatchContextRecord, record.id)
        ).context_hash == record.context_hash


async def test_duplicate_semantic_requests_and_concurrent_workers_single_call(
    factory, record, service_settings
):
    run, created = await request(factory, record, service_settings)
    other, created2 = await request(factory, record, service_settings)
    assert created and not created2 and run.id == other.id
    ctx = MatchContextV1.model_validate(record.context_jsonb)
    provider = ScriptedProvider([valid_output(ctx, record.context_hash)])
    results = await asyncio.gather(
        *[
            run_prediction_job(
                str(run.job_id),
                str(run.id),
                settings=service_settings,
                session_factory=factory,
                provider_factory=lambda _: provider,
            )
            for _ in range(3)
        ]
    )
    assert len(provider.calls) == 1 and sum(r["status"] == "reused" for r in results) == 2


async def test_concurrent_enqueue_produces_one_run_and_job(
    factory, record, service_settings, enqueued
):
    async def enqueue():
        async with factory() as session:
            run, created = await request_prediction(
                session, record=record, settings=service_settings
            )
            await enqueue_prediction(session, run, created)
            return run.id

    ids = await asyncio.gather(*[enqueue() for _ in range(5)])
    assert len(set(ids)) == 1 and len(enqueued) == 1


async def test_manual_rerun_preserves_old_run_and_duplicate_token_reuses(
    factory, record, service_settings
):
    original, _ = await request(factory, record, service_settings)
    _, first = await execute(factory, original, service_settings)
    token = str(uuid.uuid4())
    rerun, created = await request(factory, record, service_settings, rerun_key=token)
    repeated, duplicate = await request(factory, record, service_settings, rerun_key=token)
    _, second = await execute(factory, rerun, service_settings)
    assert created and not duplicate and rerun.id == repeated.id != original.id
    assert first.semantic_identity == second.semantic_identity
    async with factory() as session:
        old = await read_prediction(session, original.id)
    assert PredictionDetail.model_validate(old) == first


@pytest.mark.parametrize("role", [Role.PRIMARY, Role.CHALLENGER])
@pytest.mark.parametrize("variant", [Variant.WITH_ODDS, Variant.WITHOUT_ODDS])
async def test_primary_challenger_variants_coexist(
    factory, record, service_settings, role, variant
):
    primary, _ = await request(factory, record, service_settings)
    alternate, _ = await request(factory, record, service_settings, role=role, variant=variant)
    if role != Role.PRIMARY or variant != Variant.WITH_ODDS:
        assert alternate.id != primary.id
    _, detail = await execute(factory, alternate, service_settings)
    assert detail.role == role and detail.variant == variant
    assert detail.actual_model == ("mock-v1" if role == Role.PRIMARY else "mock-challenger-v1")


async def test_zero_candidates_is_success_not_abstain(factory, record, service_settings, tmp_path):
    data = yaml.safe_load(Path("config/llm.yaml").read_text())
    data["policy"]["ranking"]["min_edge"] = 1
    path = tmp_path / "llm.yaml"
    path.write_text(yaml.safe_dump(data))
    settings = service_settings.model_copy(update={"llm_routes_path": str(path)})
    run, _ = await request(factory, record, settings)
    _, detail = await execute(factory, run, settings)
    assert (
        detail.status == "SUCCEEDED"
        and detail.outcome == "NO_BET"
        and len(detail.probabilities) == 12
    )
    assert not any(c.displayed for c in detail.candidates) and detail.abstain_reason is None


async def test_cannot_predict_auditable_abstention_zero_calls(factory, record, service_settings):
    data = record.context_jsonb
    data["data_quality"]["can_predict"] = False
    context = MatchContextV1.model_validate(data)
    async with factory() as session:
        await session.execute(
            update(MatchContextRecord)
            .where(MatchContextRecord.id == record.id)
            .values(
                context_jsonb=data,
                context_hash=hashlib.sha256(context.canonical_json().encode()).hexdigest(),
            )
        )
        await session.commit()
        changed = await session.get(MatchContextRecord, record.id)
    run, _ = await request(factory, changed, service_settings)
    provider = ScriptedProvider([{}])
    _, detail = await execute(factory, run, service_settings, provider)
    assert detail.status == "ABSTAINED" and detail.outcome == "ABSTAIN" and provider.calls == []
    assert detail.probabilities == detail.candidates == []


async def test_invalid_output_never_creates_displayed_candidate(factory, record, service_settings):
    run, _ = await request(factory, record, service_settings)
    provider = ScriptedProvider([{}, {}, {}])
    _, detail = await execute(factory, run, service_settings, provider)
    assert (
        detail.status == "FAILED"
        and detail.error_code == "invalid_output"
        and len(provider.calls) == 2
    )
    assert detail.probabilities == detail.candidates == [] and len(detail.attempts) == 2
    async with factory() as session:
        assert (await session.get(Job, run.job_id)).status == "FAILED"


async def test_model_abstains_validly(factory, record, service_settings):
    run, _ = await request(factory, record, service_settings)
    raw = valid_output(MatchContextV1.model_validate(record.context_jsonb), record.context_hash)
    raw.update(abstain=True, abstain_reason="Source conflict", probabilities=None)
    _, detail = await execute(factory, run, service_settings, ScriptedProvider([raw]))
    assert (
        detail.status == "ABSTAINED"
        and detail.abstain_reason == "Source conflict"
        and not detail.probabilities
    )


async def test_fallback_actual_model_config_and_usage_persist(
    factory, record, service_settings, tmp_path
):
    data = yaml.safe_load(Path("config/llm.yaml").read_text())
    data["routes"]["prediction_primary"]["fallbacks"] = [
        {"provider": "minimax", "model": "configured-alt", "structured_mode": "json_only"}
    ]
    data["policy"].update(max_retries=0, max_retry_delay_seconds=0)
    path = tmp_path / "llm.yaml"
    path.write_text(yaml.safe_dump(data))
    settings = service_settings.model_copy(update={"llm_routes_path": str(path)})
    run, _ = await request(factory, record, settings)
    first = ScriptedProvider([LLMError("timeout", retryable=True)])
    second = ScriptedProvider(
        [valid_output(MatchContextV1.model_validate(record.context_jsonb), record.context_hash)],
        provider="minimax",
        actual_model="actual-alt-version",
    )
    await run_prediction_job(
        str(run.job_id),
        str(run.id),
        settings=settings,
        session_factory=factory,
        provider_factory=lambda spec: first if spec.provider == "mock" else second,
    )
    async with factory() as session:
        detail = await read_prediction(session, run.id)
    assert detail["actual_provider"] == "minimax" and detail["actual_model"] == "actual-alt-version"
    assert detail["runtime_model_config"]["model"] == "actual-alt-version"
    assert detail["input_tokens"] == 10 and detail["output_tokens"] == 20
    assert any("fallback:minimax" in a for a in detail["audit"])
    assert detail["attempts"][0]["health"] == "DEGRADED"


async def test_daily_budget_counts_repairs_and_prevents_extra_call(
    factory, record, service_settings, tmp_path
):
    data = yaml.safe_load(Path("config/llm.yaml").read_text())
    data["policy"]["max_calls_per_day"] = 1
    path = tmp_path / "llm.yaml"
    path.write_text(yaml.safe_dump(data))
    settings = service_settings.model_copy(update={"llm_routes_path": str(path)})
    run, _ = await request(factory, record, settings)
    provider = ScriptedProvider([{}, {}])
    _, detail = await execute(factory, run, settings, provider)
    assert (
        detail.status == "FAILED"
        and detail.error_code == "daily_budget_exceeded"
        and len(provider.calls) == 1
    )


async def test_automatic_eligible_context_one_job_duplicate_completion(
    factory, record, service_settings, enqueued
):
    settings = service_settings.model_copy(update={"prediction_auto_enabled": True})
    async with factory() as session:
        a = await automatic_prediction(session, record, settings)
    async with factory() as session:
        b = await automatic_prediction(session, record, settings)
    assert a.id == b.id and len(enqueued) == 1 and enqueued[0]["queue"] == "llm"
    assert enqueued[0]["args"] == [str(a.job_id), str(a.id)]


async def test_automatic_disabled_or_ineligible_context_no_jobs(
    factory, record, service_settings, enqueued
):
    async with factory() as session:
        assert await automatic_prediction(session, record, service_settings) is None
    data = record.context_jsonb
    data["data_quality"]["can_predict"] = False
    record.context_jsonb = data
    record.context_hash = hashlib.sha256(
        MatchContextV1.model_validate(data).canonical_json().encode()
    ).hexdigest()
    async with factory() as session:
        assert (
            await automatic_prediction(
                session,
                record,
                service_settings.model_copy(update={"prediction_auto_enabled": True}),
            )
            is None
        )
    assert not enqueued


async def test_api_enqueues_and_reads_persisted_state_only(
    factory, record, service_settings, enqueued
):
    with TestClient(create_app(service_settings)) as client:
        a = client.post(f"/v1/fixtures/{record.fixture_id}/analyze", json={})
        b = client.post(f"/v1/fixtures/{record.fixture_id}/analyze", json={})
        assert a.status_code == b.status_code == 202 and b.json()["already_queued"]
        assert a.json()["run_id"] == b.json()["run_id"] and len(enqueued) == 1
        assert (
            client.post(
                f"/v1/fixtures/{record.fixture_id}/analyze", json={"rerun": True}
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"/v1/fixtures/{record.fixture_id}/analyze", json={"api_key": "danger"}
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"/v1/fixtures/{record.fixture_id}/analyze", json={"phase": "POSTMATCH"}
            ).status_code
            == 422
        )
        assert (
            client.post(
                f"/v1/fixtures/{record.fixture_id}/analyze", json={"route_override": "arbitrary"}
            ).status_code
            == 422
        )
        assert client.get("/v1/predictions?role=INVALID").status_code == 422
        assert client.get(f"/v1/predictions/{uuid.uuid4()}").status_code == 404
        run_id = uuid.UUID(a.json()["run_id"])
        async with factory() as session:
            run = await session.get(PredictionRun, run_id)
        _, detail = await execute(factory, run, service_settings)
        response = client.get(f"/v1/predictions/{run_id}")
        assert response.status_code == 200 and len(response.json()["probabilities"]) == 12
        assert client.get("/v1/predictions").json()[0]["id"] == str(run_id)
        assert "context_jsonb" not in response.json()
        assert "Все вероятности" in str(
            [
                [b.text for b in row]
                for row in __import__(
                    "sports_intelligence.bot.predictions", fromlist=["prediction_keyboard"]
                )
                .prediction_keyboard(detail)
                .inline_keyboard
            ]
        )


async def test_future_lineup_odds_result_cannot_enter_frozen_prediction(
    factory, record, service_settings
):
    original_json = json.dumps(record.context_jsonb, sort_keys=True)
    run, _ = await request(factory, record, service_settings)
    future = record.as_of + timedelta(hours=5)
    async with factory() as session:
        session.add(
            OddsSnapshotSet(
                fixture_id=record.fixture_id,
                provider="future-forbidden",
                captured_at=future,
                market_whitelist_jsonb=["h2h"],
            )
        )
        session.add(
            LineupSnapshot(
                fixture_id=record.fixture_id,
                team_id=uuid.UUID(record.context_jsonb["fixture_identity"]["home_team_id"]),
                provider="future-forbidden",
                captured_at=future,
                confirmed=True,
                players_jsonb=[{"future": "forbidden"}],
                publication_state="CONFIRMED",
            )
        )
        await session.execute(
            update(Fixture).where(Fixture.id == record.fixture_id).values(status="FT")
        )
        await session.commit()
    provider = ScriptedProvider(
        [valid_output(MatchContextV1.model_validate(record.context_jsonb), record.context_hash)]
    )
    _, detail = await execute(factory, run, service_settings, provider)
    assert detail.status == "SUCCEEDED" and detail.context_hash == record.context_hash
    assert json.dumps(provider.calls[0]["context"], sort_keys=True) == original_json
    assert "future-forbidden" not in json.dumps(detail.model_dump(mode="json"))


async def test_enqueued_prompt_and_route_immutable_when_files_change(
    factory, record, service_settings, tmp_path
):
    prompt = tmp_path / "1.0.0.txt"
    prompt.write_text(Path("prompts/predictor/1.0.0.txt").read_text())
    settings = service_settings.model_copy(update={"prediction_prompt_path": str(prompt)})
    run, _ = await request(factory, record, settings)
    prompt.write_text("Changed later prompt")
    changed = settings.model_copy(
        update={"llm_provider": "openai", "predictor_model": "later-model"}
    )
    _, detail = await execute(factory, run, changed)
    assert detail.actual_provider == "mock" and detail.actual_model == "mock-v1"
    assert detail.prompt_hash != hashlib.sha256(prompt.read_bytes()).hexdigest()


async def test_enqueue_failure_auditable_no_accidental_retry(
    factory, record, service_settings, monkeypatch
):
    def fail(**kwargs):
        raise RuntimeError("synthetic broker failure")

    monkeypatch.setattr(predict_match_task, "apply_async", fail)
    async with factory() as session:
        run, created = await request_prediction(session, record=record, settings=service_settings)
        with pytest.raises(RuntimeError):
            await enqueue_prediction(session, run, created)
    duplicate, created = await request(factory, record, service_settings)
    assert duplicate.id == run.id and not created and duplicate.error_code == "enqueue_failed"


async def test_keyless_end_to_end_discovery_collectors_context_api_telegram(
    factory, service_settings, tmp_path, enqueued, monkeypatch
):
    """Real M2/M4/M6/M7 local services; synthetic providers, actual Postgres/Redis."""
    from datetime import UTC

    import httpx
    from redis.asyncio import Redis

    import sports_intelligence.collectors.odds_collector  # noqa: F401
    import sports_intelligence.collectors.sports_collectors  # noqa: F401
    from sports_intelligence.bot.backend_client import BackendClient
    from sports_intelligence.bot.context import AppContext
    from sports_intelligence.bot.predictions import prediction_callback
    from sports_intelligence.collectors.framework import CollectorContext, run_collector
    from sports_intelligence.collectors.freshness import FreshnessPolicy
    from sports_intelligence.collectors.locks import CoalesceLockManager
    from sports_intelligence.collectors.quota import QuotaManager
    from sports_intelligence.context.builder import (
        ContextBuildPolicy,
        build_and_persist_match_context,
    )
    from sports_intelligence.core.league_config import load_league_config
    from sports_intelligence.core.phases import ForecastPhase
    from sports_intelligence.pipelines.discover_fixtures import FixtureDiscoveryService
    from sports_intelligence.providers.odds.mock import MockOddsProvider
    from sports_intelligence.providers.sports.mock import MockSportsDataProvider
    from sports_intelligence.quality.engine import build_quality_policy
    from telegram_fakes import FakeTransport, make_callback

    now = datetime.now(UTC)
    kickoff = now + timedelta(hours=6)
    recorded = json.loads(
        Path(
            "src/sports_intelligence/providers/sports/mock_data/fixtures_2026-08-21.json"
        ).read_text()
    )
    recorded["response"] = recorded["response"][:1]
    recorded["response"][0]["fixture"]["date"] = kickoff.isoformat()
    recorded["response"][0]["fixture"]["timestamp"] = int(kickoff.timestamp())
    slug = "m7-e2e-" + uuid.uuid4().hex[:12]
    provider_name = "mock_m7_" + uuid.uuid4().hex[:8]
    league_config = tmp_path / "leagues.yaml"
    league_config.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "leagues": [
                    {
                        "slug": slug,
                        "name": "Synthetic M7 E2E",
                        "enabled": True,
                        "provider_ids": {provider_name: 39},
                        "odds_sport_key": "soccer_mock",
                    }
                ],
            }
        )
    )
    settings = service_settings.model_copy(
        update={
            "leagues_config_path": str(league_config),
            "research_enabled": False,
            "sports_provider": provider_name,
        }
    )
    sports = MockSportsDataProvider(
        responses={now.date().isoformat(): recorded}, provider_name=provider_name
    )
    redis = Redis.from_url(settings.redis_url)
    try:
        await redis.flushdb()
        quota = QuotaManager(settings, factory, redis=redis)
        discovery = FixtureDiscoveryService(
            sports, factory, load_league_config(str(league_config)), quota=quota
        )
        summary = await discovery.discover(now.date())
        assert summary.fixtures_created == 1
        async with factory() as session:
            league = await session.scalar(select(League).where(League.slug == slug))
            fx = await session.scalar(select(Fixture).where(Fixture.league_id == league.id))
            teams = [
                await session.get(Team, fx.home_team_id),
                await session.get(Team, fx.away_team_id),
            ]
        ctx = CollectorContext(
            provider=sports,
            quota=quota,
            locks=CoalesceLockManager(redis, settings),
            freshness=FreshnessPolicy(settings),
            session_factory=factory,
            settings=settings,
            redis=redis,
        )
        for name, args in [
            ("standings", {"league_id": fx.league_id, "season_id": fx.season_id}),
            (
                "team_stats",
                {"team_id": fx.home_team_id, "league_id": fx.league_id, "season_id": fx.season_id},
            ),
            (
                "team_stats",
                {"team_id": fx.away_team_id, "league_id": fx.league_id, "season_id": fx.season_id},
            ),
            ("form_inputs", {"team_id": fx.home_team_id}),
            ("form_inputs", {"team_id": fx.away_team_id}),
            ("availability", {"fixture_id": fx.id, "team_id": fx.home_team_id}),
        ]:
            await run_collector(ctx, name, inputs=args)
        odds = MockOddsProvider(
            home_team=teams[0].name, away_team=teams[1].name, commence_time_utc=kickoff
        )
        odds_ctx = CollectorContext(
            provider=odds,
            quota=quota,
            locks=ctx.locks,
            freshness=ctx.freshness,
            session_factory=factory,
            settings=settings,
            redis=redis,
        )
        await run_collector(
            odds_ctx,
            "odds",
            inputs={"fixture_id": fx.id, "markets": ["h2h", "double_chance", "totals", "btts"]},
        )
        as_of = datetime.now(UTC)
        build_policy = ContextBuildPolicy(
            quality_policy=build_quality_policy(settings),
            freshness_policy=FreshnessPolicy(settings),
            research_enabled=False,
        )
        async with factory() as session:
            rec, quality, _, context = await build_and_persist_match_context(
                session,
                fixture_id=fx.id,
                forecast_phase=ForecastPhase.MORNING,
                as_of=as_of,
                build_policy=build_policy,
            )
        assert quality.can_predict and context.market_snapshot.prices
        with TestClient(create_app(settings)) as client:
            response = client.post(f"/v1/fixtures/{fx.id}/analyze", json={})
            assert response.status_code == 202
            run_id = uuid.UUID(response.json()["run_id"])
            async with factory() as session:
                run = await session.get(PredictionRun, run_id)
            _, detail = await execute(factory, run, settings)
            assert detail.status == "SUCCEEDED" and len(detail.probabilities) == 12
            assert next(b for b in detail.baselines if b["name"] == "statistical")["probabilities"]
            transport = FakeTransport()
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda r: httpx.Response(200, json=client.get(r.url.path).json())
                )
            ) as http:
                backend = BackendClient("https://synthetic.invalid", client=http)
                app_context = AppContext(
                    transport=transport,
                    backend=backend,
                    settings=settings,
                    allowed_user_ids=frozenset({1}),
                )
                await prediction_callback(make_callback(f"pred:table:{run_id}"), app_context)
            assert len(transport.answered) == 1 and "OVER_1_5" in transport.edited[0]["text"]
            assert "HOME_OR_DRAW" in transport.edited[0]["text"]
            assert len(enqueued) == 1

        # The actual accepted scanner→context-worker hook also deduplicates completion.
        from sports_intelligence.collectors.pre_match_scan import PreMatchDecision
        from sports_intelligence.workers.tasks import pre_match
        from sports_intelligence.workers.tasks.context import _run_build, build_match_context_task

        auto_settings = settings.model_copy(update={"prediction_auto_enabled": True})
        monkeypatch.setattr(pre_match, "get_settings", lambda: auto_settings)
        # The context dispatch helper deliberately loads settings through core.config too.
        monkeypatch.setattr("sports_intelligence.core.config.get_settings", lambda: auto_settings)
        context_jobs = []
        monkeypatch.setattr(
            build_match_context_task, "apply_async", lambda **kw: context_jobs.append(kw)
        )
        decision = PreMatchDecision(
            fixture_id=str(fx.id),
            league_id=str(fx.league_id),
            home_team_id=str(fx.home_team_id),
            away_team_id=str(fx.away_team_id),
            season_id=str(fx.season_id),
            kickoff_at=kickoff,
            phase=ForecastPhase.MORNING,
            categories_to_collect=(),
        )
        scan_at = datetime.now(UTC)
        await pre_match._try_enqueue_context_build(factory, decision, as_of=scan_at)
        assert len(context_jobs) == 1
        args = context_jobs[0]["args"]
        await _run_build(*args, settings=auto_settings, session_factory=factory)
        assert len(enqueued) == 2
        auto_job = enqueued[-1]
        await pre_match._try_enqueue_context_build(
            factory, decision, as_of=scan_at + timedelta(seconds=1)
        )
        assert len(context_jobs) == 1 and enqueued[-1] == auto_job
        automatic_result = await run_prediction_job(
            *auto_job["args"], settings=auto_settings, session_factory=factory
        )
        assert automatic_result["status"] == "SUCCEEDED"
    finally:
        await redis.aclose()
        await sports.aclose()


async def test_validation_failure_health_and_usage_are_auditable(factory, record, service_settings):
    run, _ = await request(factory, record, service_settings)
    provider = ScriptedProvider([{}, {}])
    _, detail = await execute(factory, run, service_settings, provider)
    assert all(
        a["health"] == "DEGRADED" and a["error_code"] == "invalid_output" for a in detail.attempts
    )
    assert detail.input_tokens == 20 and detail.output_tokens == 40
    async with factory() as session:
        assert (await session.get(Job, run.job_id)).fixture_id == record.fixture_id


async def test_missing_real_credentials_fail_without_mock_fallback(
    factory, record, service_settings, tmp_path
):
    data = yaml.safe_load(Path("config/llm.yaml").read_text())
    data["routes"]["prediction_primary"]["primary"] = {
        "provider": "openai",
        "model": "configured",
        "structured_mode": "json_schema",
    }
    path = tmp_path / "llm.yaml"
    path.write_text(yaml.safe_dump(data))
    settings = service_settings.model_copy(
        update={"llm_routes_path": str(path), "app_env": "live_local"}
    )
    run, _ = await request(factory, record, settings)
    _, detail = await execute(factory, run, settings)
    assert detail.status == "FAILED" and detail.error_code == "missing_credentials"
    assert detail.actual_provider is None and detail.attempts == [] and detail.probabilities == []


async def test_challenger_budget_zero_prevents_provider_call(
    factory, record, service_settings, tmp_path
):
    data = yaml.safe_load(Path("config/llm.yaml").read_text())
    data["policy"]["max_challenger_calls_per_day"] = 0
    path = tmp_path / "llm.yaml"
    path.write_text(yaml.safe_dump(data))
    settings = service_settings.model_copy(update={"llm_routes_path": str(path)})
    run, _ = await request(factory, record, settings, role=Role.CHALLENGER)
    provider = ScriptedProvider([{}])
    _, detail = await execute(factory, run, settings, provider)
    assert (
        detail.error_code == "daily_budget_exceeded"
        and not provider.calls
        and detail.actual_model is None
    )


async def test_actual_celery_broker_payload_contains_identifiers_only(service_settings):
    import base64

    from redis.asyncio import Redis

    from sports_intelligence.workers.celery_app import create_celery_app

    settings = service_settings.model_copy(
        update={
            "celery_broker_url": service_settings.redis_url,
            "celery_result_backend": service_settings.redis_url,
        }
    )
    app = create_celery_app(settings)
    queue = "m7_test_llm_" + uuid.uuid4().hex
    identifiers = [str(uuid.uuid4()), str(uuid.uuid4())]
    redis = Redis.from_url(service_settings.redis_url)
    try:
        app.send_task("prediction.predict_match", args=identifiers, queue=queue, ignore_result=True)
        messages = await redis.lrange(queue, 0, -1)
        assert len(messages) == 1
        message = json.loads(messages[0])
        body = json.loads(base64.b64decode(message["body"]))
        assert body[0] == identifiers and body[1] == {}
        assert message["headers"]["task"] == "prediction.predict_match"
        assert "MatchContext" not in str(message)
    finally:
        await redis.delete(queue)
        await redis.aclose()
        app.close()


async def test_worker_refuses_model_config_tampering_before_call(factory, record, service_settings):
    from sports_intelligence.db.models import ModelConfig

    run, _ = await request(factory, record, service_settings)
    async with factory() as session:
        model = await session.get(ModelConfig, run.requested_model_config_id)
        model.config_jsonb = {**model.config_jsonb, "model": "tampered-after-enqueue"}
        await session.commit()
    provider = ScriptedProvider([{}])
    with pytest.raises(ValueError, match="frozen_model_config_identity_mismatch"):
        await execute(factory, run, service_settings, provider)
    assert not provider.calls
    async with factory() as session:
        failed = await session.get(PredictionRun, run.id)
        assert failed.status == "FAILED" and failed.error_code == "prediction_execution_failure"


async def test_context_internal_fixture_identity_mismatch_rejected(
    factory, record, service_settings
):
    data = record.context_jsonb
    data["fixture_identity"]["fixture_id"] = str(uuid.uuid4())
    record.context_jsonb = data
    record.context_hash = hashlib.sha256(
        MatchContextV1.model_validate(data).canonical_json().encode()
    ).hexdigest()
    with pytest.raises(ValueError, match="context_integrity_mismatch"):
        await request(factory, record, service_settings)
