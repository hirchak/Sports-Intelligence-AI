from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from pydantic import BaseModel


class SportsDataProvider(Protocol):
    """Minimum interface per master spec section 8.1. Not implemented in M0."""

    async def get_fixtures(self, date: date, league_ids: list[str]) -> list[dict[str, Any]]: ...

    async def get_fixture(self, external_fixture_id: str) -> dict[str, Any]: ...

    async def get_standings(self, league_id: str, season: str) -> dict[str, Any]: ...

    async def get_team_recent_matches(self, team_id: str, limit: int) -> list[dict[str, Any]]: ...

    async def get_head_to_head(
        self, home_team_id: str, away_team_id: str, limit: int
    ) -> list[dict[str, Any]]: ...

    async def get_injuries(self, fixture_id: str) -> list[dict[str, Any]]: ...

    async def get_lineups(self, fixture_id: str) -> list[dict[str, Any]]: ...

    async def get_team_statistics(
        self, team_id: str, league_id: str, season: str
    ) -> dict[str, Any]: ...

    async def get_result(self, fixture_id: str) -> dict[str, Any]: ...


class OddsProvider(Protocol):
    """Minimum interface per master spec section 8.2. Not implemented in M0."""

    async def get_odds(self, fixture_id: str, markets: list[str]) -> dict[str, Any]: ...


class SearchProvider(Protocol):
    """Minimum interface per master spec section 8.3. Not implemented in M0."""

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
    """Minimum interface per LLM router spec section 3. Not implemented in M0."""

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
