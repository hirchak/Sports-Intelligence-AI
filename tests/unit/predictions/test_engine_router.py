from __future__ import annotations

import pytest

from m7_fakes import ScriptedProvider, make_context, valid_output
from sports_intelligence.core.config import Settings
from sports_intelligence.predictions.config import (
    LLMConfig,
    ModelSpec,
    PredictionPolicy,
    Route,
    load_llm_config,
)
from sports_intelligence.predictions.contracts import Variant
from sports_intelligence.predictions.engine import PredictionEngine
from sports_intelligence.predictions.router import Health, ModelRouter
from sports_intelligence.providers.llm.base import LLMError
from sports_intelligence.providers.llm.factory import build_llm_provider
from sports_intelligence.providers.llm.mock import MockLLMProvider


@pytest.fixture
def model():
    return ModelSpec(provider="mock", model="mock-v1")


async def call_engine(provider, model, context=None, policy=None, fallbacks=()):
    context = context or make_context()
    engine = PredictionEngine(
        lambda _: provider, policy or PredictionPolicy(max_retry_delay_seconds=0)
    )
    return await engine.predict(
        context=context,
        context_hash="a" * 64,
        prompt="Synthetic",
        configs=(model, *fallbacks),
        variant=Variant.WITH_ODDS,
        task_type="prediction_primary",
        request_id="request",
        fallback_errors=("timeout", "server", "rate_limit", "invalid_output"),
    )


async def test_mock_is_deterministic_and_keyless(model):
    provider = MockLLMProvider()
    context = make_context()
    a, b = await call_engine(provider, model, context), await call_engine(provider, model, context)
    assert a.output == b.output and a.status == "SUCCEEDED"
    assert a.output.risk_flags == ["synthetic_mock"]


async def test_invalid_output_repaired_once(model):
    context = make_context()
    provider = ScriptedProvider([{}, valid_output(context)])
    outcome = await call_engine(provider, model, context)
    assert outcome.status == "SUCCEEDED" and len(provider.calls) == 2 and provider.closed
    assert provider.calls[1]["repair_instruction"]["attempt"] == 1
    assert outcome.audit.count("structured_repair:1") == 1


async def test_second_invalid_response_fails(model):
    provider = ScriptedProvider([{}, {}, {}])
    outcome = await call_engine(provider, model)
    assert outcome.status == "FAILED" and len(provider.calls) == 2
    assert outcome.output is None and outcome.reason == "invalid_output"


async def test_repair_timeout_never_retried(model):
    provider = ScriptedProvider([{}, LLMError("timeout", retryable=True), {}])
    outcome = await call_engine(provider, model)
    assert outcome.status == "FAILED" and len(provider.calls) == 2


@pytest.mark.parametrize(
    "error,retryable,count",
    [
        ("timeout", True, 2),
        ("server", True, 2),
        ("rate_limit", True, 2),
        ("auth", False, 1),
        ("request_incompatible", False, 1),
    ],
)
async def test_retry_classification_bounded(model, error, retryable, count):
    provider = ScriptedProvider([LLMError(error, retryable=retryable) for _ in range(5)])
    outcome = await call_engine(provider, model)
    assert outcome.status == "FAILED" and outcome.reason == error
    assert len(provider.calls) == count


@pytest.mark.parametrize(
    "condition", ["cannot_predict", "low_score", "oversize", "postmatch", "started", "cancelled"]
)
async def test_ineligible_context_never_calls_provider(model, condition):
    context = make_context()
    data = context.model_dump()
    policy = PredictionPolicy()
    if condition == "cannot_predict":
        data["data_quality"]["can_predict"] = False
    elif condition == "low_score":
        data["data_quality"]["overall_score"] = 0.64
    elif condition == "oversize":
        policy = PredictionPolicy(max_input_bytes=1024)
    elif condition == "postmatch":
        data["forecast_phase"] = "POSTMATCH"
    elif condition == "started":
        data["fixture_identity"]["kickoff_at"] = data["as_of"]
    elif condition == "cancelled":
        data["fixture_identity"]["status"] = "CANC"
    context = type(context).model_validate(data)
    provider = ScriptedProvider([{}])
    result = await call_engine(provider, model, context, policy)
    assert result.status == "ABSTAINED" and provider.calls == []


async def test_model_abstain_is_valid_outcome(model):
    context = make_context()
    raw = valid_output(context)
    raw.update(abstain=True, abstain_reason="Insufficient evidence", probabilities=None)
    result = await call_engine(ScriptedProvider([raw]), model, context)
    assert result.status == "ABSTAINED" and result.output.abstain


async def test_fallback_actual_provider_model_audited(model):
    context = make_context()
    first = ScriptedProvider([LLMError("timeout", retryable=True)] * 2)
    second = ScriptedProvider(
        [valid_output(context)], provider="minimax", actual_model="returned-version"
    )
    alternate = ModelSpec(provider="minimax", model="configured", structured_mode="json_only")
    engine = PredictionEngine(
        lambda m: first if m.provider == "mock" else second,
        PredictionPolicy(max_retry_delay_seconds=0),
    )
    result = await engine.predict(
        context=context,
        context_hash="a" * 64,
        prompt="Synthetic",
        configs=(model, alternate),
        variant=Variant.WITH_ODDS,
        task_type="prediction_primary",
        request_id="id",
        fallback_errors=("timeout",),
    )
    assert result.status == "SUCCEEDED" and result.result.model == "returned-version"
    assert result.result.provider == "minimax" and any(
        "fallback:minimax" in a for a in result.audit
    )
    assert first.closed and second.closed


async def test_single_repair_budget_across_fallbacks(model):
    context = make_context()
    first, second = ScriptedProvider([{}, {}]), ScriptedProvider([{}, {}], provider="minimax")
    alternate = ModelSpec(provider="minimax", model="alt", structured_mode="json_only")
    engine = PredictionEngine(
        lambda m: first if m.provider == "mock" else second, PredictionPolicy()
    )
    result = await engine.predict(
        context=context,
        context_hash="a" * 64,
        prompt="Synthetic",
        configs=(model, alternate),
        variant=Variant.WITH_ODDS,
        task_type="prediction_primary",
        request_id="id",
        fallback_errors=("invalid_output",),
    )
    assert result.status == "FAILED" and len(first.calls) == 2 and len(second.calls) == 1
    assert result.audit.count("structured_repair:1") == 1


async def test_without_odds_engine_payload_is_projected(model):
    context = make_context()
    provider = ScriptedProvider([valid_output(context)])
    engine = PredictionEngine(lambda _: provider, PredictionPolicy())
    result = await engine.predict(
        context=context,
        context_hash="a" * 64,
        prompt="Synthetic",
        configs=(model,),
        variant=Variant.WITHOUT_ODDS,
        task_type="prediction_primary",
        request_id="id",
        fallback_errors=(),
    )
    assert result.status == "SUCCEEDED" and "market_snapshot" not in provider.calls[0]["context"]


def test_router_deterministic_health_and_manual_override(model):
    fallback = model.model_copy(update={"model": "alternate"})
    route = Route(primary=model, fallbacks=[fallback], quality_tier="high", budget_class="small")
    config = LLMConfig(
        routes={"prediction_primary": route, "prediction_challenger": route},
        manual_override_routes=("prediction_challenger",),
    )
    router = ModelRouter(config)
    one, two = router.select("prediction_primary"), router.select("prediction_primary")
    assert one == two and one.selected == model
    alternate = router.select(
        "prediction_primary", health={("mock", "mock-v1"): Health.UNAVAILABLE}
    )
    assert alternate.selected == fallback and "UNAVAILABLE" in alternate.audit[0]
    assert (
        router.select("prediction_primary", override="prediction_challenger").route_name
        == "prediction_challenger"
    )
    for args in (
        {"override": "research_extract"},
        {"required_capabilities": ("web_search",)},
        {"quality_tier": "low"},
        {"budget_class": "large"},
    ):
        with pytest.raises(ValueError):
            router.select("prediction_primary", **args)


@pytest.mark.parametrize("env", ["sandbox", "live_local"])
def test_never_silently_mock_in_nonmock(model, env):
    settings = Settings(_env_file=None, app_env=env)
    with pytest.raises(LLMError, match="mock_forbidden"):
        build_llm_provider(settings, model, timeout_seconds=1)


@pytest.mark.parametrize("provider", ["openai", "minimax", "opencode_go", "unknown"])
def test_real_provider_gates(provider):
    config = ModelSpec(provider=provider, model="configured", structured_mode="json_only")
    settings = Settings(_env_file=None, app_env="mock")
    with pytest.raises(LLMError):
        build_llm_provider(settings, config, timeout_seconds=1)


def test_explicit_real_env_override_requires_model_and_never_mock():
    settings = Settings(
        _env_file=None,
        llm_provider="minimax",
        predictor_model="configured",
        llm_api_key="test-secret",
    )
    config = load_llm_config(settings)
    assert config.routes["prediction_primary"].primary.provider == "minimax"
    assert config.routes["prediction_primary"].primary.temperature is None
    assert config.routes["prediction_primary"].primary.structured_mode == "json_only"
    assert "test-secret" not in repr(config)
    with pytest.raises(ValueError):
        load_llm_config(Settings(_env_file=None, llm_provider="openai"))


def test_nonretryable_fallback_or_duplicate_routes_rejected(model):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Route(primary=model, fallback_errors=("auth",))
    with pytest.raises(ValidationError):
        Route(primary=model, fallbacks=[model])
