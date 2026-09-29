from __future__ import annotations

from sports_intelligence.research.conflict import detect_conflicts
from sports_intelligence.research.dedup import (
    content_sha256,
    deduplicate_search_results,
    normalize_url,
)
from sports_intelligence.research.extractor import (
    ClaimExtractor,
    MockClaimExtractor,
    RuleBasedClaimExtractor,
)
from sports_intelligence.research.models import (
    ExtractedClaimDTO,
    ResearchDocumentDTO,
    ResearchRunResultDTO,
)
from sports_intelligence.research.query_builder import build_research_queries
from sports_intelligence.research.service import (
    FixtureResearchView,
    ResearchClaimView,
    ResearchDocumentView,
    get_research_for_fixture,
)

__all__ = [
    "ClaimExtractor",
    "ExtractedClaimDTO",
    "FixtureResearchView",
    "MockClaimExtractor",
    "ResearchClaimView",
    "ResearchDocumentDTO",
    "ResearchDocumentView",
    "ResearchRunResultDTO",
    "RuleBasedClaimExtractor",
    "build_research_queries",
    "content_sha256",
    "deduplicate_search_results",
    "detect_conflicts",
    "get_research_for_fixture",
    "normalize_url",
]
