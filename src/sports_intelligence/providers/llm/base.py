from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel

from sports_intelligence.predictions.config import ModelSpec


class LLMError(Exception):
    def __init__(
        self,
        code: str,
        *,
        retryable: bool = False,
        status_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.status_code = status_code
        self.retry_after = retry_after


@dataclass(frozen=True)
class LLMResult:
    parsed_output: dict[str, Any] | None
    provider: str
    model: str
    request_id: str | None = None
    latency_ms: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None
    raw_response_reference: str | None = None
    error_code: str | None = None
    status_code: int = 200


class LLMProvider(Protocol):
    """One physical attempt. Retry/repair/budget/ledger belong to the engine."""

    async def generate_structured(
        self,
        *,
        task_type: str,
        config: ModelSpec,
        system_prompt: str,
        payload: dict[str, Any],
        output_schema: type[BaseModel],
        request_id: str,
    ) -> LLMResult: ...

    async def aclose(self) -> None: ...
