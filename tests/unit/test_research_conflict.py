from __future__ import annotations

import uuid

from sports_intelligence.core.phases import ClaimType
from sports_intelligence.research.conflict import detect_conflicts
from sports_intelligence.research.models import ExtractedClaimDTO


def test_detect_conflicts_flags_opposing_claims() -> None:
    doc_id = uuid.uuid4()
    team_id = uuid.uuid4()

    claim1 = ExtractedClaimDTO(
        document_id=doc_id,
        claim_type=ClaimType.AVAILABILITY.value,
        claim_text="Odegaard is ruled out with an ankle injury",
        confidence=0.85,
        team_id=team_id,
    )
    claim2 = ExtractedClaimDTO(
        document_id=doc_id,
        claim_type=ClaimType.AVAILABILITY.value,
        claim_text="Odegaard is fit and available to play",
        confidence=0.80,
        team_id=team_id,
    )

    resolved = detect_conflicts([claim1, claim2])
    # Both claims must be preserved (never drop contradictory evidence)
    assert len(resolved) == 2
    assert resolved[0].conflict_flag is True
    assert resolved[1].conflict_flag is True
    assert resolved[0].conflicting_claim_id == resolved[1].id
    assert resolved[1].conflicting_claim_id == resolved[0].id


def test_detect_conflicts_preserves_non_conflicting_claims() -> None:
    doc_id = uuid.uuid4()
    team_id = uuid.uuid4()

    claim1 = ExtractedClaimDTO(
        document_id=doc_id,
        claim_type=ClaimType.AVAILABILITY.value,
        claim_text="Saka is ruled out with an injury",
        confidence=0.85,
        team_id=team_id,
    )
    claim2 = ExtractedClaimDTO(
        document_id=doc_id,
        claim_type=ClaimType.TRAVEL.value,
        claim_text="Flight delayed due to weather issues",
        confidence=0.75,
        team_id=None,
    )

    resolved = detect_conflicts([claim1, claim2])
    assert len(resolved) == 2
    assert resolved[0].conflict_flag is False
    assert resolved[1].conflict_flag is False
