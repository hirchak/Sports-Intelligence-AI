from __future__ import annotations

import json
import math
import time
from typing import Any

import httpx
from pydantic import BaseModel

from sports_intelligence.predictions.config import ModelSpec
from sports_intelligence.predictions.identity import content_hash
from sports_intelligence.providers.llm.base import LLMError, LLMResult


class OpenAICompatibleProvider:
    """Vendor SDK-free, bounded non-streaming HTTP adapter. No tools or hidden retrieval."""

    def __init__(
        self,
        *,
        provider: str,
        api_key: str,
        base_url: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise LLMError("missing_credentials")
        self.provider = provider
        self._key = api_key
        self._url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = httpx.AsyncClient(
            timeout=timeout_seconds,
            transport=transport,
            follow_redirects=False,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _safe_text(self, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        return value.replace(self._key, "[REDACTED]")[:200]

    def _request_body(
        self,
        config: ModelSpec,
        system_prompt: str,
        payload: dict[str, Any],
        schema: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        if config.structured_mode in ("json_only", "json_object"):
            system_prompt += "\nReturn JSON matching exactly: " + json.dumps(schema)
        input_text = json.dumps(payload, separators=(",", ":"), allow_nan=False)
        body: dict[str, Any] = {"model": config.model, "stream": False}
        if config.temperature is not None:
            body["temperature"] = config.temperature
        if config.top_p is not None:
            body["top_p"] = config.top_p
        if config.api_style == "chat_completions":
            endpoint = "/chat/completions"
            body[config.token_limit_field] = config.max_output_tokens
            body["messages"] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": input_text},
            ]
            if config.structured_mode == "json_schema":
                body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "prediction",
                        "strict": True,
                        "schema": schema,
                    },
                }
            elif config.structured_mode == "json_object":
                body["response_format"] = {"type": "json_object"}
            if self.provider == "minimax":
                body["reasoning_split"] = True
        elif config.api_style == "responses":
            endpoint = "/responses"
            body.update(
                instructions=system_prompt,
                input=input_text,
                max_output_tokens=config.max_output_tokens,
                store=False,
            )
            if config.structured_mode == "json_schema":
                body["text"] = {
                    "format": {
                        "type": "json_schema",
                        "name": "prediction",
                        "strict": True,
                        "schema": schema,
                    }
                }
            elif config.structured_mode == "json_object":
                body["text"] = {"format": {"type": "json_object"}}
        else:
            endpoint = "/messages"
            body.update(
                system=system_prompt,
                max_tokens=config.max_output_tokens,
                messages=[{"role": "user", "content": input_text}],
            )
        return endpoint, body

    async def generate_structured(
        self,
        *,
        task_type: str,
        config: ModelSpec,
        system_prompt: str,
        payload: dict[str, Any],
        output_schema: type[BaseModel],
        request_id: str,
    ) -> LLMResult:
        endpoint, body = self._request_body(
            config,
            system_prompt,
            payload,
            output_schema.model_json_schema(),
        )
        headers = {"Authorization": f"Bearer {self._key}", "User-Agent": "sports-intelligence/0.7"}
        if config.api_style == "messages":
            headers["x-api-key"] = self._key
            headers["anthropic-version"] = "2023-06-01"
        if self.provider == "opencode_go":
            headers["x-opencode-session"] = request_id
        started = time.monotonic()
        try:
            response = await self._client.post(
                self._url + endpoint,
                headers=headers,
                json=body,
                timeout=self._timeout,
            )
        except httpx.TimeoutException:
            raise LLMError("timeout", retryable=True) from None
        except httpx.HTTPError:
            raise LLMError("transport", retryable=True) from None
        latency = int((time.monotonic() - started) * 1000)
        status = response.status_code
        if status in (401, 403):
            raise LLMError("auth", status_code=status)
        if status == 429:
            retry_after: float | None
            try:
                retry_after = max(0.0, float(response.headers.get("Retry-After", "0")))
                if not math.isfinite(retry_after):
                    retry_after = None
            except ValueError:
                retry_after = None
            raise LLMError(
                "rate_limit", retryable=True, status_code=status, retry_after=retry_after
            )
        if status >= 500:
            raise LLMError("server", retryable=True, status_code=status)
        if status != 200:
            raise LLMError("request_incompatible", status_code=status)
        rid = self._safe_text(response.headers.get("x-request-id"))
        # Store only a content hash, never full response headers/bodies or reasoning traces.
        raw_ref = "sha256:" + content_hash(response.text)
        try:
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("response object required")
            usage = data.get("usage") or {}
            if not isinstance(usage, dict):
                usage = {}
            actual_model = self._safe_text(data.get("model")) or config.model
            rid = rid or self._safe_text(data.get("id"))
            if config.api_style == "chat_completions":
                choice = data["choices"][0]
                text = choice["message"].get("content")
                reason = self._safe_text(choice.get("finish_reason"))
            elif config.api_style == "messages":
                text = "".join(
                    b.get("text", "") for b in data["content"] if b.get("type") == "text"
                )
                reason = self._safe_text(data.get("stop_reason"))
            else:
                text = "".join(
                    b.get("text", "")
                    for item in data.get("output", [])
                    for b in item.get("content", [])
                    if b.get("type") == "output_text"
                )
                reason = self._safe_text(data.get("status"))
            parsed = None
            error = None
            if (
                not isinstance(text, str)
                or self._key in text
                or len(text.encode()) > 100000
                or reason not in ("stop", "end_turn", "completed")
            ):
                error = "invalid_output"
            else:
                try:
                    value = json.loads(text, object_pairs_hook=_unique_keys)
                    if not isinstance(value, dict):
                        raise ValueError("output object required")
                    parsed = value
                except (ValueError, TypeError):
                    error = "invalid_output"
            return LLMResult(
                parsed_output=parsed,
                provider=self.provider,
                model=actual_model,
                latency_ms=latency,
                request_id=rid,
                input_tokens=_usage_int(usage.get("prompt_tokens", usage.get("input_tokens"))),
                output_tokens=_usage_int(
                    usage.get("completion_tokens", usage.get("output_tokens"))
                ),
                finish_reason=reason,
                raw_response_reference=raw_ref,
                error_code=error,
            )
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            return LLMResult(
                None,
                self.provider,
                config.model,
                rid,
                latency,
                raw_response_reference=raw_ref,
                error_code="invalid_output",
            )


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _usage_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


class OpenAIProvider(OpenAICompatibleProvider):
    pass


class MiniMaxProvider(OpenAICompatibleProvider):
    pass


class OpenCodeGoProvider(OpenAICompatibleProvider):
    pass
