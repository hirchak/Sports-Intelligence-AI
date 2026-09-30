# Current Task

**Task**: Milestone M6: Deterministic Feature Builder + Data Quality Engine + Immutable MatchContext  
**Status**: COMPLETE / AWAITING INDEPENDENT REVIEW  
**Branch**: `build/m6`  
**Base Commit**: `fb256ecaf2ca1a97c64f1dba8d491cff6b935c91` (tag `v0.6-m5`, PR #7 merged into `main`)

## Milestone Review Verdicts
- M4 → PASS / ACCEPTED (`0d0cd4a631c067a29c21ce584e806a47c534dc82`, merged in PR #6 `2e4683a`)
- M5.3 / M5 → PASS / ACCEPTED (`b38229b0874e9ab992ae25ea2a63e1e6109f8ca7`, merged in PR #7 `fb256ec`, tagged `v0.6-m5`)
- **M6 → READY FOR INDEPENDENT REVIEW**

## Implemented in Milestone M6
1. **Prerequisite Form Inputs Fix**:
   - Extended mock sports provider canned completed fixtures to 10 fixtures.
   - Updated `FormInputsCollector` default window_size to 10 with `is_home` and `result` fields.
   - Added `FreshnessCategory.TEAM_FORM` dispatch to `execute_plan()` in `pre_match_scan.py`.
2. **Database Schema & Models** (Alembic migration `0008`):
   - `feature_snapshots`: deterministic computed features, versioned, keyed by `(fixture_id, forecast_phase, as_of)`.
   - `data_quality_reports`: 7-dimension quality evaluation, quality band (`gold`, `silver`, `bronze`, `abstain`), `can_predict`.
   - `match_contexts`: immutable context document, canonical JSON, SHA-256 `context_hash`.
3. **Point-in-Time Evidence Selector** (`sports_intelligence.context.selector`):
   - Strict `<= as_of` temporal cutoff across Fixture, Standings, Team Stats, Form, Availability, Lineups, Odds, and Research.
   - Strictly enforces league and season matching for standings.
4. **Source Provenance Manifest** (`sports_intelligence.context.provenance`):
   - Machine-readable manifest mapping each evidence category to table, snapshot_id, provider, captured_at, payload reference.
   - Composite SHA-256 `source_fingerprint` uniquely capturing the source snapshot state.
5. **Deterministic Feature Builder V1** (`sports_intelligence.features.builder`):
   - Form metrics (PPG, GF, GA, scoring/conceding rates, clean sheets, home/away splits).
   - Schedule rest days and 7d/14d congestion.
   - Standings rank and points deltas.
   - Availability counts and state.
   - Market no-vig probabilities and odds movement.
   - Missing data strictly preserved as `None` (missing != 0.0).
6. **Deterministic Data Quality Engine** (`sports_intelligence.quality.engine`):
   - 7 dimensions evaluated with configurable weights.
   - MORNING vs PREMATCH lineups policy: in MORNING, lineups are N/A (excluded from denominator); in PREMATCH, evaluated per publication/confirmation.
   - Critical missing gating (`can_predict = False` if odds or form missing).
   - Conflict and stale source penalties.
7. **MatchContext V1 Schema & Persistence** (`sports_intelligence.context.models`, `builder`):
   - Strictly ordered 13 sections.
   - Canonical JSON serialization with SHA-256 `context_hash`.
   - Fully idempotent persistence across `match_contexts`, `data_quality_reports`, and `feature_snapshots`.
8. **Celery Task & Orchestration**:
   - Task `context.build_match_context` on queue `evaluation`.
   - Pre-match scanner dispatches context build when all required data categories are fresh.
9. **Read-only API Endpoints**:
   - `GET /v1/fixtures/{fixture_id}/quality`
   - `GET /v1/fixtures/{fixture_id}/context`
10. **Acceptance Verification**:
    - 408 tests pass (328 unit, 80 integration).
    - 0 schema drift on `alembic check` and clean migration downgrade/upgrade cycle.
    - Zero live API calls, zero secrets, zero LLM calls, zero betting logic.
