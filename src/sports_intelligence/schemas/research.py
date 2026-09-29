from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ResearchClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    claim_type: str
    claim_text: str
    confidence: float
    team_id: uuid.UUID | None
    conflict_flag: bool
    conflicting_claim_id: uuid.UUID | None
    extraction_version: str
    metadata: dict[str, Any]
    created_at: datetime


class ResearchDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    url: str
    domain: str
    title: str
    published_at: datetime | None
    retrieved_at: datetime
    content_hash: str
    relevance_score: float | None
    snippet: str | None
    provider: str
    metadata: dict[str, Any]
    claims: list[ResearchClaimOut] = []


class FixtureResearchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fixture_id: uuid.UUID
    status: str
    last_captured_at: datetime | None
    documents_count: int
    claims_count: int
    conflicts_count: int
    documents: list[ResearchDocumentOut] = []
    claims: list[ResearchClaimOut] = []
