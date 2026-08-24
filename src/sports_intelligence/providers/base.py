from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

from sports_intelligence.providers.dto import (
    FixtureDiscoveryResult,
    ProviderAvailabilityResult,
    ProviderCompletedFixturesResult,
    ProviderLineupsResult,
    ProviderStandingsResult,
    ProviderTeamStatisticsResult,
)


@dataclass(frozen=True)
class ProviderCapabilities:
    provider: str
    supports_fixtures_by_date: bool = True
    supports_fixture_ids_batch: bool = False
    supports_standings: bool = False
    supports_team_statistics: bool = False
    supports_availability: bool = False
    supports_lineups: bool = False
    supports_completed_fixtures: bool = False


@runtime_checkable
class SportsDataProvider(Protocol):
    """Typed provider surface for discovery + M4 collection categories.

    Implementations MUST return provider-shaped real data. Canned MOCK
    payloads are allowed ONLY inside the mock provider implementation.
    """

    @property
    def capabilities(self) -> ProviderCapabilities: ...

    async def get_fixtures_by_date(
        self, fixture_date: date, timezone_name: str | None = None
    ) -> FixtureDiscoveryResult: ...

    async def get_standings(
        self, *, provider_league_id: int, season: int | None
    ) -> ProviderStandingsResult: ...

    async def get_team_statistics(
        self, *, provider_team_id: int, provider_league_id: int, season: int | None
    ) -> ProviderTeamStatisticsResult: ...

    async def get_availability(self, *, provider_fixture_id: int) -> ProviderAvailabilityResult:
        """Single request per fixture; the result carries BOTH teams."""
        ...

    async def get_lineups(self, *, provider_fixture_id: int) -> ProviderLineupsResult:
        """Single request per fixture; result carries BOTH teams plus an
        explicit publication state (absence ≠ empty lineup)."""
        ...

    async def get_completed_fixtures(
        self, *, provider_team_id: int, last_n: int
    ) -> ProviderCompletedFixturesResult: ...

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
