from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

CategoryState = Literal["fresh", "stale", "unknown", "disabled"]


class CategoryStatus(BaseModel):
    captured_at: datetime | None
    age_seconds: int | None
    state: CategoryState


class FixtureStatusOut(BaseModel):
    fixture_id: UUID
    kickoff_at: datetime
    last_refresh: dict[str, datetime | None]
    freshness: dict[str, CategoryStatus]
    lineup_available: bool
    degraded_mode: str
    quota_daily_remaining: int | None
    quota_minute_remaining: int | None


class SystemStatusOut(BaseModel):
    scheduler_enabled: bool
    degradation_mode: str
    daily_remaining: int | None
    minute_remaining: int | None
