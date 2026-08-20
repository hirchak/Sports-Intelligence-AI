from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from pydantic import BaseModel

from sports_intelligence.providers.dto import FixtureDiscoveryResult


@dataclass(frozen=True)
class ProviderCapabilities:
    provider: str
    supports_fixtures_by_date: bool = True
    supports_fixture_ids_batch: bool = False


class SportsDataProvider(Protocol):
    """Typed provider surface. Extended by later milestones with typed DTOs."""

    @property
    def capabilities(self) -> ProviderCapabilities: ...

    async def get_fixtures_by_date(self, fixture_date: date) -> FixtureDiscoveryResult: ...

    async def aclose(self) -> None: ...


class OddsProvider(Protocol):
    """Minimum interface per master spec section 8.2. Not implemented (M4)."""

    async def get_odds(self, fixture_id: str, markets: list[str]) -> dict[str, Any]: ...


class SearchProvider(Protocol):
    """Minimum interface per master spec section 8.3. Not implemented (M5)."""

    async def search(self, query: str, max_results: int) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class LLMResult:
    parsed_output: BaseModel | None
    raw_response_reference: str | None
    provider: str
    model: str
    latency_ms: int
    usage: dict[str, Any] | None
    finish_reason: str | None
    request_id: str


class LLMProvider(Protocol):
    """Minimum interface per LLM router spec section 3. Not implemented (M7)."""

    async def generate_structured(
        self,
        *,
        task_type: str,
        model: str,
        system_prompt: str,
        payload: dict[str, Any],
        output_schema: type[BaseModel],
        request_id: str,
    ) -> LLMResult: ...
