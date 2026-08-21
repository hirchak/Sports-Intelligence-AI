from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from sports_intelligence.providers.sports.mock import MockSportsDataProvider

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "provider" / "api_football"
RECORDED = json.loads((FIXTURES_DIR / "fixtures_by_date.json").read_text())


async def test_mock_provider_serves_builtin_dataset_without_any_key() -> None:
    provider = MockSportsDataProvider()

    result = await provider.get_fixtures_by_date(date(2026, 8, 21))

    assert len(result.fixtures) > 0
    assert result.metadata.provider == "mock"
    assert result.raw_payload is not None


async def test_mock_provider_returns_empty_result_for_unknown_date() -> None:
    provider = MockSportsDataProvider()

    result = await provider.get_fixtures_by_date(date(2030, 1, 1))

    assert result.fixtures == []
    assert result.metadata.request_fingerprint == "mock:fixtures_by_date:date=2030-01-01"


async def test_mock_provider_uses_injected_responses() -> None:
    provider = MockSportsDataProvider(responses={"2026-09-01": RECORDED})

    result = await provider.get_fixtures_by_date(date(2026, 9, 1))

    assert len(result.fixtures) == 4
    assert result.metadata.provider == "mock"


async def test_mock_provider_aclose_is_safe_noop() -> None:
    provider = MockSportsDataProvider()
    await provider.aclose()
