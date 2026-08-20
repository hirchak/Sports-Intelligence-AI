from __future__ import annotations

import pytest
from pydantic import ValidationError

from sports_intelligence.core.config import Settings

BASE = {
    "_env_file": None,
    "app_env": "mock",
    "database_url": "postgresql+asyncpg://test:test@localhost:5433/sports_test",
    "redis_url": "redis://localhost:6380/0",
}


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {**BASE, **overrides}
    return Settings(**values)  # type: ignore[arg-type]


def test_mock_mode_defaults_require_no_keys() -> None:
    settings = make_settings()
    assert settings.app_env == "mock"
    assert settings.is_mock_mode
    assert settings.default_min_odds == 1.30
    assert settings.app_timezone == "Europe/Warsaw"
    assert settings.telegram_allowed_user_ids == []
    assert settings.sports_api_key == ""


def test_app_env_is_normalized_to_lowercase() -> None:
    settings = make_settings(
        app_env="LIVE_LOCAL",
        llm_provider="opencode_go",
        llm_api_key="test-key",
    )
    assert settings.app_env == "live_local"


def test_telegram_user_ids_parsed_from_comma_separated_string() -> None:
    settings = make_settings(telegram_allowed_user_ids="1, 22, 333")
    assert settings.telegram_allowed_user_ids == [1, 22, 333]


def test_telegram_user_ids_empty_string_becomes_empty_list() -> None:
    settings = make_settings(telegram_allowed_user_ids="")
    assert settings.telegram_allowed_user_ids == []


def test_live_local_requires_llm_key_when_provider_set() -> None:
    with pytest.raises(ValidationError):
        make_settings(app_env="live_local", llm_provider="opencode_go", llm_api_key="")


def test_live_local_passes_with_configured_keys() -> None:
    settings = make_settings(
        app_env="live_local",
        llm_provider="opencode_go",
        llm_api_key="test-key",
        sports_provider="api_football",
        sports_api_key="sports-key",
    )
    assert settings.app_env == "live_local"
    assert settings.llm_api_key == "test-key"


def test_mock_mode_allows_missing_keys() -> None:
    settings = make_settings(llm_provider="opencode_go", llm_api_key="")
    assert settings.is_mock_mode
