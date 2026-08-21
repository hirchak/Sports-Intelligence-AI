from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from sports_intelligence.core.time import utc_now
from sports_intelligence.providers.base import ProviderCapabilities
from sports_intelligence.providers.dto import (
    FixtureDiscoveryResult,
    ProviderResponseMetadata,
    canonical_request_fingerprint,
)
from sports_intelligence.providers.sports.api_football import parse_fixtures_response

DEFAULT_DATASET_PATH = Path(__file__).parent / "mock_data" / "fixtures_2026-08-21.json"


class MockSportsDataProvider:
    def __init__(
        self,
        responses: dict[str, dict[str, object]] | None = None,
        provider_name: str = "mock",
    ) -> None:
        self._responses = responses
        self._provider_name = provider_name
        self._builtin: dict[str, object] | None = None

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(provider=self._provider_name, supports_fixtures_by_date=True)

    async def get_fixtures_by_date(
        self, fixture_date: date, timezone_name: str | None = None
    ) -> FixtureDiscoveryResult:
        iso = fixture_date.isoformat()
        params = {"date": iso}
        if timezone_name is not None:
            params["timezone"] = timezone_name
        retrieved_at = utc_now()
        payload = self._load(iso)
        fingerprint = canonical_request_fingerprint(self._provider_name, "fixtures_by_date", params)
        if payload is None:
            return FixtureDiscoveryResult(
                metadata=ProviderResponseMetadata(
                    provider=self._provider_name,
                    endpoint_family="fixtures_by_date",
                    request_fingerprint=fingerprint,
                    retrieved_at=retrieved_at,
                    results_count=0,
                ),
            )
        result = parse_fixtures_response(
            payload, retrieved_at=retrieved_at, provider=self._provider_name
        )
        result.metadata.request_fingerprint = fingerprint
        return result

    async def aclose(self) -> None:
        return None

    def _load(self, iso: str) -> dict[str, object] | None:
        if self._responses is not None:
            return self._responses.get(iso)
        if self._builtin is None:
            self._builtin = json.loads(DEFAULT_DATASET_PATH.read_text())
        if iso in _DEFAULT_DATASET_DATES:
            return self._builtin
        return None


_DEFAULT_DATASET_DATES = frozenset({"2026-08-21"})
