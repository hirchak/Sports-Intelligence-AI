from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from sports_intelligence.core.config import Settings

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for field_name in Settings.model_fields:
        monkeypatch.delenv(field_name.upper(), raising=False)
    for compose_var in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"):
        monkeypatch.delenv(compose_var, raising=False)


def write_dotenv(tmp_path: Path, content: str) -> Path:
    env_file = tmp_path / ".env"
    env_file.write_text(content)
    return env_file


def test_dotenv_example_loads_without_validation_error() -> None:
    settings = Settings(_env_file=REPO_ROOT / ".env.example")
    assert settings.app_env == "mock"
    assert settings.is_mock_mode
    assert settings.default_min_odds == 1.30
    assert (
        settings.database_url
        == "postgresql+asyncpg://sports:sports_dev_password@localhost:5433/sports_intel"
    )


def test_empty_telegram_user_ids_yields_empty_list(tmp_path: Path) -> None:
    env_file = write_dotenv(tmp_path, "APP_ENV=mock\nTELEGRAM_ALLOWED_USER_IDS=\n")
    settings = Settings(_env_file=env_file)
    assert settings.telegram_allowed_user_ids == []


def test_comma_separated_telegram_user_ids_are_parsed(tmp_path: Path) -> None:
    env_file = write_dotenv(tmp_path, "APP_ENV=mock\nTELEGRAM_ALLOWED_USER_IDS=123,456\n")
    settings = Settings(_env_file=env_file)
    assert settings.telegram_allowed_user_ids == [123, 456]


def test_mock_mode_requires_no_external_keys(tmp_path: Path) -> None:
    env_file = write_dotenv(tmp_path, "APP_ENV=mock\nLLM_PROVIDER=opencode_go\n")
    settings = Settings(_env_file=env_file)
    assert settings.is_mock_mode
    assert settings.llm_api_key == ""


def test_non_mock_configured_provider_without_key_fails(tmp_path: Path) -> None:
    env_file = write_dotenv(tmp_path, "APP_ENV=live_local\nLLM_PROVIDER=opencode_go\n")
    with pytest.raises(ValidationError):
        Settings(_env_file=env_file)


def test_compose_only_variables_do_not_break_settings(tmp_path: Path) -> None:
    env_file = write_dotenv(
        tmp_path,
        "APP_ENV=mock\nPOSTGRES_USER=sports\nPOSTGRES_PASSWORD=dev\nPOSTGRES_DB=sports_intel\n",
    )
    settings = Settings(_env_file=env_file)
    assert settings.app_env == "mock"


def test_known_field_type_validation_is_enforced(tmp_path: Path) -> None:
    env_file = write_dotenv(tmp_path, "APP_ENV=mock\nDEFAULT_MIN_ODDS=not-a-number\n")
    with pytest.raises(ValidationError):
        Settings(_env_file=env_file)
