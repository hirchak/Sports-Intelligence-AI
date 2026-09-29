from __future__ import annotations

import re
from dataclasses import replace

from sports_intelligence.research.models import ExtractedClaimDTO

_ABSENCE_TERMS = {
    "ruled out",
    "miss the match",
    "miss match",
    "will miss",
    "out of the game",
    "sidelined",
    "suspended",
    "injured and out",
}

_PRESENCE_TERMS = {
    "passed fitness test",
    "fit to play",
    "in the squad",
    "in squad",
    "available to play",
    "ready to start",
    "starting xi",
    "cleared to play",
}


def _extract_subject_words(text: str) -> set[str]:
    """Extract significant subject/name tokens from claim text."""
    words = re.findall(r"\b[A-Za-zА-Яа-я]{3,}\b", text.lower())
    stop_words = {
        "the",
        "and",
        "for",
        "with",
        "will",
        "has",
        "have",
        "match",
        "game",
        "team",
        "player",
        "manager",
        "coach",
        "fitness",
        "test",
        "out",
    }
    return {w for w in words if w not in stop_words}


def detect_conflicts(claims: list[ExtractedClaimDTO]) -> list[ExtractedClaimDTO]:
    """Detect and flag conflicting claims within the same fixture.

    Hard rule: conflicting claims must NEVER be deleted or merged.
    Both claims are preserved, flagged with `conflict_flag = True`,
    and documented with conflict metadata for M6 Data Quality analysis.
    """
    if len(claims) < 2:
        return claims

    # Check pairs
    conflicted_indices: dict[int, list[int]] = {}

    for i in range(len(claims)):
        c1 = claims[i]
        c1_text = c1.claim_text.lower()
        c1_is_absent = any(term in c1_text for term in _ABSENCE_TERMS)
        c1_is_present = any(term in c1_text for term in _PRESENCE_TERMS)

        if not (c1_is_absent or c1_is_present):
            continue

        c1_subjects = _extract_subject_words(c1.claim_text)

        for j in range(i + 1, len(claims)):
            c2 = claims[j]
            # Must be same team (or both generic to fixture)
            if c1.team_id != c2.team_id and (c1.team_id is not None and c2.team_id is not None):
                continue

            c2_text = c2.claim_text.lower()
            c2_is_absent = any(term in c2_text for term in _ABSENCE_TERMS)
            c2_is_present = any(term in c2_text for term in _PRESENCE_TERMS)

            # Contradiction: one says absent, other says present
            if (c1_is_absent and c2_is_present) or (c1_is_present and c2_is_absent):
                c2_subjects = _extract_subject_words(c2.claim_text)
                shared_subjects = c1_subjects & c2_subjects

                # If they share named entities/subjects or are in same narrow scope
                if shared_subjects or (c1.team_id is not None and c1.team_id == c2.team_id):
                    conflicted_indices.setdefault(i, []).append(j)
                    conflicted_indices.setdefault(j, []).append(i)

    if not conflicted_indices:
        return claims

    updated_claims: list[ExtractedClaimDTO] = []
    for idx, claim in enumerate(claims):
        if idx in conflicted_indices:
            other_indices = conflicted_indices[idx]
            other_texts = [claims[o].claim_text for o in other_indices]
            conflicting_id = claims[other_indices[0]].id if other_indices else None
            updated = replace(
                claim,
                conflict_flag=True,
                conflicting_claim_id=conflicting_id,
                metadata={
                    **claim.metadata,
                    "conflict_detected": True,
                    "conflicting_with_texts": other_texts,
                },
            )
            updated_claims.append(updated)
        else:
            updated_claims.append(claim)

    return updated_claims
