from __future__ import annotations

import uuid

from sports_intelligence.core.phases import ClaimType
from sports_intelligence.research.extractor import RuleBasedClaimExtractor
from sports_intelligence.research.models import ResearchDocumentDTO


def test_rule_based_extractor_extracts_injuries() -> None:
    extractor = RuleBasedClaimExtractor()
    home_id = uuid.uuid4()
    away_id = uuid.uuid4()

    doc = ResearchDocumentDTO(
        url="https://news.com/1",
        domain="news.com",
        title="Arsenal injury boost as captain returns",
        snippet="Bukayo Saka is ruled out with a hamstring injury ahead of the weekend clash.",
        content_hash="hash123",
        provider="mock",
    )

    claims = extractor.extract(
        doc,
        home_team_id=home_id,
        away_team_id=away_id,
        home_team_name="Arsenal",
        away_team_name="Chelsea",
    )

    assert len(claims) >= 1
    injury_claims = [c for c in claims if c.claim_type == ClaimType.AVAILABILITY]
    assert len(injury_claims) >= 1
    assert any(
        "hamstring" in c.claim_text.lower() or "ruled out" in c.claim_text.lower()
        for c in injury_claims
    )
    assert any(c.team_id == home_id for c in injury_claims)
    assert all(0.0 <= c.confidence <= 1.0 for c in injury_claims)


def test_rule_based_extractor_extracts_suspensions() -> None:
    extractor = RuleBasedClaimExtractor()
    home_id = uuid.uuid4()
    away_id = uuid.uuid4()

    doc = ResearchDocumentDTO(
        url="https://news.com/2",
        domain="news.com",
        title="Chelsea disciplinary news",
        snippet=(
            "Nicolas Jackson is suspended following a red card suspension in the previous match."
        ),
        content_hash="hash456",
        provider="mock",
    )

    claims = extractor.extract(
        doc,
        home_team_id=home_id,
        away_team_id=away_id,
        home_team_name="Arsenal",
        away_team_name="Chelsea",
    )

    suspension_claims = [c for c in claims if c.claim_type == ClaimType.SUSPENSION]
    assert len(suspension_claims) >= 1
    assert suspension_claims[0].team_id == away_id


def test_rule_based_extractor_extracts_manager_quotes() -> None:
    extractor = RuleBasedClaimExtractor()
    home_id = uuid.uuid4()

    doc = ResearchDocumentDTO(
        url="https://news.com/3",
        domain="news.com",
        title="Press conference quotes",
        snippet="Arteta stated that the team expects a difficult test against their rivals.",
        content_hash="hash789",
        provider="mock",
    )

    claims = extractor.extract(
        doc,
        home_team_id=home_id,
        away_team_id=None,
        home_team_name="Arsenal",
        away_team_name=None,
    )

    quote_claims = [c for c in claims if c.claim_type == ClaimType.MANAGER_STATEMENT]
    assert len(quote_claims) >= 1


def test_rule_based_extractor_empty_on_irrelevant_text() -> None:
    extractor = RuleBasedClaimExtractor()
    doc = ResearchDocumentDTO(
        url="https://news.com/4",
        domain="news.com",
        title="Stock market rally",
        snippet="Wall Street gained three hundred points on unexpected tech sector earnings.",
        content_hash="hash999",
        provider="mock",
    )

    claims = extractor.extract(doc)
    assert len(claims) == 0
