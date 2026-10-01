from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

import yaml
from pydantic import Field, model_validator

from sports_intelligence.core.config import Settings
from sports_intelligence.predictions.contracts import MARKETS, Role, StrictModel
from sports_intelligence.predictions.identity import fingerprint


class ModelSpec(StrictModel):
    provider: Annotated[str, Field(min_length=1, max_length=64)]
    model: Annotated[str, Field(min_length=1, max_length=128)]
    base_url: Annotated[str, Field(max_length=255)] | None = None
    api_style: Literal["chat_completions", "responses", "messages"] = "chat_completions"
    structured_mode: Literal["json_schema", "json_object", "json_only"] = "json_schema"
    temperature: Annotated[float, Field(ge=0, le=2)] | None = None
    top_p: Annotated[float, Field(ge=0, le=1)] | None = None
    max_output_tokens: Annotated[int, Field(ge=128, le=8192)] = 1500
    token_limit_field: Literal["max_tokens", "max_completion_tokens"] = "max_completion_tokens"
    capabilities: tuple[str, ...] = ("structured_output",)

    @model_validator(mode="after")
    def compatible(self) -> ModelSpec:
        if self.base_url:
            url = urlsplit(self.base_url)
            if url.scheme not in ("https", "http") or not url.hostname:
                raise ValueError("invalid LLM base URL")
            if url.username or url.password or url.query or url.fragment:
                raise ValueError("LLM base URL must not contain credentials/query/fragment")
        if self.api_style == "messages" and self.structured_mode != "json_only":
            raise ValueError("messages adapter supports JSON-only schema prompt")
        if self.provider == "minimax" and self.structured_mode != "json_only":
            raise ValueError("MiniMax uses JSON-only prompt; native schema not asserted")
        return self

    @property
    def hash(self) -> str:
        return fingerprint(self.model_dump(mode="json"))


class Route(StrictModel):
    primary: ModelSpec
    fallbacks: Annotated[list[ModelSpec], Field(max_length=3)] = Field(default_factory=list)
    quality_tier: str = "standard"
    budget_class: str = "normal"
    fallback_errors: tuple[str, ...] = (
        "timeout",
        "transport",
        "server",
        "rate_limit",
        "invalid_output",
    )

    @model_validator(mode="after")
    def bounded_fallback(self) -> Route:
        allowed = {"timeout", "transport", "server", "rate_limit", "invalid_output"}
        if set(self.fallback_errors) - allowed:
            raise ValueError("non-retryable failures cannot authorize fallback")
        configs = [self.primary, *self.fallbacks]
        if len({m.hash for m in configs}) != len(configs):
            raise ValueError("duplicate fallback model configs")
        return self


class RankingPolicy(StrictModel):
    version: str = "ranking_v1"
    allowed_markets: tuple[str, ...] = ("1x2", "double_chance", "ou_15", "ou_25", "btts")
    min_data_quality: Annotated[float, Field(ge=0, le=1)] = 0.65
    min_decimal_odds: Annotated[float, Field(gt=1)] = 1.30
    max_decimal_odds: Annotated[float, Field(gt=1)] | None = None
    min_model_probability: Annotated[float, Field(ge=0, le=1)] = 0.55
    min_edge: Annotated[float, Field(ge=-1, le=1)] = 0.05
    comparison_tolerance: Annotated[float, Field(ge=0, le=1e-6)] = 1e-12
    max_candidates: Annotated[int, Field(ge=0, le=12)] = 3
    max_odds_age_seconds: Annotated[int, Field(ge=0, le=86400)] = 7200
    league_allow: tuple[str, ...] = ()
    league_deny: tuple[str, ...] = ()

    @model_validator(mode="after")
    def valid_markets(self) -> RankingPolicy:
        if set(self.allowed_markets) - set(MARKETS.values()):
            raise ValueError("unsupported ranking markets")
        if self.max_decimal_odds is not None and self.max_decimal_odds < self.min_decimal_odds:
            raise ValueError("max odds below min odds")
        if set(self.league_allow) & set(self.league_deny):
            raise ValueError("league cannot be allowed and denied")
        return self


class PredictionPolicy(StrictModel):
    version: str = "prediction_v1"
    min_data_quality: Annotated[float, Field(ge=0, le=1)] = 0.65
    timeout_seconds: Annotated[float, Field(gt=0, le=120)] = 30
    max_retries: Annotated[int, Field(ge=0, le=2)] = 1
    max_retry_delay_seconds: Annotated[float, Field(ge=0, le=30)] = 5
    max_input_bytes: Annotated[int, Field(ge=1024, le=500000)] = 100000
    max_calls_per_day: Annotated[int, Field(ge=0, le=10000)] = 100
    max_challenger_calls_per_day: Annotated[int, Field(ge=0, le=10000)] = 20
    health_ttl_seconds: Annotated[int, Field(ge=1, le=3600)] = 300
    ranking: RankingPolicy = Field(default_factory=RankingPolicy)

    @property
    def hash(self) -> str:
        return fingerprint(self.model_dump(mode="json"))


class LLMConfig(StrictModel):
    version: str = "llm_routes_v1"
    routes: dict[str, Route]
    policy: PredictionPolicy = Field(default_factory=PredictionPolicy)
    manual_override_routes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def required_routes(self) -> LLMConfig:
        if any(not name or len(name) > 64 for name in self.routes):
            raise ValueError("route names must fit persistent identity")
        if not {"prediction_primary", "prediction_challenger"}.issubset(self.routes):
            raise ValueError("primary/challenger routes required")
        if set(self.manual_override_routes) - self.routes.keys():
            raise ValueError("unknown manual override route")
        return self


def load_llm_config(settings: Settings) -> LLMConfig:
    data = yaml.safe_load(Path(settings.llm_routes_path).read_text())
    config = LLMConfig.model_validate(data)
    # Legacy env fields are an explicit override of the primary route only.
    if settings.llm_provider:
        provider = settings.llm_provider.strip().lower()
        if not settings.predictor_model and provider != "mock":
            raise ValueError("PREDICTOR_MODEL required for explicit LLM_PROVIDER")
        base = config.routes["prediction_primary"].primary.model_dump()
        base.update(provider=provider, model=settings.predictor_model or "mock-v1")
        # A changed vendor/model must not inherit MOCK sampling as purported support.
        base.update(temperature=None, top_p=None)
        base["base_url"] = settings.llm_base_url or None
        if provider in ("minimax", "opencode_go"):
            base["structured_mode"] = "json_only"
        routes = dict(config.routes)
        routes["prediction_primary"] = Route(primary=ModelSpec.model_validate(base))
        config = config.model_copy(update={"routes": routes})
    return config


def task_type(role: Role) -> str:
    return "prediction_primary" if role == Role.PRIMARY else "prediction_challenger"
