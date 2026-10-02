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
        hide_input_in_errors=True,
    )

    app_env: AppEnv = "mock"
    app_timezone: str = "Europe/Warsaw"
    log_level: str = "INFO"
    production_like: bool = False
    worker_concurrency: int = Field(default=2, ge=1, le=16)

    database_url: str = (
        "postgresql+asyncpg://sports:sports_dev_password@localhost:5433/sports_intel"
    )
    redis_url: str = "redis://localhost:6380/0"
    celery_broker_url: str = "redis://localhost:6380/0"
    celery_result_backend: str = "redis://localhost:6380/1"

    telegram_bot_token: str = Field(default="", repr=False)
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

    result_scan_enabled: bool = False
    result_scan_interval_seconds: int = Field(default=3600, ge=900)
    result_expected_finish_minutes: int = Field(default=120, ge=90)
    result_grace_minutes: int = Field(default=30, ge=0)
    result_lookback_days: int = Field(default=7, ge=1, le=365)
    result_retry_limit: int = Field(default=2, ge=0, le=3)
    evaluation_epsilon: float = Field(
        default=1e-15, ge=2.220446049250313e-16, lt=0.01, allow_inf_nan=False
    )
    evaluation_calibration_boundaries: list[float] = Field(
        default_factory=lambda: [i / 10 for i in range(11)]
    )
    evaluation_default_days: int = Field(default=30, ge=1, le=3650)

    sports_provider: str = "mock"
    sports_api_key: str = Field(default="", repr=False)
    api_football_base_url: str = "https://v3.football.api-sports.io"
    leagues_config_path: str = "config/leagues.yaml"
    odds_provider: str = ""
    odds_api_key: str = Field(default="", repr=False)
    # Explicit intentional mock override for non-mock environments.
    # MOCK odds are NEVER used silently when credentials are missing.
    odds_allow_mock_override: bool = False
    search_provider: str = ""
    search_api_key: str = Field(default="", repr=False)
    research_enabled: bool = True
    research_allow_mock_override: bool = False
    research_max_queries_per_fixture: int = 6
    research_max_results_per_query: int = 5
    research_claim_extraction_enabled: bool = True
    research_provider_error_retry_seconds: int = 15 * 60
    research_max_retry_after_seconds: int = 30
    tavily_base_url: str = "https://api.tavily.com"

    llm_routes_path: str = "config/llm.yaml"
    prediction_prompt_path: str = "prompts/predictor/1.0.0.txt"
    prediction_auto_enabled: bool = False
    prediction_auto_variant: Literal["LLM_WITH_ODDS", "LLM_WITHOUT_ODDS"] = "LLM_WITH_ODDS"
    llm_openai_api_key: str = Field(default="", repr=False)
    llm_minimax_api_key: str = Field(default="", repr=False)
    llm_opencode_go_api_key: str = Field(default="", repr=False)
    # Current Go docs target coding traffic. Runtime activation is an explicit separate gate.
    llm_opencode_go_runtime_allowed: bool = False
    llm_provider: str = ""
    llm_api_key: str = Field(default="", repr=False)
    llm_base_url: str = ""
    predictor_model: str = ""
    research_model: str = ""
    improvement_model: str = ""
    experiment_candidate_prompt_path: str = "prompts/experiments/1.1.0.txt"
    experiment_live_enabled: bool = False
    improvement_prompt_path: str = "prompts/improvement/1.0.0.txt"
    improvement_schedule_enabled: bool = False
    improvement_live_enabled: bool = False
    improvement_max_calls_per_day: int = Field(default=10, ge=0, le=100)

    default_min_odds: float = 1.30
    default_min_model_probability: float = 0.55
    default_min_edge: float = 0.05

    # M6.1 Data Quality Policy
    quality_weight_fixture_identity: float = 0.15
    quality_weight_form: float = 0.20
    quality_weight_season_stats: float = 0.15
    quality_weight_availability: float = 0.15
    quality_weight_odds: float = 0.15
    quality_weight_research: float = 0.10
    quality_weight_lineups: float = 0.10
    quality_min_predict_score: float = 0.65
    quality_band_excellent_min: float = 0.90
    quality_band_good_min: float = 0.80
    quality_band_usable_min: float = 0.65
    quality_staleness_penalty: float = 0.05
    quality_max_staleness_penalty: float = 0.20

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
    def validate_operational_safety(self) -> Settings:
        if self.production_like and self.log_level.upper() == "DEBUG":
            raise ValueError("PRODUCTION_LIKE forbids DEBUG logging")
        if any(user_id <= 0 for user_id in self.telegram_allowed_user_ids):
            raise ValueError("TELEGRAM_ALLOWED_USER_IDS requires positive user IDs")
        return self

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
        if (
            self.llm_provider
            and self.llm_provider != "mock"
            and not (
                self.llm_api_key
                or {
                    "openai": self.llm_openai_api_key,
                    "openai_compatible": self.llm_openai_api_key,
                    "minimax": self.llm_minimax_api_key,
                    "opencode_go": self.llm_opencode_go_api_key,
                }.get(self.llm_provider)
            )
        ):
            missing.append("LLM_API_KEY")
        if missing:
            raise ValueError(f"APP_ENV={self.app_env} requires: {', '.join(missing)}")
        return self

    @model_validator(mode="after")
    def validate_quality_settings(self) -> Settings:
        weights = [
            ("fixture_identity", self.quality_weight_fixture_identity),
            ("form", self.quality_weight_form),
            ("season_stats", self.quality_weight_season_stats),
            ("availability", self.quality_weight_availability),
            ("odds", self.quality_weight_odds),
            ("research", self.quality_weight_research),
            ("lineups", self.quality_weight_lineups),
        ]
        for name, w in weights:
            if w < 0:
                raise ValueError(f"Quality weight '{name}' must be >= 0, got {w}")
        total = sum(w for _, w in weights)
        if total <= 0:
            raise ValueError(f"Total quality weight must be > 0, got {total}")
        if not (0.0 <= self.quality_min_predict_score <= 1.0):
            raise ValueError(
                "quality_min_predict_score must be between 0 and 1, "
                f"got {self.quality_min_predict_score}"
            )
        usable = self.quality_band_usable_min
        good = self.quality_band_good_min
        excellent = self.quality_band_excellent_min
        if not (0.0 <= usable <= good <= excellent <= 1.0):
            raise ValueError(
                "Quality band thresholds must satisfy 0 <= usable <= good <= excellent <= 1, "
                f"got usable={usable}, good={good}, excellent={excellent}"
            )
        if self.quality_staleness_penalty < 0:
            raise ValueError(
                f"quality_staleness_penalty must be >= 0, got {self.quality_staleness_penalty}"
            )
        if not (0.0 <= self.quality_max_staleness_penalty <= 1.0):
            raise ValueError(
                "quality_max_staleness_penalty must be between 0 and 1, "
                f"got {self.quality_max_staleness_penalty}"
            )
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
