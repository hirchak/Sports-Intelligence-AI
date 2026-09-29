from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

AppEnv = Literal["mock", "sandbox", "live_local"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        env_ignore_empty=True,
    )

    app_env: AppEnv = "mock"
    app_timezone: str = "Europe/Warsaw"
    log_level: str = "INFO"

    database_url: str = (
        "postgresql+asyncpg://sports:sports_dev_password@localhost:5433/sports_intel"
    )
    redis_url: str = "redis://localhost:6380/0"
    celery_broker_url: str = "redis://localhost:6380/0"
    celery_result_backend: str = "redis://localhost:6380/1"

    telegram_bot_token: str = ""
    telegram_allowed_user_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)
    bot_backend_base_url: str = "http://localhost:8000"

    # --- M4: scheduler, freshness, quota, odds ---
    scheduler_enabled: bool = False
    scheduler_discovery_morning_hour: int = 9
    scheduler_discovery_morning_minute: int = 0
    scheduler_discovery_refresh_hour: int = 13
    scheduler_discovery_refresh_minute: int = 0
    scheduler_pre_match_scan_enabled: bool = False
    scheduler_pre_match_scan_cron: str = "*/15"

    freshness_standings_seconds: int = 12 * 3600
    freshness_team_statistics_seconds: int = 12 * 3600
    freshness_team_form_seconds: int = 6 * 3600
    freshness_availability_seconds: int = 4 * 3600
    freshness_lineups_seconds: int = 24 * 3600
    freshness_odds_seconds: int = 2 * 3600
    freshness_prematch_odds_seconds: int = 30 * 60
    freshness_prematch_availability_seconds: int = 60 * 60
    freshness_research_seconds: int = 6 * 3600
    freshness_prematch_research_seconds: int = 90 * 60

    lineup_window_t_minutes: Annotated[list[int], NoDecode] = Field(
        default_factory=lambda: [120, 60, 20]
    )

    quota_provider_daily_limit_default: int = 100
    quota_provider_minute_limit_default: int = 10
    quota_reserve_p0_calls: int = 20
    quota_degrade_normal_remaining_pct: int = 50
    quota_degrade_conserve_remaining_pct: int = 25
    quota_degrade_critical_remaining_pct: int = 10

    redis_lock_default_ttl_seconds: int = 120
    redis_lock_acquire_timeout_seconds: float = 5.0

    odds_provider_base_url: str = "https://api.the-odds-api.com/v4"
    odds_provider_regions: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["eu"])
    odds_provider_markets: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["h2h", "double_chance", "totals", "btts"]
    )

    sports_provider: str = "mock"
    sports_api_key: str = ""
    api_football_base_url: str = "https://v3.football.api-sports.io"
    leagues_config_path: str = "config/leagues.yaml"
    odds_provider: str = ""
    odds_api_key: str = ""
    # Explicit intentional mock override for non-mock environments.
    # MOCK odds are NEVER used silently when credentials are missing.
    odds_allow_mock_override: bool = False
    search_provider: str = ""
    search_api_key: str = ""
    research_enabled: bool = True
    research_allow_mock_override: bool = False
    research_max_queries_per_fixture: int = 6
    research_max_results_per_query: int = 5
    tavily_base_url: str = "https://api.tavily.com"

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

    @field_validator("lineup_window_t_minutes", mode="before")
    @classmethod
    def parse_lineup_window(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            return [int(part) for part in stripped.split(",") if part.strip()]
        return value

    @field_validator("odds_provider_regions", "odds_provider_markets", mode="before")
    @classmethod
    def parse_csv_str(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            return [part.strip() for part in stripped.split(",") if part.strip()]
        return value

    @model_validator(mode="after")
    def validate_mode_requirements(self) -> Settings:
        if self.app_env == "mock":
            return self
        missing: list[str] = []
        if self.sports_provider and self.sports_provider != "mock" and not self.sports_api_key:
            missing.append("SPORTS_API_KEY")
        if self.odds_provider and self.odds_provider != "mock" and not self.odds_api_key:
            missing.append("ODDS_API_KEY")
        if (
            self.research_enabled
            and self.search_provider
            and self.search_provider != "mock"
            and not self.search_api_key
        ):
            missing.append("SEARCH_API_KEY")
        if self.llm_provider and self.llm_provider != "mock" and not self.llm_api_key:
            missing.append("LLM_API_KEY")
        if missing:
            raise ValueError(f"APP_ENV={self.app_env} requires: {', '.join(missing)}")
        return self

    @property
    def is_mock_mode(self) -> bool:
        return self.app_env == "mock"

    @property
    def odds_capability_enabled(self) -> bool:
        """Odds collection is enabled only when a REAL provider is
        configured (or MOCK is explicitly permitted).

        APP_ENV=mock + empty/mock → mock allowed.
        APP_ENV=sandbox/live_local + empty → DISABLED (never silent mock).
        APP_ENV=sandbox/live_local + mock → only with explicit override.
        """
        name = (self.odds_provider or "").strip().lower()
        if self.app_env == "mock":
            return name in ("", "mock") or name in ("the_odds_api", "theoddsapi")
        if self.odds_allow_mock_override and name == "mock":
            return True
        return name in ("the_odds_api", "theoddsapi") and bool(self.odds_api_key)

    @property
    def research_capability_enabled(self) -> bool:
        """Web research is enabled only when research_enabled is True and
        a real provider is configured (or MOCK is explicitly permitted).

        APP_ENV=mock + empty/mock → mock allowed.
        APP_ENV=sandbox/live_local + empty → DISABLED (never silent mock).
        APP_ENV=sandbox/live_local + mock → only with explicit override.
        """
        if not self.research_enabled:
            return False
        name = (self.search_provider or "").strip().lower()
        if self.app_env == "mock":
            return name in ("", "mock", "tavily")
        if self.research_allow_mock_override and name == "mock":
            return True
        return name == "tavily" and bool(self.search_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
