"""M8.1 persisted summary materialization selection, using synthetic M7 forecasts."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
import test_m8_evaluation as m8
from fastapi.testclient import TestClient

from sports_intelligence.api.app import create_app
from sports_intelligence.evaluation.config import EvaluationFilters

factory = m8.factory
record = m8.record
clear_evaluation = m8.clear_evaluation

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not (os.environ.get("TEST_DATABASE_URL") and os.environ.get("TEST_REDIS_URL")),
        reason="isolated Postgres/Redis required",
    ),
]


@pytest.fixture
async def forecast(factory, record, service_settings):
    run, _ = await m8.request(factory, record, service_settings)
    await m8.execute(factory, run, service_settings)
    await m8.result_and_settle(factory, record)
    return uuid.UUID(record.context_jsonb["fixture_identity"]["league_id"])


async def broad_automatic(factory, settings):
    # Same persisted all-time filter/cutoff contract as the automatic M8 refresh.
    cutoff = datetime.now(UTC)
    return await m8.evaluate(
        factory, settings, filters=EvaluationFilters(end=cutoff), cutoff=cutoff
    )


async def test_older_combined_scope_survives_newer_broad_run(factory, forecast, service_settings):
    scoped, metrics, _ = await m8.evaluate(
        factory, service_settings, filters=EvaluationFilters(league=forecast, market="1x2")
    )
    broad, _, _ = await broad_automatic(factory, service_settings)
    assert broad.source_cutoff > scoped.source_cutoff
    with TestClient(create_app(service_settings)) as client:
        payload = client.get(
            f"/v1/evaluations/summary?period=all&league={forecast}&market=1x2"
        ).json()
    assert payload["status"] == "SUCCEEDED"
    assert payload["evaluation_id"] == str(scoped.id)
    assert len(payload["groups"]) == 1
    brier = payload["groups"][0]["metrics"]["binary_brier"]
    assert (brier["value"], brier["sample_size"]) == m8.summary(metrics)["binary_brier"]
    assert brier["sample_size"] == 3


async def test_scoped_filter_plus_group_by_survives_newer_broad_run(
    factory, forecast, service_settings
):
    scoped, metrics, _ = await m8.evaluate(
        factory, service_settings, filters=EvaluationFilters(league=forecast)
    )
    broad, _, _ = await broad_automatic(factory, service_settings)
    assert broad.source_cutoff > scoped.source_cutoff
    with TestClient(create_app(service_settings)) as client:
        payload = client.get(
            f"/v1/evaluations/summary?period=all&league={forecast}&group_by=market"
        ).json()
    assert payload["evaluation_id"] == str(scoped.id)
    assert {g["dimensions"]["market"] for g in payload["groups"]} == {
        "1x2",
        "double_chance",
        "ou_15",
        "ou_25",
        "btts",
    }
    for group in payload["groups"]:
        market = group["dimensions"]["market"]
        brier = group["metrics"]["binary_brier"]
        assert (brier["value"], brier["sample_size"]) == m8.summary(metrics, market=market)[
            "binary_brier"
        ]


async def test_broad_run_serves_base_single_filter_and_single_group_by(
    factory, forecast, service_settings
):
    broad, _, _ = await broad_automatic(factory, service_settings)
    with TestClient(create_app(service_settings)) as client:
        for suffix, expected in (
            ("", 12),
            ("&market=1x2", 3),
            (f"&league={forecast}", 12),
            ("&group_by=market", 12),
            (f"&league={forecast}&group_by=league", 12),
        ):
            payload = client.get("/v1/evaluations/summary?period=all" + suffix).json()
            assert payload["status"] == "SUCCEEDED"
            assert payload["evaluation_id"] == str(broad.id)
            assert sum(g["sample_size"] for g in payload["groups"]) == expected


async def test_incompatible_combinations_are_not_available(factory, forecast, service_settings):
    broad, _, _ = await broad_automatic(factory, service_settings)
    with TestClient(create_app(service_settings)) as client:
        for suffix in (
            f"&league={forecast}&market=1x2",
            f"&league={forecast}&group_by=market",
            f"&league={forecast}&market=1x2&evaluation_id={broad.id}",
        ):
            response = client.get("/v1/evaluations/summary?period=all" + suffix)
            assert response.status_code == 200
            payload = response.json()
            assert payload["status"] == "not_available"
            assert payload["groups"] == [] and payload["sample_size"] == 0
            assert payload["reason"] == "no_compatible_persisted_materialization"
            assert "evaluation_id" not in payload


async def test_most_scoped_run_preferred_and_equal_scopes_use_latest_cutoff(
    factory, forecast, service_settings
):
    filters = EvaluationFilters(league=forecast, market="1x2")
    old, _, _ = await m8.evaluate(factory, service_settings, filters=filters)
    new, _, _ = await m8.evaluate(factory, service_settings, filters=filters)
    partial, _, _ = await m8.evaluate(
        factory, service_settings, filters=EvaluationFilters(league=forecast)
    )
    broad, _, _ = await broad_automatic(factory, service_settings)
    assert old.source_cutoff < new.source_cutoff < partial.source_cutoff < broad.source_cutoff
    with TestClient(create_app(service_settings)) as client:
        payload = client.get(
            f"/v1/evaluations/summary?period=all&league={forecast}&market=1x2"
        ).json()
        assert payload["evaluation_id"] == str(new.id)
        # One scoped dimension + one persisted facet can also truthfully answer the query.
        payload = client.get(
            f"/v1/evaluations/summary?period=all&league={forecast}&market=1x2"
            f"&evaluation_id={partial.id}"
        ).json()
        assert payload["evaluation_id"] == str(partial.id)
        assert payload["groups"][0]["sample_size"] == 3
