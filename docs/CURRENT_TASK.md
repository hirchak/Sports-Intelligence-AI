# Current Task

**Task**: Milestone M6.2: Final Acceptance-Hardening Pass  
**Status**: AWAITING INDEPENDENT REVIEW  
**Branch**: `build/m6`  
**Base Commit**: `fb256ecaf2ca1a97c64f1dba8d491cff6b935c91` (tag `v0.6-m5`, PR #7 merged into `main`)  
**Reviewed M6 HEAD**: `fff8df75c520696f6c25a14e19ded7b6711e7688` (Verdict: FAIL)  
**Reviewed M6.1 HEAD**: `08d253fe90883f11456b402563f4065fc4b00072` (Verdict: FAIL)  

## Milestone Review Verdicts
- M4 → PASS / ACCEPTED (`0d0cd4a631c067a29c21ce584e806a47c534dc82`, merged in PR #6 `2e4683a`)
- M5.3 / M5 → PASS / ACCEPTED (`b38229b0874e9ab992ae25ea2a63e1e6109f8ca7`, merged in PR #7 `fb256ec`, tagged `v0.6-m5`)
- **M6 → FAIL** (`fff8df75c520696f6c25a14e19ded7b6711e7688`)
- **M6.1 → FAIL** (`08d253fe90883f11456b402563f4065fc4b00072`)
- **M6.2 → COMPLETED (AWAITING INDEPENDENT REVIEW)**

## Completed Work Items in M6.2
1. **Historical Migration 0003 Byte-for-Byte Restoration**:
   - Reverted `0003_provider_evidence_history_and_indexes.py` to be 100% byte-for-byte identical to `origin/main` (SHA-256 verified).
2. **Authoritative Fixture Metadata & Historical Fallback Removal**:
   - Removed mutable fallback from point-in-time selector: when no `FixtureMetadataSnapshot` exists `<= as_of`, status is set to `"METADATA_UNAVAILABLE"`, `venue=None`, `round=None`, `fixture_metadata_snapshot_id=None`.
   - Data quality flags `"fixture_metadata_missing"` in `critical_missing`, forcing `can_predict=False` and quality band to `"abstain"`.
   - When snapshot exists `<= as_of`, uses its `league_id`, `season_id`, `home_team_id`, `away_team_id`, observed names, venue, round, status, kickoff_at, and resolves league via snapshot `league_id`.
3. **Migration 0009 Legacy Baseline Backfill**:
   - Migration 0009 backfills `legacy_baseline` snapshot at `clock_timestamp()` (NOT backdated).
   - Added `policy_fingerprint` column to `data_quality_reports` and updated `uq_data_quality_reports_identity` unique constraint.
   - Symmetrical downgrade cleanly drops constraint, columns, and tables.
4. **Complete Fixture Provenance**:
   - Source manifest includes snapshot_id, provider, captured_at, payload_id, provider_fixture_id, source_version, league_id, season_id, home_team_id, away_team_id. No fake legacy IDs.
   - When missing, manifest records `snapshot_id=None`, `authoritative=False`, and `error="fixture_metadata_missing"`.
5. **Runtime Quality Settings Wiring**:
   - Added deterministic `build_quality_policy(settings: Settings) -> QualityPolicy`.
   - Context worker builds `QualityPolicy` and `FreshnessPolicy` from real `resolved_settings` and passes them down through `build_and_persist_match_context`.
   - Configurable staleness penalty (`staleness_penalty`, `max_staleness_penalty`) used directly in evaluation.
6. **Strict Quality Config Validation**:
   - `Settings.validate_quality_settings` and `QualityPolicy.__post_init__` validate: weights >= 0, total active weight > 0, 0 <= min_predict_score <= 1, monotonic 0 <= usable <= good <= excellent <= 1, staleness_penalty >= 0, 0 <= max_staleness_penalty <= 1.
7. **Quality Policy Fingerprint & Identity**:
   - Canonical JSON hash of policy persisted in `data_quality_reports.policy_fingerprint`.
   - `uq_data_quality_reports_identity` includes `policy_fingerprint`. Different policies for same fixture and as_of create distinct reports.
8. **Build Configuration Generation in Job Identity**:
   - Deterministic `compute_build_config_fingerprint` SHA-256 of context schema version, feature schema version, quality schema version, policy fingerprint, and research enabled.
   - Pre-match scanner constructs job key: `context_build:{fixture_id}:{phase}:{source_fingerprint}:{build_config_fingerprint}`.
9. **Deterministic Market Snapshot Serialization**:
   - OddsPrice prices sorted by `(market, selection, bookmaker, line, decimal_odds, id)`.
   - Replaced singular `bookmaker` with `bookmakers: list[str]`.
   - Verified identical canonical JSON and hash regardless of DB row insertion order.
10. **Compatible Previous Odds Snapshot Requirement**:
    - Query strictly requires `OddsSnapshotSet.provider == odds_set.provider` and `captured_at < odds_set.captured_at`.
    - Cross-provider sets are never paired; movement defaults to None.
11. **Strict Typed MatchContext Schema**:
    - Converted `MatchContextV1` and all section models to Pydantic with `ConfigDict(extra="forbid", frozen=True)`.
    - Unexpected extra fields fail validation immediately.
12. **Structured Research Claim Source References**:
    - Added `ResearchClaimSource` with document_id, url, domain, title, published_at, retrieved_at, content_hash, provider.
    - Each claim references its structured source object directly.
13. **Historical Provider Entity Mapping Semantics**:
    - `ProviderEntityId` queries strictly filter `first_seen_at <= as_of_utc`.
    - `get_home_external_id(provider)` and `get_away_external_id(provider)` return `None` when the requested provider is unmapped (never falls back to an arbitrary provider).
14. **MORNING Lineup Fully N/A**:
    - In MORNING phase, lineup weight is excluded from denominator, stale lineups do not enter `stale_sources`, and no staleness penalty or warnings are triggered.
15. **Acceptance Verification**:
    - 443 total tests passed (350 unit, 93 integration).
    - Ruff check & format: clean (174 files).
    - Mypy src: clean (116 files).
    - Alembic downgrade -1, upgrade head, check: clean (0 schema drift).
    - Compose and Telegram profile configs: valid.
