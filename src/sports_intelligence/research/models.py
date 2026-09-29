from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sports_intelligence.core.phases import ClaimType, ResearchState


@dataclass(frozen=True)
class ExtractedClaimDTO:
    claim_type: str | ClaimType
    claim_text: str
    confidence: float
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    document_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    conflict_flag: bool = False
    conflicting_claim_id: uuid.UUID | None = None
    extraction_version: str = "v1_rule"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResearchDocumentDTO:
    url: str
    domain: str
    title: str
    content_hash: str = ""
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    published_at: datetime | None = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    relevance_score: float | None = None
    snippet: str | None = None
    provider: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    claims: list[ExtractedClaimDTO] = field(default_factory=list)


@dataclass(frozen=True)
class ResearchRunResultDTO:
    fixture_id: uuid.UUID
    status: ResearchState
    provider: str
    phase: str
    captured_at: datetime
    queries: list[str]
    documents: list[ResearchDocumentDTO]
    conflicts_count: int = 0
    details: dict[str, Any] = field(default_factory=dict)
