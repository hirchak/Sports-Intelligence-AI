# Review Handoff — Milestone M6.1

Use this file when handing the repository to an independent reviewer, ChatGPT, Kimi, another engineer, or a fresh coding-agent session.

Update it before every milestone review.

---

# Review Status

**Milestone:** M6.1 — Correctness, Provenance, Freshness, and Orchestration Pass  
**Milestone Verdict:** COMPLETED, AWAITING INDEPENDENT REVIEW  
**Branch:** `build/m6`  
**Base Commit:** `fb256ecaf2ca1a97c64f1dba8d491cff6b935c91` (tag `v0.6-m5`, PR #7 merged into `main`)  
**Reviewed M6 HEAD:** `fff8df75c520696f6c25a14e19ded7b6711e7688` (Verdict: FAIL)  
**M6.1 HEAD:** `ecba462cb9059a5df30193dc2eb3e112f85d3aee`

---

# 26-Point Review Response & Architecture Evidence

### 1. Final build/m6 Remote HEAD SHA
- `ecba462cb9059a5df30193dc2eb3e112f85d3aee`

### 2. Immutable Fixture-Observation Solution
- **Migration 0009**: Creates table `fixture_metadata_snapshots` tracking point-in-time fixture identity:
  - `id`, `fixture_id`, `provider`, `provider_fixture_id`, `captured_at`, `league_id`, `season_id`, `home_team_id`, `away_team_id`, `observed_home_team_name`, `observed_away_team_name`, `kickoff_at`, `venue`, `round`, `status`, `payload_id` (ForeignKey to `raw_provider_payloads.id`), `source_version`.
- **Discovery Pipeline Integration**: Whenever a fixture is discovered or updated (`discover_fixtures.py`), a `FixtureMetadataSnapshot` is recorded with `captured_at=retrieved_at` and `payload_id=raw_payload.id`.
- **Point-in-Time Selector**: `select_evidence()` in `src/sports_intelligence/context/selector.py` selects the most recent `FixtureMetadataSnapshot` where `captured_at <= as_of`.

### 3. Fixture Historical Anti-Leakage Behavior
- Later changes in canonical `fixtures` or `teams` (e.g., rescheduled kickoff time, postponed status, venue change, name correction) do NOT affect historical contexts built with `as_of = T0` prior to those changes.
- Verified in `tests/integration/test_m6_anti_leakage_and_context.py::test_strict_as_of_anti_leakage_boundary` and `test_fixture_metadata_snapshot_anti_leakage`.

### 4. Corrected Research Provenance
- `FixtureResearchView` exposes real `ResearchRun.id` (not a placeholder).
- `build_source_manifest()` includes:
  - `run_id`, `status`, `selected_document_ids`, `selected_claim_ids`, `selected_urls`, `extraction_version`.
- Every claim in `MatchContext.research_claims["claims"]` includes `document_id` and source reference.

### 5. Corrected Odds / Current + Previous Provenance
- Both current and previous odds snapshot set IDs are captured in `source_manifest["sources"]["odds"]` (`snapshot_set_id` and `previous_snapshot_set_id`).
- Both are included in the SHA-256 `source_fingerprint`.

### 6. Multi-Bookmaker Deterministic Aggregation Policy
- In `src/sports_intelligence/features/builder.py`:
  - Per market and selection across available bookmakers in the snapshot:
    - Consensus decimal odds: median of decimal odds.
    - Consensus probability: median of no-vig probabilities computed per bookmaker via additive normalization.
  - Odds movement: calculated strictly as `current_consensus_median - previous_consensus_median`.
  - Independent of SQL row iteration order (`test_multi_bookmaker_insertion_order_determinism`).
  - Bookmaker identities preserved in `market_snapshot["bookmakers"]`.

### 7. Form Identity & Provider Identity Fixes
- `select_evidence()` strictly selects `TeamFormSnapshot` matching `window_size == 10` and `scope == "overall"`.
- Provider-scoped external team ID mapping: standings rows and team stats are matched using external IDs scoped to `provider == snapshot.provider` via `get_home_external_id(provider)` and `get_away_external_id(provider)`.

### 8. Missingness Behavior in Form & Stats Math
- In `src/sports_intelligence/features/builder.py`:
  - `missing != 0.0`. Missing values in goals_for or goals_against do not default to 0.
  - Missing goals_against does NOT count as a clean sheet.
  - Missing goals_for does NOT count as failed to score.
  - Independent counts of valid GF and valid GA matches are tracked.

### 9. Freshness-Aware Data Quality Behavior
- `DataQualityEngine.evaluate()` assesses the age of each snapshot category against configured phase TTLs at the exact evaluation `as_of`.
- Stale snapshots are appended to `stale_sources` and receive staleness penalties (e.g. 0.05 per stale source up to max 0.20).
- Canonical lineup states handled in PREMATCH:
  - `CONFIRMED` -> 1.0 score.
  - `NOT_YET_PUBLISHED` -> 0.40 score.
  - `UNSUPPORTED` -> 0.50 score.
  - `PROVIDER_ERROR` -> 0.20 score + provider error record.
- In MORNING phase: Lineups dimension is N/A and excluded from score denominator.

### 10. Persisted Quality Policy and Version
- `quality_policy` dictionary stored on `DataQualityReport` and `MatchContext`:
  - `policy_version`, `weights`, `min_predict_score`, `staleness_penalty`, `max_staleness_penalty`, `band_thresholds`.
- Canonical quality bands: `excellent` (>= 0.85), `good` (>= 0.70), `usable_with_warnings` (>= 0.50), `abstain` (< 0.50).

### 11. Feature-Level Provenance
- `build_feature_provenance(evidence)` maps every derived feature family (`form`, `schedule`, `standings`, `availability`, `market`, `research`, `lineups`) to contributing source snapshot IDs.
- Stored in `FeatureSnapshot.feature_provenance_jsonb`.

### 12. Context-Build Readiness Semantics
- In `src/sports_intelligence/workers/tasks/pre_match.py`:
  - Pre-match scanner tracks `has_in_flight_collectors` if any required collector job is `PENDING`, `RUNNING`, or has pending enqueues.
  - Context build is ONLY triggered if `not has_in_flight_collectors and jobs_enqueued == 0`.

### 13. Source-Generation Job Identity
- Context build idempotency key format:
  `context_build:{fixture_id}:{phase}:{schema_version}:{source_fingerprint}`
- Guarantees deterministic per-source-generation job identity.

### 14. FAILED Context-Job Retry Behavior
- In `_try_enqueue_context_build`:
  - If a job for the same source generation already exists in `FAILED` status, it is retried via CAS transition `FAILED -> PENDING` with the same UUID.
  - Never downgrades `RUNNING` or `SUCCEEDED`.

### 15. Concurrent Builder Idempotency Result
- Safe unique conflict handling across `feature_snapshots`, `data_quality_reports`, and `match_contexts`.
- Tested with 5 concurrent builder tasks on the exact same fixture, phase, and as_of: all return identical records, source fingerprints, and context hashes without spurious failures (`test_concurrent_context_build_idempotency`).

### 16. Strict MatchContext Schema Result
- Defined typed Pydantic models for sections (`FixtureIdentitySection`, `TeamFormSection`, `DataQualitySection`, `FeaturesSection`, `MarketSnapshotSection`).
- Deterministic canonical JSON serialization and SHA-256 `context_hash`.

### 17. Migrations Created
- `0009_m6_1_fixture_metadata_and_provenance.py`:
  - Creates `fixture_metadata_snapshots`.
  - Adds `team_form_snapshots.payload_id`.
  - Adds `data_quality_reports.source_fingerprint` and `quality_policy_jsonb`.
  - Adds `feature_snapshots.feature_provenance_jsonb`.
  - Unique constraint `uq_data_quality_reports_identity` on `(fixture_id, forecast_phase, as_of)`.

### 18. Unit Test Result
- `uv run pytest -q -m 'not integration'` → **339 passed, 87 deselected in 3.81s**

### 19. Integration Test Result
- `pytest -q -m integration` (with PostgreSQL and Redis service containers) → **87 passed, 339 deselected in 15.23s**

### 20. Full Pytest Suite Result
- `uv run pytest -q` → **426 passed in 16.64s**

### 21. Alembic Migration Verification
- `alembic upgrade head`, `downgrade base`, `upgrade head` verified.
- `alembic check` → **No new upgrade operations detected** (models and migrations in 100% sync).

### 22. Ruff / Format / Mypy
- `uv run ruff check .` → **All checks passed!**
- `uv run ruff format --check .` → **173 files already formatted**
- `uv run mypy src` → **Success: no issues found in 116 source files**

### 23. Docker Compose Verification
- `docker compose config -q` → valid (exit code 0)
- `docker compose --profile telegram config -q` → valid (exit code 0)

### 24. Exact CI Result
- Complete local reproduction of CI pipeline (unit, integration, lint, format, typecheck, migrations, compose) passes 100% green.

### 25. Real External Calls Made
- Exactly **0** real external calls made in Milestone M6.1. All tests and services run completely offline and self-contained with mock providers.

### 26. Confirmation: M6 Not Merged / M7 Not Started
- Branch remains `build/m6`.
- `main` remains untouched at `fb256ecaf2ca1a97c64f1dba8d491cff6b935c91` (tag `v0.6-m5`).
- Milestone M7 is **NOT** started. Zero LLM calls, zero predictions, zero ranking, zero betting recommendations exist.