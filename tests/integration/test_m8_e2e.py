"""Full keyless M2→M8 pipeline with test clocks and real isolated Docker services."""

import json
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import test_m7_predictions as m7
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_m8_evaluation import clear_evaluation  # noqa: F401

from sports_intelligence.api.app import create_app
from sports_intelligence.db.models import (
    FeatureSnapshot,
    Fixture,
    League,
    MatchContextRecord,
    PredictionRun,
    Team,
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


async def test_m8_full_keyless_result_worker_to_evaluation_api_telegram(
    factory, service_settings, tmp_path, enqueued, monkeypatch, *, include_research=False
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
            "research_enabled": include_research,
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
        if include_research:
            import sports_intelligence.collectors.research_collector  # noqa: F401
            from sports_intelligence.providers.search.mock import MockSearchProvider

            search = MockSearchProvider()
            research_ctx = CollectorContext(
                provider=search,
                quota=quota,
                locks=ctx.locks,
                freshness=ctx.freshness,
                session_factory=factory,
                settings=settings,
                redis=redis,
            )
            await run_collector(research_ctx, "research", inputs={"fixture_id": fx.id})
            assert search.calls
            calls_before = len(search.calls)
            await run_collector(research_ctx, "research", inputs={"fixture_id": fx.id})
            assert len(search.calls) == calls_before  # Freshness avoids repeated queries.
        as_of = datetime.now(UTC)
        build_policy = ContextBuildPolicy(
            quality_policy=build_quality_policy(settings),
            freshness_policy=FreshnessPolicy(settings),
            research_enabled=include_research,
        )
        async with factory() as session:
            rec, quality, _, context = await build_and_persist_match_context(
                session,
                fixture_id=fx.id,
                forecast_phase=ForecastPhase.MORNING,
                as_of=as_of,
                build_policy=build_policy,
            )
        async with factory() as session:
            feature_before = (
                await session.get(FeatureSnapshot, rec.feature_snapshot_id)
            ).features_jsonb
        assert quality.can_predict and context.market_snapshot.prices
        if include_research:
            assert context.research_claims.claims
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
                    lambda r: httpx.Response(
                        200, json=client.get(r.url.path, params=dict(r.url.params)).json()
                    )
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

        # Advance only the synthetic clock after the prediction; historical M7 data stays frozen.

        from sports_intelligence.bot.evaluation import results_command, stats_callback
        from sports_intelligence.evaluation import results as result_service
        from sports_intelligence.evaluation import service as eval_service
        from sports_intelligence.pipelines.discover_fixtures import create_or_get_job
        from sports_intelligence.workers.tasks import evaluation as tasks
        from telegram_fakes import make_message

        t2 = kickoff + timedelta(hours=3)
        t3 = t2 + timedelta(hours=1)

        class LaterClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return t3 if tz is not None else t3.replace(tzinfo=None)

        monkeypatch.setattr(tasks, "datetime", LaterClock)
        monkeypatch.setattr(result_service, "datetime", LaterClock)
        monkeypatch.setattr(eval_service, "datetime", LaterClock)
        monkeypatch.setattr("sports_intelligence.providers.sports.mock.utc_now", lambda: t2)
        finished_payload = json.loads(json.dumps(recorded))
        finished_payload["response"][0]["fixture"]["status"] = {"short": "FT"}
        finished_payload["response"][0]["score"] = {"fulltime": {"home": 2, "away": 1}}
        result_provider = MockSportsDataProvider(
            responses={kickoff.date().isoformat(): finished_payload}, provider_name=provider_name
        )
        eval_jobs = []
        monkeypatch.setattr(tasks.evaluate_task, "apply_async", lambda **kw: eval_jobs.append(kw))
        async with factory() as session:
            job, _ = await create_or_get_job(session, "results", "m8-e2e-" + uuid.uuid4().hex, t2)
            await session.commit()
        outcome = await tasks.run_result_job(
            str(job.id),
            kickoff.date().isoformat(),
            provider_name,
            settings=settings,
            factory=factory,
            provider=result_provider,
            redis=redis,
        )
        assert outcome["status"] == "SUCCEEDED" and outcome["settled"] == 12
        assert len(eval_jobs) == 3
        for item in eval_jobs:
            await tasks.run_evaluation_job(**item["kwargs"], settings=settings, factory=factory)
        with TestClient(create_app(settings)) as client:
            all_time = client.get("/v1/evaluations/summary?period=all").json()
            assert all_time["groups"][0]["sample_size"] == 12
            assert len(client.get(f"/v1/results/{fx.id}/settlements").json()) == 12
            transport = FakeTransport()
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda r: httpx.Response(
                        200, json=client.get(r.url.path, params=dict(r.url.params)).json()
                    )
                )
            ) as http:
                backend = BackendClient("https://synthetic.invalid", client=http)
                app_context = AppContext(
                    transport=transport,
                    backend=backend,
                    settings=settings,
                    allowed_user_ids=frozenset({1}),
                )
                await stats_callback(make_callback("stats:all:summary"), app_context)
                await results_command(make_message("/results"), app_context)
            assert "Brier" in transport.edited[0]["text"] and "n=12" in transport.edited[0]["text"]
            assert "n=1" in transport.sent[0]["text"]
            async with factory() as session:
                original = await session.get(MatchContextRecord, rec.id)
                assert (
                    await session.get(FeatureSnapshot, rec.feature_snapshot_id)
                ).features_jsonb == feature_before
                assert (
                    original.context_hash == rec.context_hash
                    and original.context_jsonb == rec.context_jsonb
                )
    finally:
        await redis.aclose()
        await sports.aclose()
