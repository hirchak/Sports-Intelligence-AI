from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Protocol

from sports_intelligence.context.models import MatchContextV1
from sports_intelligence.predictions.config import ModelSpec, PredictionPolicy
from sports_intelligence.predictions.contracts import PredictionOutput, Variant
from sports_intelligence.predictions.projection import project_context
from sports_intelligence.predictions.validator import PredictionValidationError, validate_prediction
from sports_intelligence.providers.llm.base import LLMError, LLMProvider, LLMResult


class AttemptObserver(Protocol):
    async def reserve(self, config: ModelSpec, purpose: str) -> str: ...
    async def finish(
        self, attempt: str, result: LLMResult | None, error: LLMError | None
    ) -> None: ...


class NullObserver:
    async def reserve(self, config: ModelSpec, purpose: str) -> str:
        return "offline"

    async def finish(self, attempt: str, result: LLMResult | None, error: LLMError | None) -> None:
        pass


@dataclass(frozen=True)
class EngineOutcome:
    status: str
    output: PredictionOutput | None = None
    result: LLMResult | None = None
    config: ModelSpec | None = None
    reason: str | None = None
    audit: tuple[str, ...] = field(default_factory=tuple)


class PredictionEngine:
    def __init__(
        self,
        provider_factory: Callable[[ModelSpec], LLMProvider],
        policy: PredictionPolicy,
        *,
        observer: AttemptObserver | None = None,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.factory = provider_factory
        self.policy = policy
        self.observer = observer or NullObserver()
        self.sleeper = sleeper

    async def predict(
        self,
        *,
        context: MatchContextV1,
        context_hash: str,
        prompt: str,
        configs: tuple[ModelSpec, ...],
        variant: Variant,
        task_type: str,
        request_id: str,
        fallback_errors: tuple[str, ...],
    ) -> EngineOutcome:
        if (
            not context.data_quality.can_predict
            or context.data_quality.overall_score < self.policy.min_data_quality
        ):
            return EngineOutcome("ABSTAINED", reason="data_quality_prediction_forbidden")
        if context.forecast_phase not in ("MORNING", "PREMATCH"):
            return EngineOutcome("ABSTAINED", reason="unsupported_forecast_phase")
        if datetime.fromisoformat(context.as_of) >= datetime.fromisoformat(
            context.fixture_identity.kickoff_at
        ) or context.fixture_identity.status in ("FT", "AET", "PEN", "CANC", "PST", "ABD"):
            return EngineOutcome("ABSTAINED", reason="context_not_prematch_eligible")
        payload_context = project_context(context, variant)
        payload: dict[str, Any] = {"context": payload_context, "context_hash": context_hash}
        if len(json.dumps(payload).encode()) > self.policy.max_input_bytes:
            return EngineOutcome("ABSTAINED", reason="context_input_budget_exceeded")
        base_payload = payload.copy()
        audit: list[str] = []
        repair_used = False
        last_error = "no_model_config"
        last_result: LLMResult | None = None
        last_config: ModelSpec | None = None
        for route_index, config in enumerate(configs):
            if route_index:
                audit.append(f"fallback:{config.provider}:{config.model}:after:{last_error}")
            payload = base_payload.copy()
            last_config, last_result = config, None
            try:
                provider = self.factory(config)
            except LLMError as exc:
                return EngineOutcome("FAILED", config=config, reason=exc.code, audit=tuple(audit))
            try:
                repair = False
                while True:
                    purpose = "repair" if repair else "initial"
                    result, error = await self._call(
                        provider,
                        config,
                        prompt,
                        payload,
                        task_type,
                        request_id,
                        purpose,
                    )
                    if result is not None:
                        last_result, last_config = result, config
                    if error is not None:
                        last_error = error.code
                        break
                    assert result is not None
                    try:
                        if result.error_code or result.parsed_output is None:
                            raise PredictionValidationError("invalid_structured_json")
                        output = validate_prediction(
                            result.parsed_output,
                            fixture_id=context.fixture_id,
                            context_hash=context_hash,
                            phase=context.forecast_phase,
                            payload=payload_context,
                            can_predict=context.data_quality.can_predict,
                        )
                        # A different provider cannot impersonate the configured adapter.
                        if result.provider != config.provider:
                            raise PredictionValidationError("provider_identity_mismatch")
                        return EngineOutcome(
                            "ABSTAINED" if output.abstain else "SUCCEEDED",
                            output,
                            result,
                            config,
                            output.abstain_reason,
                            tuple(audit),
                        )
                    except PredictionValidationError as exc:
                        last_error = "invalid_output"
                        audit.append(f"validation:{str(exc)}")
                        if repair_used:
                            break
                        repair_used = repair = True
                        audit.append("structured_repair:1")
                        # No unsafe raw invalid output is echoed; exact original context + schema.
                        payload = {
                            **payload,
                            "repair_instruction": {
                                "attempt": 1,
                                "validation_error": str(exc),
                                "instruction": "Reissue corrected schema JSON.",
                            },
                        }
            finally:
                await provider.aclose()
            if last_error not in fallback_errors:
                break
        return EngineOutcome(
            "FAILED",
            result=last_result,
            config=last_config,
            reason=last_error,
            audit=tuple(audit),
        )

    async def _call(
        self,
        provider: LLMProvider,
        config: ModelSpec,
        prompt: str,
        payload: dict[str, Any],
        task_type: str,
        request_id: str,
        purpose: str,
    ) -> tuple[LLMResult | None, LLMError | None]:
        retries = 0 if purpose == "repair" else self.policy.max_retries
        for retry in range(retries + 1):
            try:
                attempt = await self.observer.reserve(config, purpose)
            except LLMError as exc:
                return None, exc
            result: LLMResult | None = None
            error: LLMError | None = None
            try:
                result = await asyncio.wait_for(
                    provider.generate_structured(
                        task_type=task_type,
                        config=config,
                        system_prompt=prompt,
                        payload=payload,
                        output_schema=PredictionOutput,
                        request_id=request_id,
                    ),
                    timeout=self.policy.timeout_seconds,
                )
            except TimeoutError:
                error = LLMError("timeout", retryable=True)
            except LLMError as exc:
                error = exc
            except Exception:
                error = LLMError("provider_implementation_failure")
            if result is not None and result.parsed_output is not None and not result.error_code:
                try:
                    context_payload = payload["context"]
                    validate_prediction(
                        result.parsed_output,
                        fixture_id=context_payload["fixture_id"],
                        context_hash=payload["context_hash"],
                        phase=context_payload["forecast_phase"],
                        payload=context_payload,
                        can_predict=context_payload["data_quality"]["can_predict"],
                    )
                    if result.provider != config.provider:
                        raise PredictionValidationError("provider_identity_mismatch")
                except PredictionValidationError:
                    result = replace(result, error_code="invalid_output")
            await self.observer.finish(attempt, result, error)
            if error is None:
                return result, None
            if not error.retryable or retry == retries:
                return None, error
            delay = min(
                error.retry_after if error.retry_after is not None else 2**retry,
                self.policy.max_retry_delay_seconds,
            )
            await self.sleeper(delay)
        raise AssertionError("unreachable retry state")
