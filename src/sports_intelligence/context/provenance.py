from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from sports_intelligence.context.selector import SelectedEvidence


@dataclass(frozen=True)
class ProvenanceRecord:
    category: str
    table: str
    snapshot_id: str | None
    provider: str | None
    captured_at: str | None
    payload_id: str | None = None
    fingerprint: str | None = None
    details: dict[str, Any] | None = None


@dataclass(frozen=True)
class SourceManifest:
    sources: dict[str, ProvenanceRecord]
    source_fingerprint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_fingerprint": self.source_fingerprint,
            "sources": {k: asdict(v) for k, v in self.sources.items()},
        }


def build_source_manifest(evidence: SelectedEvidence) -> SourceManifest:
    """Construct an auditable, machine-readable provenance manifest of all selected evidence."""
    sources: dict[str, ProvenanceRecord] = {}

    # Fixture Metadata
    if evidence.fixture_metadata is not None:
        sources["fixture_metadata"] = ProvenanceRecord(
            category="fixture_metadata",
            table="fixture_metadata_snapshots",
            snapshot_id=str(evidence.fixture_metadata.id),
            provider=evidence.fixture_metadata.provider,
            captured_at=evidence.fixture_metadata.captured_at.isoformat(),
            payload_id=(
                str(evidence.fixture_metadata.payload_id)
                if evidence.fixture_metadata.payload_id
                else None
            ),
            details={
                "provider_fixture_id": evidence.fixture_metadata.provider_fixture_id,
                "source_version": evidence.fixture_metadata.source_version,
                "league_id": str(evidence.fixture_metadata.league_id),
                "observed_league_name": evidence.fixture_metadata.observed_league_name,
                "observed_league_slug": evidence.fixture_metadata.observed_league_slug,
                "season_id": (
                    str(evidence.fixture_metadata.season_id)
                    if evidence.fixture_metadata.season_id
                    else None
                ),
                "home_team_id": str(evidence.fixture_metadata.home_team_id),
                "away_team_id": str(evidence.fixture_metadata.away_team_id),
                "observed_home_team_name": evidence.fixture_metadata.observed_home_team_name,
                "observed_away_team_name": evidence.fixture_metadata.observed_away_team_name,
                "status": evidence.fixture_metadata.status,
                "kickoff_at": evidence.fixture_metadata.kickoff_at.isoformat(),
                "venue": evidence.fixture_metadata.venue,
                "round": evidence.fixture_metadata.round,
            },
        )
    else:
        sources["fixture_metadata"] = ProvenanceRecord(
            category="fixture_metadata",
            table="fixture_metadata_snapshots",
            snapshot_id=None,
            provider=None,
            captured_at=None,
            payload_id=None,
            details={"error": "fixture_metadata_missing", "authoritative": False},
        )

    # Standings
    if evidence.standings is not None:
        sources["standings"] = ProvenanceRecord(
            category="standings",
            table="standings_snapshots",
            snapshot_id=str(evidence.standings.id),
            provider=evidence.standings.provider,
            captured_at=evidence.standings.captured_at.isoformat(),
            payload_id=(
                str(evidence.standings.payload_id) if evidence.standings.payload_id else None
            ),
            fingerprint=evidence.standings.source_fingerprint,
        )

    # Home Team Stats
    if evidence.home_team_stats is not None:
        sources["home_team_statistics"] = ProvenanceRecord(
            category="home_team_statistics",
            table="team_statistics_snapshots",
            snapshot_id=str(evidence.home_team_stats.id),
            provider=evidence.home_team_stats.provider,
            captured_at=evidence.home_team_stats.captured_at.isoformat(),
            payload_id=(
                str(evidence.home_team_stats.payload_id)
                if evidence.home_team_stats.payload_id
                else None
            ),
        )

    # Away Team Stats
    if evidence.away_team_stats is not None:
        sources["away_team_statistics"] = ProvenanceRecord(
            category="away_team_statistics",
            table="team_statistics_snapshots",
            snapshot_id=str(evidence.away_team_stats.id),
            provider=evidence.away_team_stats.provider,
            captured_at=evidence.away_team_stats.captured_at.isoformat(),
            payload_id=(
                str(evidence.away_team_stats.payload_id)
                if evidence.away_team_stats.payload_id
                else None
            ),
        )

    # Home Form
    if evidence.home_form is not None:
        sources["home_team_form"] = ProvenanceRecord(
            category="home_team_form",
            table="team_form_snapshots",
            snapshot_id=str(evidence.home_form.id),
            provider="form_inputs_collector",
            captured_at=evidence.home_form.as_of.isoformat(),
            payload_id=(
                str(evidence.home_form.payload_id) if evidence.home_form.payload_id else None
            ),
            fingerprint=evidence.home_form.source_fingerprint,
            details={
                "window_size": evidence.home_form.window_size,
                "scope": evidence.home_form.scope,
            },
        )

    # Away Form
    if evidence.away_form is not None:
        sources["away_team_form"] = ProvenanceRecord(
            category="away_team_form",
            table="team_form_snapshots",
            snapshot_id=str(evidence.away_form.id),
            provider="form_inputs_collector",
            captured_at=evidence.away_form.as_of.isoformat(),
            payload_id=(
                str(evidence.away_form.payload_id) if evidence.away_form.payload_id else None
            ),
            fingerprint=evidence.away_form.source_fingerprint,
            details={
                "window_size": evidence.away_form.window_size,
                "scope": evidence.away_form.scope,
            },
        )

    # Home Availability
    if evidence.home_availability is not None:
        sources["home_availability"] = ProvenanceRecord(
            category="home_availability",
            table="availability_snapshots",
            snapshot_id=str(evidence.home_availability.id),
            provider=evidence.home_availability.provider,
            captured_at=evidence.home_availability.captured_at.isoformat(),
            payload_id=(
                str(evidence.home_availability.payload_id)
                if evidence.home_availability.payload_id
                else None
            ),
            details={"availability_state": evidence.home_availability.availability_state},
        )

    # Away Availability
    if evidence.away_availability is not None:
        sources["away_availability"] = ProvenanceRecord(
            category="away_availability",
            table="availability_snapshots",
            snapshot_id=str(evidence.away_availability.id),
            provider=evidence.away_availability.provider,
            captured_at=evidence.away_availability.captured_at.isoformat(),
            payload_id=(
                str(evidence.away_availability.payload_id)
                if evidence.away_availability.payload_id
                else None
            ),
            details={"availability_state": evidence.away_availability.availability_state},
        )

    # Home Lineup
    if evidence.home_lineup is not None:
        sources["home_lineup"] = ProvenanceRecord(
            category="home_lineup",
            table="lineup_snapshots",
            snapshot_id=str(evidence.home_lineup.id),
            provider=evidence.home_lineup.provider,
            captured_at=evidence.home_lineup.captured_at.isoformat(),
            payload_id=(
                str(evidence.home_lineup.payload_id) if evidence.home_lineup.payload_id else None
            ),
            details={
                "publication_state": evidence.home_lineup.publication_state,
                "confirmed": evidence.home_lineup.confirmed,
            },
        )

    # Away Lineup
    if evidence.away_lineup is not None:
        sources["away_lineup"] = ProvenanceRecord(
            category="away_lineup",
            table="lineup_snapshots",
            snapshot_id=str(evidence.away_lineup.id),
            provider=evidence.away_lineup.provider,
            captured_at=evidence.away_lineup.captured_at.isoformat(),
            payload_id=(
                str(evidence.away_lineup.payload_id) if evidence.away_lineup.payload_id else None
            ),
            details={
                "publication_state": evidence.away_lineup.publication_state,
                "confirmed": evidence.away_lineup.confirmed,
            },
        )

    # Odds (Current)
    if evidence.odds_set is not None:
        sources["odds"] = ProvenanceRecord(
            category="odds",
            table="odds_snapshot_sets",
            snapshot_id=str(evidence.odds_set.id),
            provider=evidence.odds_set.provider,
            captured_at=evidence.odds_set.captured_at.isoformat(),
            payload_id=str(evidence.odds_set.payload_id) if evidence.odds_set.payload_id else None,
            details={"prices_count": len(evidence.odds_prices)},
        )

    # Odds (Previous for Movement)
    if evidence.prev_odds_set is not None:
        sources["prev_odds"] = ProvenanceRecord(
            category="prev_odds",
            table="odds_snapshot_sets",
            snapshot_id=str(evidence.prev_odds_set.id),
            provider=evidence.prev_odds_set.provider,
            captured_at=evidence.prev_odds_set.captured_at.isoformat(),
            payload_id=(
                str(evidence.prev_odds_set.payload_id)
                if evidence.prev_odds_set.payload_id
                else None
            ),
            details={"prices_count": len(evidence.prev_odds_prices)},
        )

    # Research
    if evidence.research is not None:
        sources["research"] = ProvenanceRecord(
            category="research",
            table="research_runs",
            snapshot_id=str(evidence.research.run_id) if evidence.research.run_id else None,
            provider=evidence.research.provider or "web_research",
            captured_at=(
                evidence.research.last_captured_at.isoformat()
                if evidence.research.last_captured_at
                else None
            ),
            details={
                "status": evidence.research.status,
                "run_id": str(evidence.research.run_id) if evidence.research.run_id else None,
                "documents_count": evidence.research.documents_count,
                "claims_count": evidence.research.claims_count,
                "conflicts_count": evidence.research.conflicts_count,
                "document_ids": [str(d.id) for d in evidence.research.documents],
                "claim_ids": [str(c.id) for c in evidence.research.claims],
                "urls": [d.url for d in evidence.research.documents],
                "extraction_versions": sorted(
                    list({c.extraction_version for c in evidence.research.claims})
                ),
            },
        )

    # Provider Mappings
    if evidence.fixture.home_provider_mappings or evidence.fixture.away_provider_mappings:
        sources["provider_mappings"] = ProvenanceRecord(
            category="provider_mappings",
            table="provider_entity_ids",
            snapshot_id=None,
            provider=None,
            captured_at=None,
            payload_id=None,
            details={
                "home_mappings": [
                    {
                        "provider": m.provider,
                        "external_id": m.external_id,
                        "mapping_id": str(m.mapping_id),
                        "first_seen_at": m.first_seen_at.isoformat(),
                    }
                    for m in evidence.fixture.home_provider_mappings
                ],
                "away_mappings": [
                    {
                        "provider": m.provider,
                        "external_id": m.external_id,
                        "mapping_id": str(m.mapping_id),
                        "first_seen_at": m.first_seen_at.isoformat(),
                    }
                    for m in evidence.fixture.away_provider_mappings
                ],
            },
        )

    # Compute canonical JSON fingerprint from the complete provenance manifest
    sources_dict = {k: asdict(v) for k, v in sources.items()}
    canonical = json.dumps(sources_dict, sort_keys=True, separators=(",", ":"))
    fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    return SourceManifest(sources=sources, source_fingerprint=fingerprint)


def build_feature_provenance(evidence: SelectedEvidence) -> dict[str, Any]:
    """Map each feature family to the exact snapshot IDs from which it was computed."""
    return {
        "fixture_identity": {
            "source_type": "fixture_metadata_snapshot" if evidence.fixture_metadata else "none",
            "snapshot_id": (
                str(evidence.fixture_metadata.id) if evidence.fixture_metadata else None
            ),
        },
        "form": {
            "source_type": "team_form_snapshots",
            "home_snapshot_id": str(evidence.home_form.id) if evidence.home_form else None,
            "away_snapshot_id": str(evidence.away_form.id) if evidence.away_form else None,
        },
        "standings": {
            "source_type": "standings_snapshots",
            "snapshot_id": str(evidence.standings.id) if evidence.standings else None,
        },
        "team_statistics": {
            "source_type": "team_statistics_snapshots",
            "home_snapshot_id": (
                str(evidence.home_team_stats.id) if evidence.home_team_stats else None
            ),
            "away_snapshot_id": (
                str(evidence.away_team_stats.id) if evidence.away_team_stats else None
            ),
        },
        "availability": {
            "source_type": "availability_snapshots",
            "home_snapshot_id": (
                str(evidence.home_availability.id) if evidence.home_availability else None
            ),
            "away_snapshot_id": (
                str(evidence.away_availability.id) if evidence.away_availability else None
            ),
        },
        "lineups": {
            "source_type": "lineup_snapshots",
            "home_snapshot_id": (str(evidence.home_lineup.id) if evidence.home_lineup else None),
            "away_snapshot_id": (str(evidence.away_lineup.id) if evidence.away_lineup else None),
        },
        "odds": {
            "source_type": "odds_snapshot_sets",
            "current_snapshot_set_id": str(evidence.odds_set.id) if evidence.odds_set else None,
            "previous_snapshot_set_id": (
                str(evidence.prev_odds_set.id) if evidence.prev_odds_set else None
            ),
        },
        "research": {
            "source_type": "research_runs",
            "run_id": (
                str(evidence.research.run_id)
                if (evidence.research and evidence.research.run_id)
                else None
            ),
        },
    }
