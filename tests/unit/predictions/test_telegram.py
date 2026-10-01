from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from aiogram.filters import CommandObject

from sports_intelligence.bot.backend_client import BackendClient, BackendClientError
from sports_intelligence.bot.context import AppContext
from sports_intelligence.bot.predictions import (
    analyze_command,
    fixture_prediction_keyboard,
    prediction_callback,
    prediction_keyboard,
    render_prediction,
)
from sports_intelligence.core.config import Settings
from sports_intelligence.predictions.contracts import Role, Variant
from sports_intelligence.schemas.predictions import PredictionDetail
from telegram_fakes import FakeTransport, make_callback, make_message


def detail():
    run_id, fixture_id, context_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    return PredictionDetail(
        id=run_id,
        fixture_id=fixture_id,
        match_context_id=context_id,
        context_hash="a" * 64,
        forecast_phase="MORNING",
        as_of=datetime(2026, 8, 21, 10, tzinfo=UTC),
        role=Role.PRIMARY,
        variant=Variant.WITH_ODDS,
        status="SUCCEEDED",
        outcome="NO_BET",
        actual_provider="mock",
        actual_model="mock-v1",
        created_at=datetime(2026, 8, 21, 10, tzinfo=UTC),
        completed_at=None,
        home_team="<Home>",
        away_team="Away",
        data_quality=0.9,
        abstain_reason=None,
        error_code=None,
        model_config_hash="b" * 64,
        runtime_model_config={},
        requested_model_config={},
        prompt_name="predictor",
        prompt_version="1.0.0",
        prompt_hash="c" * 64,
        prompt_source="prompts/predictor/1.0.0.txt",
        requested_identity="d" * 64,
        semantic_identity="e" * 64,
        requested_route="prediction_primary",
        route_fingerprint="f" * 64,
        policy={},
        policy_hash="a" * 64,
        latency_ms=123,
        input_tokens=12,
        output_tokens=34,
        provider_request_id="request",
        audit=[],
        output={
            "summary": "Synthetic <script>",
            "evidence_for": [{"path": "data_quality.overall_score", "observation": "Synthetic"}],
            "evidence_against": [],
            "risk_flags": ["synthetic_mock"],
            "confidence": {"level": "low", "limitations": []},
        },
        probabilities=[{"market": "1x2", "selection": "HOME", "model_probability": 0.5}],
        candidates=[],
        baselines=[],
        attempts=[],
    )


@pytest.mark.parametrize("view", ["top", "table", "why", "risks", "model"])
def test_screens_render_safe_compact_persisted_data(view):
    run = detail()
    text = render_prediction(run, view)
    assert "&lt;Home&gt;" in text and "<script>" not in text and len(text) < 4096
    assert "guaranteed" not in text and "safe bet" not in text
    if view == "top":
        assert "NO HIGH-CONFIDENCE OPPORTUNITY" in text
    if view == "table":
        assert "HOME: 50.0%" in text
    if view == "model":
        assert "mock-v1" in text and run.context_hash in text


@pytest.mark.parametrize("status", ["QUEUED", "RUNNING", "FAILED", "ABSTAINED"])
def test_non_success_never_shows_normal_forecast(status):
    run = detail().model_copy(
        update={"status": status, "abstain_reason": "Quality insufficient", "error_code": "timeout"}
    )
    assert "NO HIGH-CONFIDENCE OPPORTUNITY" not in render_prediction(run)


def test_challenger_not_shown_as_primary():
    run = detail().model_copy(update={"role": Role.CHALLENGER})
    assert "Теневой прогноз" in render_prediction(run)


def test_all_callback_payloads_under_64_bytes():
    for keyboard in (prediction_keyboard(detail()), fixture_prediction_keyboard(uuid.uuid4())):
        assert all(
            len(b.callback_data.encode()) <= 64 for row in keyboard.inline_keyboard for b in row
        )


async def test_duplicate_rerun_taps_have_stable_token_and_original_context():
    run = detail()
    calls = []

    class Backend:
        async def get_prediction(self, run_id):
            return run

        async def analyze_fixture(self, fixture_id, **options):
            calls.append((fixture_id, options))
            return SimpleNamespace(run_id=uuid.uuid4())

    transport = FakeTransport()
    ctx = AppContext(
        transport=transport,
        backend=Backend(),
        settings=Settings(_env_file=None),
        allowed_user_ids=frozenset({1}),
    )
    callback = make_callback(f"pred:rerun:{run.id}")
    await prediction_callback(callback, ctx)
    await prediction_callback(callback, ctx)
    assert calls[0] == calls[1] and calls[0][1]["context_id"] == run.match_context_id
    assert calls[0][1]["rerun_key"] == uuid.uuid5(run.id, "telegram_explicit_rerun")
    assert len(transport.answered) == 2


async def test_malformed_callback_no_backend_call_and_one_ack():
    transport = FakeTransport()
    ctx = AppContext(
        transport=transport,
        backend=None,
        settings=Settings(_env_file=None),
        allowed_user_ids=frozenset({1}),
    )
    await prediction_callback(make_callback("pred:top:invalid"), ctx)
    assert len(transport.answered) == 1 and transport.edited


async def test_analyze_command_only_enqueues_backend():
    calls = []

    class Backend:
        async def analyze_fixture(self, fixture_id):
            calls.append(fixture_id)
            return SimpleNamespace(job_id=uuid.uuid4(), already_queued=False)

    transport = FakeTransport()
    ctx = AppContext(
        transport=transport,
        backend=Backend(),
        settings=Settings(_env_file=None),
        allowed_user_ids=frozenset({1}),
    )
    fixture_id = uuid.uuid4()
    await analyze_command(
        make_message("/analyze"), CommandObject(command="analyze", args=str(fixture_id)), ctx
    )
    assert calls == [str(fixture_id)] and "очередь" in transport.sent[0]["text"]


async def test_backend_client_predictions_and_analyze_contract():
    run = detail()
    captured = []

    def handler(request):
        captured.append(request)
        if request.method == "POST":
            return httpx.Response(
                202,
                json={
                    "run_id": str(run.id),
                    "job_id": str(uuid.uuid4()),
                    "status": "QUEUED",
                    "already_queued": False,
                    "requested_identity": "a" * 64,
                },
            )
        if request.url.path.endswith(str(run.id)):
            return httpx.Response(200, json=run.model_dump(mode="json"))
        return httpx.Response(200, json=[run.model_dump(mode="json")])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        backend = BackendClient("https://synthetic.invalid", client=http)
        assert (await backend.list_predictions())[0].id == run.id
        assert await backend.get_prediction(str(run.id)) == run
        assert (await backend.analyze_fixture(str(run.fixture_id))).run_id == run.id
    assert len(captured) == 3 and captured[0].url.params["role"] == "PRIMARY"


async def test_backend_error_has_no_secret_or_remote_body():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(500, text="SYNTHETIC_SECRET"))
    ) as http:
        backend = BackendClient("https://synthetic.invalid", client=http)
        with pytest.raises(BackendClientError) as caught:
            await backend.list_predictions()
        assert "SYNTHETIC_SECRET" not in str(caught.value)
