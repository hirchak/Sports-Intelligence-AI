from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class LeagueConfigEntry(BaseModel):
    slug: str
    name: str
    country: str | None = None
    enabled: bool = False
    provider_ids: dict[str, int] = Field(default_factory=dict)


class LeagueConfigVersionMismatchError(RuntimeError):
    """LeagueConfig version at execution differs from the version encoded in the job identity."""

    def __init__(self, expected: int, actual: int) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"league config version mismatch: job expects v{expected}, "
            f"loaded config is v{actual}; refusing to execute discovery "
            f"with a different semantic configuration"
        )


class LeagueConfig(BaseModel):
    version: int = 1
    leagues: list[LeagueConfigEntry] = Field(default_factory=list)

    def enabled_slugs(self) -> list[str]:
        return [entry.slug for entry in self.leagues if entry.enabled]

    def provider_id_for(self, slug: str, provider: str) -> int | None:
        for entry in self.leagues:
            if entry.slug == slug:
                return entry.provider_ids.get(provider)
        return None

    def slug_by_provider_league_id(self, provider_league_id: int, provider: str) -> str | None:
        for entry in self.leagues:
            if entry.provider_ids.get(provider) == provider_league_id:
                return entry.slug
        return None


def load_league_config(path: str) -> LeagueConfig:
    config_path = Path(path)
    if not config_path.exists():
        return LeagueConfig()
    return LeagueConfig.model_validate(yaml.safe_load(config_path.read_text()) or {})
