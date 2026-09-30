# Review Handoff — Milestone M6.2

Use this file when handing the repository to an independent reviewer, ChatGPT, Kimi, another engineer, or a fresh coding-agent session.

Update it before every milestone review.

---

# Review Status

**Milestone:** M6.2 — Final Acceptance-Hardening Pass  
**Milestone Verdict:** COMPLETED, AWAITING INDEPENDENT REVIEW  
**Branch:** `build/m6`  
**Base Commit:** `fb256ecaf2ca1a97c64f1dba8d491cff6b935c91` (tag `v0.6-m5`, PR #7 merged into `main`)  
**Reviewed M6 HEAD:** `fff8df75c520696f6c25a14e19ded7b6711e7688` (Verdict: FAIL)  
**Reviewed M6.1 HEAD:** `08d253fe90883f11456b402563f4065fc4b00072` (Verdict: FAIL)  
**M6.2 HEAD:** (to be committed on `build/m6`)

---

# 23-Point Milestone M6.2 Review Response & Architecture Evidence

### 1. Final build/m6 Remote HEAD SHA
- (Recorded upon commit and push)

### 2. Legacy Fixture Anti-Leakage Behavior
- When no `FixtureMetadataSnapshot` exists `<= as_of` for a fixture:
  - Selector sets `status="METADATA_UNAVAILABLE"`, `venue=None`, `round=None`, `season_id=None`, `home_team_name=None`, `away_team_name=None`, `fixture_metadata_snapshot_id=None`.
  - It does NOT fall back to mutable canonical `Fixture` attributes (e.g. `status="FT"`).
  - Data Quality Engine flags `"fixture_metadata_missing"` in `critical_missing`, evaluates quality band to `"abstain"`, and sets `can_predict=False`.
  - Manifest fixture_metadata record has `snapshot_id=None`, `captured_at=None`, `payload_id=None`, and `details={"error": "fixture_metadata_missing", "authoritative": False}`.
  - Regression verified: `test_historical_context_no_metadata_snapshot_never_leaks_mutable_fixture`.

### 3. Exact Fixture Metadata Authority Behavior
- When `FixtureMetadataSnapshot` exists `<= as_of`:
  - Its fields (`league_id`, `season_id`, `home_team_id`, `away_team_id`, `observed_home_team_name`, `observed_away_team_name`, `kickoff_at`, `venue`, `round`, `status`, `provider`, `provider_fixture_id`, `captured_at`, `payload_id`, `source_version`) are authoritative.
  - League metadata is fetched using snapshot's `league_id`.
  - Canonical `Fixture` mutations (e.g. changed kickoff, venue, status, or league) are strictly overridden for historical replay.
  - Regression verified: `test_metadata_snapshot_overrides_changed_canonical_fixture`.

### 4. Runtime Quality Policy Wiring
- Deterministic helper `build_quality_policy(settings: Settings) -> QualityPolicy` builds an immutable `QualityPolicy` from runtime `Settings`.
- `FreshnessPolicy` is constructed from the same `resolved_settings`.
- The production Celery worker (`context.py::_run_build`) instantiates both from `resolved_settings` and passes them down:
  `build_and_persist_match_context(..., policy=quality_policy, freshness_policy=freshness_policy)`.
- No bare `Settings()` are instantiated in quality evaluation during production.
- Staleness penalties use `q_policy.staleness_penalty` and `q_policy.max_staleness_penalty` directly.

### 5. Policy Fingerprint / Identity Behavior
- `QualityPolicy.policy_fingerprint()` computes a canonical SHA-256 hash of `to_dict()`.
- Persisted in `data_quality_reports.policy_fingerprint` and enforced in unique constraint `uq_data_quality_reports_identity` on `(fixture_id, forecast_phase, as_of, schema_version, source_fingerprint, policy_fingerprint)`.
- Separate policies for the same evidence and `as_of` produce distinct reports that co-exist in PostgreSQL without conflict.
- Regression verified: `test_different_quality_policies_create_separate_identities_and_fingerprints`.

### 6. Build Config Fingerprint Behavior
- `compute_build_config_fingerprint(*, context_schema_version, feature_schema_version, quality_schema_version, policy_fingerprint, research_enabled) -> str` computes a SHA-256 fingerprint of all configuration affecting context build.
- Pre-match scanner job key format:
  `context_build:{fixture_id}:{phase}:{source_fingerprint}:{build_config_fingerprint}`.
- Re-enqueues legitimate new context builds if the quality policy or build configuration changes for the same sources.

### 7. Deterministic Market-Context Serialization
- OddsPrice rows are deterministically sorted by `(market, selection, bookmaker, line, decimal_odds, id)`.
- Replaced misleading singular `bookmaker` with `bookmakers: list[str] = sorted(unique bookmaker names)`.
- Arbitrary SQL insertion order produces byte-for-byte identical `context.canonical_json()` and `context_hash`.
- Regression verified: `test_odds_insertion_order_produces_identical_context_hash`.

### 8. Compatible Previous-Odds Behavior
- Previous odds query strictly requires `OddsSnapshotSet.provider == odds_set.provider` and `captured_at < odds_set.captured_at`.
- Different provider sets are never paired; movement features default to `None`.
- Regression verified: `test_previous_odds_provider_mismatch_yields_no_movement`.

### 9. Strict MatchContext Validation
- `MatchContextV1` and all 13 section schemas are strict Pydantic models with `ConfigDict(extra="forbid", frozen=True)`.
- Full context is validated before canonical serialization, hashing, and database persistence.
- Any rogue, extra, or malformed fields fail fast with `ValidationError`.
- Regressions verified: `test_malformed_match_context_section_rejected`, `test_malformed_top_level_match_context_rejected`.

### 10. Structured Research Provenance
- `ResearchClaimSource` strictly models `(document_id, url, domain, title, published_at, retrieved_at, content_hash, provider)`.
- Each claim in MatchContext contains a structured `source` reference.
- Regressions verified: `test_research_provenance_and_claims_identity`.

### 11. Provider Mapping Historical Behavior
- `ProviderEntityId` queries strictly filter `first_seen_at <= as_of_utc`.
- Calling `get_home_external_id(provider)` or `get_away_external_id(provider)` with a specific provider returns `None` if that provider mapping is missing (no fallback to arbitrary mappings).
- Regression verified: `test_provider_mapping_historical_semantics_and_isolation`.

### 12. MORNING Lineup N/A Behavior
- In MORNING phase:
  - Lineups dimension weight is excluded from the denominator.
  - Stale lineups do not enter `stale_sources`.
  - Lineups do not trigger staleness penalties or warnings.
  - Score is identical whether lineups are missing, fresh, or 10 days old.
- Regression verified: `test_stale_morning_lineup_zero_quality_effect`.

### 13. Confirmation Accepted Migration 0003 Unchanged
- Restored `0003_provider_evidence_history_and_indexes.py` byte-for-byte to match `origin/main`.
- SHA-256 hash verified identical to `origin/main`:
  `8573d9cc3790166c2b365c627b99b2789c314716839b0fa6da64dc3e184dafaf`.
- `git diff origin/main -- src/sports_intelligence/db/migrations/versions/0003_provider_evidence_history_and_indexes.py` is completely empty.

### 14. Migration(s) Added / Changed
- `0009_m6_1_fixture_metadata_and_provenance.py`:
  - Upgrades: `fixture_metadata_snapshots` table, `legacy_baseline` backfill at `clock_timestamp()` (NOT backdated), `payload_id` on `team_form_snapshots`, `source_fingerprint`, `quality_policy_jsonb`, `policy_fingerprint`, and unique constraint `uq_data_quality_reports_identity` on `data_quality_reports`, `feature_provenance_jsonb` on `feature_snapshots`.
  - Downgrades: cleanly and symmetrically drops added constraint, columns, and tables.

### 15. Unit Result
- `uv run pytest -q -m "not integration"`: **350 passed, 93 deselected in 4.78s**.

### 16. Integration Result
- `TEST_DATABASE_URL=... TEST_REDIS_URL=... uv run pytest -q -m integration`: **93 passed, 350 deselected in 26.30s**.

### 17. Full Pytest Result
- `uv run pytest -q`: **443 passed in 58.71s**.

### 18. Alembic Result
- Tested:
  - `alembic downgrade -1`: clean.
  - `alembic upgrade head`: clean.
  - `alembic check`: clean (`No new upgrade operations detected`).
  - Fresh database lifecycle: `downgrade base` -> `upgrade head` -> `downgrade base` -> `upgrade head` -> clean.

### 19. Ruff / Format / Mypy
- `uv run ruff check .`: clean (`All checks passed!`).
- `uv run ruff format --check .`: clean (`174 files already formatted`).
- `uv run mypy src`: clean (`Success: no issues found in 116 source files`).

### 20. Compose
- `docker compose config -q`: valid.
- `docker compose --profile telegram config -q`: valid.

### 21. Exact CI Result
- Deterministic local CI test suite passed:
  - Unit: 350 passed.
  - Integration: 93 passed.
  - Total: 443 passed.

### 22. External Calls Made
- Exactly ZERO live external calls made during automated tests:
  - 0 API-Football calls.
  - 0 The Odds API calls.
  - 0 Tavily search calls.
  - 0 LLM calls.

### 23. Confirmation M6 Not Merged / M7 Not Started
- Confirmed: branch `build/m6` is NOT merged into `main`.
- Confirmed: `main` remains at accepted M5 (`fb256ecaf2ca1a97c64f1dba8d491cff6b935c91`, tag `v0.6-m5`).
- Confirmed: Milestone M7 is NOT started.
- Confirmed: stopped for independent review.