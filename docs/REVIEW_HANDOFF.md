# Review Handoff

Use this file when handing the repository to an independent reviewer, ChatGPT, Kimi, another engineer, or a fresh coding-agent session.

Update it before every milestone review.

---

# Review Status

**Milestone:** M6 — Deterministic Feature Builder + Data Quality Engine + Immutable MatchContext  
**Milestone Verdict:** READY FOR INDEPENDENT REVIEW  
**Branch:** `build/m6`  
**Base Commit:** `fb256ecaf2ca1a97c64f1dba8d491cff6b935c91` (tag `v0.6-m5`, PR #7 merged into `main`)  
**Previous Accepted Milestones:**
- M4 → PASS / ACCEPTED (`0d0cd4a631c067a29c21ce584e806a47c534dc82`, PR #6 `2e4683a`, tag `v0.5-m4`)
- M5 / M5.3 → PASS / ACCEPTED (`b38229b0874e9ab992ae25ea2a63e1e6109f8ca7`, PR #7 `fb256ec`, tag `v0.6-m5`)

---

# Milestone M6 Architectural Boundaries & Scope

Per `00_MASTER_TECHNICAL_SPEC.md`, `14_DATA_QUALITY_PROVENANCE_AND_LEAKAGE.md`, `15_FORECASTING_METHODOLOGY_V1.md`, and `08_FOOTBALL_ANALYTICS_PIPELINE.md`:

- **Phase**: LOCAL DEVELOPMENT ONLY.
- **Strict Determinism**: Zero LLM calls, zero model predictions, zero candidate ranking, zero betting recommendations.
- **Offline Self-Containment**: Zero live external sports/search API calls during automated test execution.
- **Strict Temporal Boundary (`as_of`)**: Pure point-in-time evidence selection. All DB queries strictly enforce `< = as_of`. Zero future record leakage.
- **Immutable Context**: Every generated `MatchContext` is canonical JSON serialized, SHA-256 hashed, and immutable after creation.
- **No Direct Merge**: Branch `build/m6` is submitted for independent acceptance review and is NOT merged into `main`.

---

# Implemented Components

### 1. Form Inputs Collector Prerequisite Fix
- Extended mock sports data provider to canned history of 10 fixtures (`src/sports_intelligence/providers/sports/mock.py`).
- Updated `FormInputsCollector` default window size to 10 fixtures with `is_home` and `result` fields (`src/sports_intelligence/collectors/sports_collectors.py`).
- Added `FreshnessCategory.TEAM_FORM` dispatch to `execute_plan()` in `src/sports_intelligence/collectors/pre_match_scan.py`.

### 2. Database Schema & Alembic Migration 0008
- `src/sports_intelligence/db/models/context.py` & migration `0008_m6_match_context_features_quality.py`:
  - `feature_snapshots`: versioned (`features_v1`), composite unique constraint `(fixture_id, forecast_phase, as_of)`.
  - `data_quality_reports`: versioned (`quality_v1`), composite unique constraint `(fixture_id, forecast_phase, as_of)`, storing overall score, band (`gold`, `silver`, `bronze`, `abstain`), `can_predict`, and dimension scores.
  - `match_contexts`: versioned (`context_v1`), composite unique constraint `(fixture_id, forecast_phase, as_of)`, storing immutable canonical document and SHA-256 `context_hash`.
- Full migration verification: `alembic upgrade head`, `downgrade -1`, `upgrade head`, and `alembic check` report 0 schema drift.

### 3. Point-in-Time Evidence Selector (`src/sports_intelligence/context/selector.py`)
- Executes point-in-time queries strictly filtered by `< = as_of` across 8 snapshot categories:
  - Fixture identity
  - Standings (strictly matched on `league_id` AND `season_id`)
  - Team Statistics
  - Team Form
  - Player Availability
  - Lineups
  - Odds (most recent snapshot set `< = as_of` + previous set `< = as_of` to measure movement)
  - Web Research (`get_research_for_fixture(mode="latest_run")`)
- Proves zero temporal leakage in `tests/integration/test_m6_anti_leakage_and_context.py::test_strict_as_of_anti_leakage_boundary`.

### 4. Source Provenance Manifest (`src/sports_intelligence/context/provenance.py`)
- Emits machine-readable provenance manifest mapping each evidence category to table, snapshot ID, provider, captured_at, and payload reference.
- Generates composite SHA-256 `source_fingerprint` capturing the complete state of underlying source data.

### 5. Deterministic Feature Builder V1 (`src/sports_intelligence/features/builder.py`)
- Form metrics: PPG, GF/match, GA/match, scoring rate, conceding rate, clean sheet rate, home/away splits.
- Schedule metrics: rest days, 7-day match congestion, 14-day match congestion.
- Standings deltas: rank delta, points delta, goals-per-match deltas.
- Availability: missing player counts, unknown status flags.
- Market: implied probabilities, no-vig probabilities, odds movement deltas.
- Missing data invariant: missing features remain strictly `None` (missing != 0.0), with missing reasons tracked in `missing_features`.

### 6. Deterministic Data Quality Engine (`src/sports_intelligence/quality/engine.py`)
- Evaluates 7 dimensions: `fixture_identity`, `form`, `season_stats`, `availability`, `odds`, `research`, `lineups`.
- Phase-aware Lineups Policy:
  - `MORNING` phase: Lineups are expected to be absent (N/A). Lineup weight is dynamically excluded from the score denominator (effective weight 0).
  - `PREMATCH` phase: Lineups are evaluated based on confirmed/unconfirmed publication state.
- Gating rules: `can_predict = False` if both odds and form are missing or critical inputs are absent.
- Band mapping: `gold` (>= 0.85), `silver` (>= 0.70), `bronze` (>= 0.50), `abstain` (< 0.50).
- Conflict & stale penalties applied deterministically.

### 7. MatchContext V1 Schema & Canonical Hash (`src/sports_intelligence/context/models.py`, `builder.py`)
- Strictly ordered 13 sections per spec:
  1. `meta`
  2. `source_manifest`
  3. `data_quality`
  4. `fixture_identity`
  5. `standings`
  6. `team_form`
  7. `season_strength`
  8. `schedule`
  9. `availability`
  10. `lineups`
  11. `market_snapshot`
  12. `research_claims`
  13. `missing_features`
- Canonical JSON serialization with SHA-256 `context_hash`.
- Idempotent builder: repeat executions for same `(fixture_id, phase, as_of)` yield identical IDs and hashes without duplicate rows.

### 8. Celery Worker Task & Orchestration
- Registered task `context.build_match_context` on queue `evaluation` (`src/sports_intelligence/workers/tasks/context.py`).
- Pre-match scanner in `pre_match.py` triggers `_try_enqueue_context_build` once all required collector categories are fresh.
- Records job attempt and updates job state to `SUCCEEDED`/`FAILED`.

### 9. Read-Only API Endpoints (`src/sports_intelligence/api/routes/context.py`)
- `GET /v1/fixtures/{fixture_id}/quality`: returns data quality report, quality band, and dimension scores.
- `GET /v1/fixtures/{fixture_id}/context`: returns complete immutable MatchContext document, context hash, and source timing.
- Read-only DB queries, 0 external provider calls.

---

# Verification & Test Results

```text
Full Test Suite: 408 passed in 14.20s
- Unit tests: 328 passed, 80 deselected in 3.58s
- Integration tests: 80 passed, 328 deselected in 13.42s
Ruff Lint: All checks passed!
Ruff Format: 172 files already formatted
Mypy: Success: no issues found in 115 source files
Alembic Check: No new upgrade operations detected (schema in sync)
Docker Compose: Valid (standard and telegram profiles)
```

---

# Recommended Independent Review Verification Steps

To independently verify this milestone on branch `build/m6`:

1. **Verify git commit and branch state**:
   ```bash
   git branch --show-current   # build/m6
   git log -n 5 --oneline
   ```
2. **Run lint and type checks**:
   ```bash
   uv run ruff check .
   uv run ruff format --check .
   uv run mypy src
   ```
3. **Verify Alembic migrations**:
   ```bash
   DATABASE_URL='postgresql+asyncpg://sports:sports_dev_password@localhost:5433/sports_intel' uv run alembic check
   ```
4. **Run unit tests**:
   ```bash
   uv run pytest -q -m 'not integration'
   ```
5. **Run full integration test suite**:
   ```bash
   TEST_DATABASE_URL='postgresql+asyncpg://sports:sports_dev_password@localhost:5433/sports_intel_test' TEST_REDIS_URL='redis://localhost:6380/15' uv run pytest -q
   ```
6. **Verify Docker Compose**:
   ```bash
   docker compose config -q
   docker compose --profile telegram config -q
   ```