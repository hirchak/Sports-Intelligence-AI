# Current Task

**Task**: Milestone M6.1: Correctness, Provenance, Freshness, and Orchestration Pass  
**Status**: COMPLETED — AWAITING INDEPENDENT REVIEW  
**Branch**: `build/m6`  
**Base Commit**: `fb256ecaf2ca1a97c64f1dba8d491cff6b935c91` (tag `v0.6-m5`, PR #7 merged into `main`)  
**Reviewed M6 HEAD**: `fff8df75c520696f6c25a14e19ded7b6711e7688` (Verdict: FAIL)

## Milestone Review Verdicts
- M4 → PASS / ACCEPTED (`0d0cd4a631c067a29c21ce584e806a47c534dc82`, merged in PR #6 `2e4683a`)
- M5.3 / M5 → PASS / ACCEPTED (`b38229b0874e9ab992ae25ea2a63e1e6109f8ca7`, merged in PR #7 `fb256ec`, tagged `v0.6-m5`)
- **M6 → FAIL** (`fff8df75c520696f6c25a14e19ded7b6711e7688`)
- **M6.1 → COMPLETED (AWAITING INDEPENDENT REVIEW)**

## Completed Work Items in M6.1
1. **Immutable Fixture Metadata Observation Model (`fixture_metadata_snapshots`)**:
   - Migration 0009: table `fixture_metadata_snapshots` tracking point-in-time fixture identity (kickoff, status, venue, round, league_id, season_id, observed team names, payload_id).
   - Added `payload_id` (ForeignKey to `raw_provider_payloads.id`, nullable=True) to `team_form_snapshots`.
   - Recorded snapshot in fixture discovery pipeline when fixture is discovered/updated.
   - Selector queries `fixture_metadata_snapshots` `<= as_of`.
2. **Fixture Identity in Provenance**:
   - Added fixture metadata snapshot to source manifest and composite source fingerprint.
3. **Research Provenance**:
   - Exposed real `ResearchRun.id` in `FixtureResearchView`.
   - Manifest includes run ID, status, selected document IDs, claim IDs, URLs, and extraction version.
   - Claims in MatchContext include `document_id` and source reference.
4. **Complete Odds Provenance**:
   - Included both current and previous odds snapshot set IDs in source manifest and fingerprint.
5. **Deterministic Multi-Bookmaker Aggregation**:
   - Consensus median per market/selection across bookmakers.
   - Movement = current consensus median - previous consensus median.
   - Market prices in MatchContext include bookmaker identity.
6. **Form Selection Filtering**:
   - Selector strictly filters `window_size == 10` and `scope == "overall"`.
7. **Provider-Scoped Team External IDs**:
   - Match standings/team stats external IDs using `provider == snapshot.provider`.
8. **Preserve Missing != 0 in Form Math**:
   - Do not convert missing GF/GA to 0. Do not treat missing GA as clean sheet or missing GF as failed to score.
9. **Real Freshness in Data Quality**:
   - Evaluate snapshot age at `as_of` using configured phase TTLs. Populate `stale_sources` and penalties.
10. **Canonical Lineup Publication States**:
    - `CONFIRMED`, `NOT_YET_PUBLISHED`, `UNSUPPORTED`, `PROVIDER_ERROR`.
11. **Distinguish Research Not-Collected from NO_USEFUL_RESULTS**:
    - Distinguish `no_run_collected` (0.50 score + warning) from `NO_USEFUL_RESULTS` (0.85 score), `DISABLED`, `PROVIDER_ERROR`, `QUOTA_DENIED`.
12. **Configurable and Persisted Quality Policy**:
    - Runtime configurable weights/thresholds via Settings.
    - Persist `quality_policy` (weights, thresholds, version) with DataQualityReport / MatchContext.
    - Canonical quality bands: `excellent`, `good`, `usable_with_warnings`, `abstain`.
13. **Context-Build Readiness Semantics**:
    - Scanner refuses context build if required collector job is `PENDING`, `RUNNING`, or has pending enqueues.
14. **Source-Generation Context Build Identity**:
    - Idempotency key: `context_build:{fixture_id}:{phase}:{schema_version}:{source_fingerprint}`.
15. **Safe Context Job Retry**:
    - CAS transition `FAILED -> PENDING` on retry with same UUID.
16. **Concurrent Context Build Idempotency**:
    - Safe upsert / unique conflict handling across `feature_snapshots`, `data_quality_reports`, `match_contexts`.
17. **Feature-Level Provenance**:
    - Feature family provenance map linking feature groups to source snapshot IDs stored in `feature_provenance_jsonb`.
18. **Form Snapshot Raw Evidence Link**:
    - Persist `payload_id` in `TeamFormSnapshot`.
19. **Stricter Typed MatchContext Schema**:
    - Pydantic models for major sections.
20. **API Input Validation**:
    - Typed `ForecastPhase` enum query parameter (HTTP 422 on invalid).
21. **Documentation Updates & Acceptance Verification**:
    - Full test suite: 426 passed (339 unit, 87 integration).
    - Ruff check & format: clean.
    - Mypy src: clean (116 files).
    - Alembic check: clean, 0 drift.
    - Compose: valid.
