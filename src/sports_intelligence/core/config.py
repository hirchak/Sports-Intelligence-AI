from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["mock", "sandbox", "live_local"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        case_sensitive=False,
    )

    app_env: AppEnv = "mock"
    app_timezone: str = "Europe/Warsaw"
    log_level: str = "INFO"

    database_url: str = (
        "postgresql+asyncpg://sports:sports_dev_password@localhost:5433/sports_intel"
    )
    redis_url: str = "redis://localhost:6380/0"

    telegram_bot_token: str = ""
    telegram_allowed_user_ids: list[int] = Field(default_factory=list)

    sports_provider: str = ""
    sports_api_key: str = ""
    odds_provider: str = ""
    odds_api_key: str = ""
    search_provider: str = ""
    search_api_key: str = ""

    llm_provider: str = ""
    llm_api_key: str = ""
    llm_base_url: str = ""
    predictor_model: str = ""
    research_model: str = ""
    improvement_model: str = ""

    default_min_odds: float = 1.30
    default_min_model_probability: float = 0.55
    default_min_edge: float = 0.05

    @field_validator("app_env", mode="before")
    @classmethod
    def normalize_app_env(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("telegram_allowed_user_ids", mode="before")
    @classmethod
    def parse_user_ids(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            return [int(part) for part in stripped.split(",") if part.strip()]
        return value

    @model_validator(mode="after")
    def validate_mode_requirements(self) -> Settings:
        if self.app_env == "mock":
            return self
        missing: list[str] = []
        if self.sports_provider and not self.sports_api_key:
            missing.append("SPORTS_API_KEY")
        if self.odds_provider and not self.odds_api_key:
            missing.append("ODDS_API_KEY")
        if self.search_provider and not self.search_api_key:
            missing.append("SEARCH_API_KEY")
        if self.llm_provider and not self.llm_api_key:
            missing.append("LLM_API_KEY")
        if missing:
            raise ValueError(f"APP_ENV={self.app_env} requires: {', '.join(missing)}")
        return self

    @property
    def is_mock_mode(self) -> bool:
        return self.app_env == "mock"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
