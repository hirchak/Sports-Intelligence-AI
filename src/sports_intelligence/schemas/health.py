from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str


class ComponentChecks(BaseModel):
    database: str
    redis: str


class ReadinessResponse(BaseModel):
    status: str
    checks: ComponentChecks
