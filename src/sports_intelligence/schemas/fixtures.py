from __future__ import annotations

import uuid
from datetime import date as DateType
from datetime import datetime

from pydantic import BaseModel


class FixtureOut(BaseModel):
    id: uuid.UUID
    league_slug: str
    home_team: str
    away_team: str
    kickoff_at: datetime
    venue: str | None = None
    round: str | None = None
    status: str


class DiscoverJobRequest(BaseModel):
    date: DateType | None = None


class DiscoverJobResponse(BaseModel):
    job_id: uuid.UUID
    idempotency_key: str
    status: str
    already_queued: bool
