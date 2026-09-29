from __future__ import annotations

import re
import uuid
from typing import Protocol, runtime_checkable

from sports_intelligence.core.phases import ClaimType
from sports_intelligence.providers.search.base import SearchResultItem
from sports_intelligence.research.models import ExtractedClaimDTO, ResearchDocumentDTO

_RECOGNIZED_PATTERNS: list[tuple[ClaimType, list[str]]] = [
    (
        ClaimType.AVAILABILITY,
        [
            "ruled out",
            "miss the match",
            "miss match",
            "ankle sprain",
            "hamstring",
            "knee injury",
            "injured",
            "injury",
            "late fitness test",
            "passed fitness test",
            "fit to play",
            "sidelined",
            "knock in training",
            "doubtful",
        ],
    ),
    (
        ClaimType.SUSPENSION,
        ["suspension", "suspended", "red card", "yellow card accumulation", "disciplinary"],
    ),
    (
        ClaimType.ROTATION,
        ["significant rotation", "squad rotation", "rested", "benched", "rest key players"],
    ),
    (
        ClaimType.LINEUP,
        ["predicted lineup", "starting xi", "expected 4-3-3", "expected 3-5-2", "lineup news"],
    ),
    (
        ClaimType.MANAGER_STATEMENT,
        [
            "manager stated",
            "head coach stated",
            "press conference",
            "coach confirmed",
            "arteta stated",
            "stated that",
        ],
    ),
    (
        ClaimType.TACTICAL,
        ["tactical adjustments", "formation change", "tactical breakdown", "defensive system"],
    ),
    (
        ClaimType.TRAVEL,
        ["travel disruption", "flight delayed", "travel problem", "long journey"],
    ),
    (
        ClaimType.TEAM_NEWS,
        ["team news", "match preview", "squad update"],
    ),
]


def _match_team(
    text: str,
    home_id: uuid.UUID | None,
    away_id: uuid.UUID | None,
    home_name: str | None,
    away_name: str | None,
) -> uuid.UUID | None:
    t_lower = text.lower()
    h_lower = (home_name or "").lower().strip()
    a_lower = (away_name or "").lower().strip()

    h_in = bool(h_lower and h_lower in t_lower)
    a_in = bool(a_lower and a_lower in t_lower)

    if h_in and not a_in:
        return home_id
    if a_in and not h_in:
        return away_id
    return None


@runtime_checkable
class ClaimExtractor(Protocol):
    """Extraction interface. Allows M5 rule-based extraction and M7 LLM router."""

    async def extract_claims(
        self,
        document: SearchResultItem | ResearchDocumentDTO,
        *,
        home_team_id: uuid.UUID | None = None,
        away_team_id: uuid.UUID | None = None,
        home_team_name: str = "",
        away_team_name: str = "",
    ) -> list[ExtractedClaimDTO]: ...


class RuleBasedClaimExtractor:
    """Deterministic rule-based extractor for M5.

    Does not fabricate claims when no recognizable pattern is found.
    Extracts structured claims with category, team attribution, confidence,
    and extraction version.
    """

    def __init__(self, *, default_confidence: float = 0.85) -> None:
        self.default_confidence = default_confidence

    def _extract_sync(
        self,
        document: SearchResultItem | ResearchDocumentDTO,
        *,
        home_team_id: uuid.UUID | None = None,
        away_team_id: uuid.UUID | None = None,
        home_team_name: str = "",
        away_team_name: str = "",
    ) -> list[ExtractedClaimDTO]:
        content = getattr(document, "content", None) or getattr(document, "snippet", "") or ""
        title = document.title or ""
        full_text = f"{title}. {content}"
        # Split into sentences or clean blocks
        sentences = [s.strip() for s in re.split(r"[.\n;]", full_text) if len(s.strip()) > 15]

        claims: list[ExtractedClaimDTO] = []
        seen_texts: set[str] = set()

        for sentence in sentences:
            s_lower = sentence.lower()
            for claim_type, keywords in _RECOGNIZED_PATTERNS:
                matched_kw = next((kw for kw in keywords if kw in s_lower), None)
                if matched_kw is not None:
                    clean_text = sentence.strip()
                    if clean_text in seen_texts:
                        continue
                    seen_texts.add(clean_text)

                    team_id = _match_team(
                        clean_text,
                        home_team_id,
                        away_team_id,
                        home_team_name,
                        away_team_name,
                    )
                    if team_id is None:
                        team_id = _match_team(
                            title,
                            home_team_id,
                            away_team_id,
                            home_team_name,
                            away_team_name,
                        )

                    confidence = self.default_confidence
                    domain = document.domain or ""
                    if any(
                        ext in domain
                        for ext in ("premierleague.com", "uefa.com", "official", "bbc.")
                    ):
                        confidence = min(0.98, confidence + 0.10)

                    claims.append(
                        ExtractedClaimDTO(
                            document_id=getattr(document, "id", None),
                            claim_type=claim_type,
                            claim_text=clean_text,
                            confidence=round(confidence, 2),
                            team_id=team_id,
                            extraction_version="v1_rule",
                            metadata={
                                "keyword": matched_kw,
                                "source_domain": domain,
                                "source_url": document.url,
                            },
                        )
                    )
                    break

        return claims

    def extract(
        self,
        document: SearchResultItem | ResearchDocumentDTO,
        *,
        home_team_id: uuid.UUID | None = None,
        away_team_id: uuid.UUID | None = None,
        home_team_name: str = "",
        away_team_name: str = "",
    ) -> list[ExtractedClaimDTO]:
        return self._extract_sync(
            document,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_team_name=home_team_name,
            away_team_name=away_team_name,
        )

    async def extract_claims(
        self,
        document: SearchResultItem | ResearchDocumentDTO,
        *,
        home_team_id: uuid.UUID | None = None,
        away_team_id: uuid.UUID | None = None,
        home_team_name: str = "",
        away_team_name: str = "",
    ) -> list[ExtractedClaimDTO]:
        return self._extract_sync(
            document,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_team_name=home_team_name,
            away_team_name=away_team_name,
        )


class MockClaimExtractor:
    """Mock extractor for testing specific claim patterns, conflicts, or disabled modes."""

    def __init__(
        self,
        *,
        canned_claims: list[ExtractedClaimDTO] | None = None,
        is_available: bool = True,
    ) -> None:
        self.canned_claims = canned_claims
        self.is_available = is_available

    async def extract_claims(
        self,
        document: SearchResultItem | ResearchDocumentDTO,
        *,
        home_team_id: uuid.UUID | None = None,
        away_team_id: uuid.UUID | None = None,
        home_team_name: str = "",
        away_team_name: str = "",
    ) -> list[ExtractedClaimDTO]:
        if not self.is_available:
            return []
        if self.canned_claims is not None:
            return list(self.canned_claims)
        return RuleBasedClaimExtractor()._extract_sync(
            document,
            home_team_id=home_team_id,
            away_team_id=away_team_id,
            home_team_name=home_team_name,
            away_team_name=away_team_name,
        )
