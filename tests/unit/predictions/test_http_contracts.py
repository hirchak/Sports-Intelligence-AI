from __future__ import annotations

import json

import httpx
import pytest

from m7_fakes import make_context, valid_output
from sports_intelligence.predictions.config import ModelSpec, PredictionPolicy
from sports_intelligence.predictions.contracts import PredictionOutput, Variant
from sports_intelligence.predictions.engine import PredictionEngine
from sports_intelligence.providers.llm.base import LLMError
from sports_intelligence.providers.llm.http import (
    MiniMaxProvider,
    OpenAICompatibleProvider,
    OpenCodeGoProvider,
)

SECRET = "synthetic-contract-key-not-real"


def adapter(handler, provider="openai"):
    cls = {"minimax": MiniMaxProvider, "opencode_go": OpenCodeGoProvider}.get(
        provider, OpenAICompatibleProvider
    )
    return cls(
        provider=provider,
        api_key=SECRET,
        base_url="https://synthetic.invalid/v1",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )


async def generate(provider, config=None):
    context = make_context()
    return await provider.generate_structured(
        task_type="prediction_primary",
        config=config or ModelSpec(provider="openai", model="configured"),
        system_prompt="Synthetic JSON",
        payload={"context": context.model_dump(), "context_hash": "a" * 64},
        output_schema=PredictionOutput,
        request_id="stable-session",
    )


def response_payload():
    return {
        "id": "response-id",
        "model": "actual-model-version",
        "choices": [
            {
                "message": {"content": json.dumps(valid_output(make_context()))},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 123, "completion_tokens": 45},
    }


async def test_native_output_usage_request_id_finish_reason_schema_and_no_tools():
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(
            200, json=response_payload(), headers={"x-request-id": "header-request-id"}
        )

    provider = adapter(handler)
    result = await generate(provider)
    await provider.aclose()
    assert (
        result.input_tokens == 123
        and result.output_tokens == 45
        and result.request_id == "header-request-id"
    )
    assert (
        result.model == "actual-model-version"
        and result.finish_reason == "stop"
        and result.parsed_output
    )
    body = json.loads(captured[0].content)
    assert (
        "tools" not in body and "temperature" not in body and body["max_completion_tokens"] == 1500
    )
    schema = body["response_format"]["json_schema"]
    assert schema["strict"] and schema["schema"]["additionalProperties"] is False
    assert set(schema["schema"]["required"]) == set(schema["schema"]["properties"])
    assert result.raw_response_reference.startswith("sha256:") and SECRET not in repr(result)


@pytest.mark.parametrize(
    "status,code,retryable",
    [
        (401, "auth", False),
        (403, "auth", False),
        (429, "rate_limit", True),
        (500, "server", True),
        (503, "server", True),
        (400, "request_incompatible", False),
        (302, "request_incompatible", False),
    ],
)
async def test_http_error_classification_secret_safe(status, code, retryable):
    provider = adapter(lambda _: httpx.Response(status, text=SECRET, headers={"Retry-After": "2"}))
    with pytest.raises(LLMError) as caught:
        await generate(provider)
    await provider.aclose()
    assert (
        caught.value.code == code
        and caught.value.retryable == retryable
        and SECRET not in str(caught.value)
    )
    if status == 429:
        assert caught.value.retry_after == 2


@pytest.mark.parametrize("error", [httpx.ReadTimeout, httpx.ConnectError])
async def test_transport_timeout_normalized(error):
    def handler(request):
        raise error(SECRET, request=request)

    provider = adapter(handler)
    with pytest.raises(LLMError) as caught:
        await generate(provider)
    await provider.aclose()
    assert caught.value.retryable and SECRET not in str(caught.value)


@pytest.mark.parametrize(
    "invalid", ["broken JSON", "[]", '{"home": 0.1, "home": 0.9}', "<think>text</think>{}", SECRET]
)
async def test_bad_json_no_regex_and_duplicate_keys_rejected(invalid):
    payload = response_payload()
    payload["choices"][0]["message"]["content"] = invalid
    provider = adapter(lambda _: httpx.Response(200, json=payload))
    result = await generate(provider)
    await provider.aclose()
    assert result.parsed_output is None and result.error_code == "invalid_output"
    assert result.input_tokens == 123 and SECRET not in repr(result)


async def test_response_envelope_bad_json_is_repairable():
    provider = adapter(lambda _: httpx.Response(200, text="not-json"))
    result = await generate(provider)
    await provider.aclose()
    assert result.error_code == "invalid_output"


@pytest.mark.parametrize(
    "provider_name,style",
    [
        ("minimax", "chat_completions"),
        ("opencode_go", "messages"),
        ("opencode_go", "responses"),
        ("opencode_go", "chat_completions"),
    ],
)
async def test_minimax_and_go_endpoint_styles(provider_name, style):
    captured = []
    raw = valid_output(make_context())

    def handler(request):
        captured.append(request)
        if style == "messages":
            payload = {
                "id": "id",
                "model": "actual",
                "content": [{"type": "text", "text": json.dumps(raw)}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 12, "output_tokens": 13},
            }
        elif style == "responses":
            payload = {
                "id": "id",
                "model": "actual",
                "output": [{"content": [{"type": "output_text", "text": json.dumps(raw)}]}],
                "status": "completed",
                "usage": {"input_tokens": 12, "output_tokens": 13},
            }
        else:
            payload = response_payload()
        return httpx.Response(200, json=payload)

    provider = adapter(handler, provider_name)
    spec = ModelSpec(
        provider=provider_name, model="configured", api_style=style, structured_mode="json_only"
    )
    result = await generate(provider, spec)
    await provider.aclose()
    assert result.parsed_output and result.error_code is None
    expected_path = {
        "chat_completions": "chat/completions",
        "messages": "messages",
        "responses": "responses",
    }[style]
    assert captured[0].url.path.endswith(expected_path)
    body = json.loads(captured[0].content)
    assert "tools" not in body
    if provider_name == "opencode_go":
        assert captured[0].headers["x-opencode-session"] == "stable-session"
    if provider_name == "minimax":
        assert body["reasoning_split"] is True and "response_format" not in body


async def test_http_engine_retry_and_repair_bounded():
    calls = []
    context = make_context()

    def handler(request):
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return httpx.Response(503)
        data = response_payload()
        data["choices"][0]["message"]["content"] = "{}"
        return httpx.Response(200, json=data)

    provider = adapter(handler)
    engine = PredictionEngine(
        lambda _: provider, PredictionPolicy(max_retries=1, max_retry_delay_seconds=0)
    )
    result = await engine.predict(
        context=context,
        context_hash="a" * 64,
        prompt="Synthetic",
        configs=(ModelSpec(provider="openai", model="configured"),),
        variant=Variant.WITH_ODDS,
        task_type="prediction_primary",
        request_id="id",
        fallback_errors=(),
    )
    assert result.status == "FAILED" and len(calls) == 3
    assert "repair_instruction" in json.loads(calls[2]["messages"][1]["content"])


async def test_output_truncation_rejected_even_with_valid_json():
    payload = response_payload()
    payload["choices"][0]["finish_reason"] = "length"
    provider = adapter(lambda _: httpx.Response(200, json=payload))
    result = await generate(provider)
    await provider.aclose()
    assert result.parsed_output is None and result.error_code == "invalid_output"
