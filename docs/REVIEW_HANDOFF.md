# Review Handoff: M6.4 Acceptance-Fix Pass

**Milestone:** M6.4 — Acceptance-Fix Pass (Historical League Authority, Deterministic Provider Mappings, Immutability Audit, Task Semantics)
**Branch:** `build/m6`
**Base:** `origin/main` (`fb256ecaf2ca1a97c64f1dba8d491cff6b935c91`, tag `v0.6-m5`)
**Implementation Commit:** `cedf481ca8839714b82b0dfaf75bab33023e32a8`
**Remote Status:** Pushing to `origin/build/m6`
**Development Phase:** LOCAL DEVELOPMENT ONLY (No Hetzner, no SSH, no Hermes, no deployment, no M7, no LLM calls)

---

## 1. Scope & Objective
Resolve the remaining review findings from M6.3:
1. **Historical League Metadata Authority**: Historical MatchContext reconstruction must not depend on mutable current `League.slug` or `League.name`.
2. **Deterministic Provider-Mapping Selection and Order**: Eliminate non-deterministic `ProviderEntityId` queries; define deterministic semantics for querying, multiple mapping selection (`first_seen_at <= as_of`), and canonical list sorting.
3. **Pydantic Immutability Claim Audit**: Audit documentation and tests claiming `BaseModel(frozen=True)` guarantees deep immutability; align documentation and tests with actual behavior (attribute-frozen models, authoritative PostgreSQL persistence boundary).
4. **Celery Task Error Semantics**: Ensure `HistoricalFixtureMetadataUnavailable` is logged cleanly without unhandled tracebacks while marking Celery job `FAILED` in the database ledger (`jobs` and `job_attempts`) and re-raising for Celery failure accounting.
5. **Migration & Doc Hygiene**: Fix migration `0010_m6_3_freshness_policy.py` revision docstring, create migration `0011_m6_4_historical_league_metadata.py`, and update persistent project memory.

---

## 2. Source and Test Files Changed

### Source Files (8):
1. `src/sports_intelligence/context/selector.py`:
   - Updated `select_evidence` to read `league_name` and `league_slug` from authoritative `FixtureMetadataSnapshot.observed_league_name` and `observed_league_slug`.
   - Explicit SQL ordering on `ProviderEntityId` queries: `provider ASC, first_seen_at DESC, external_id ASC, id ASC`.
   - Deterministic selection of latest mapping `<= as_of` per provider; exclusion of future mappings (`first_seen_at > as_of`).
   - Canonical sort for mapping lists: `(provider, -first_seen_at.timestamp(), external_id, str(mapping_id))`.
2. `src/sports_intelligence/context/provenance.py`:
   - Captured `observed_league_name` and `observed_league_slug` under `fixture_metadata.details`.
3. `src/sports_intelligence/db/models/discovery.py`:
   - Added `observed_league_name: Mapped[str | None]` and `observed_league_slug: Mapped[str | None]` to `FixtureMetadataSnapshot`.
4. `src/sports_intelligence/db/repositories/discovery.py`:
   - Updated `record_fixture_metadata_snapshot` to accept and persist `observed_league_name` and `observed_league_slug`.
5. `src/sports_intelligence/pipelines/discover_fixtures.py`:
   - Passes observed league name and slug to `record_fixture_metadata_snapshot`.
6. `src/sports_intelligence/workers/tasks/context.py`:
   - Catches `HistoricalFixtureMetadataUnavailable` explicitly, logs structured warning without traceback, marks Celery job `FAILED` in `jobs` and `job_attempts`, and re-raises.
7. `src/sports_intelligence/db/migrations/versions/0010_m6_3_freshness_policy.py`:
   - Corrected revision docstring from `cb9a7f960dbe` to `0010`.
8. `src/sports_intelligence/db/migrations/versions/0011_m6_4_historical_league_metadata.py`:
   - Added `observed_league_name` and `observed_league_slug` to `fixture_metadata_snapshots` with safe migration-time backfill from `leagues` table and clean symmetrical downgrade.

### Test Files (2):
9. `tests/unit/context/test_context_schema_and_hash.py`:
   - Added `test_match_context_immutability_attribute_frozen_and_nested_behavior` auditing Pydantic freeze vs mutable container behavior.
   - Added `test_league_historical_identity_in_provenance_and_source_fingerprint`.
   - Added `test_provider_mappings_deterministic_canonical_ordering_and_hash`.
10. `tests/integration/test_m6_anti_leakage_and_context.py`:
    - Added `test_mutable_league_metadata_change_does_not_alter_historical_context_replay`.
    - Added `test_provider_mapping_deterministic_selection_and_ordering_across_insertion_orders`.
    - Added `test_historical_metadata_unavailable_task_and_refusal_persistence`.

---

## 3. Historical League Metadata Authority
- **Problem Solved**: Previous selector resolved `league_name` and `league_slug` by querying the mutable canonical `leagues` row at context assembly time. Mutating the `League` row at T1 altered the reconstructed context and `context_hash` for historical T0 replays, violating historical immutability.
- **Solution**:
  - `FixtureMetadataSnapshot` now captures `observed_league_name` and `observed_league_slug` at observation time.
  - Migration `0011` backfills existing snapshots truthfully from `leagues` at migration observation time.
  - Context selector reads `league_name` and `league_slug` strictly from `FixtureMetadataSnapshot`.
  - Provenance details in `source_manifest` capture observed league values, ensuring source fingerprint directly reflects historical observation.
- **Regression Verification**:
  - `test_mutable_league_metadata_change_does_not_alter_historical_context_replay`: builds context at T0 (`Premier League`), updates `League` in DB to `Barclays Premier League` with slug `barclays-pl`, rebuilds at T0. Context identity, source fingerprint, and context hash remain 100% byte-for-byte identical.

---

## 4. Deterministic Provider Mapping Rules
- **Problem Solved**: `ProviderEntityId` queries previously relied on database row order without ordering constraints, and tie-breaking across multiple mappings was implicit.
- **Rules Defined**:
  1. **Query Ordering**: `ORDER BY provider ASC, first_seen_at DESC, external_id ASC, id ASC`.
  2. **Multiple Mappings Selection**: Only mappings with `first_seen_at <= as_of_utc` are considered. The first row encountered for each provider is the most recently observed valid mapping (with deterministic tie-breakers `external_id ASC, id ASC`).
  3. **List Sorting**: Downstream lists (`home_provider_mappings`, `away_provider_mappings`) are canonically sorted by `(provider, -first_seen_at.timestamp(), external_id, str(mapping_id))`.
- **Regression Verification**:
  - `test_provider_mapping_deterministic_selection_and_ordering_across_insertion_orders`: verifies that inserting mappings in reverse orders on disk produces identical `SelectedFixtureInfo`, `source_manifest`, `source_fingerprint`, and `context_hash`. Future mappings (`first_seen_at > as_of`) are excluded.

---

## 5. Pydantic Immutability Claim Audit
- **Audit Findings**:
  - Pydantic models with `ConfigDict(frozen=True)` provide **attribute-level freezing**: assigning to model fields (`ctx.fixture_identity = ...`) raises `ValidationError`.
  - However, standard Python mutable collections nested inside models (e.g., `list`, `dict`) can still be mutated in-place via collection methods (e.g. `list.append()`, `dict["k"] = v`) unless explicitly copied or wrapped in immutable types.
  - **Authoritative Boundary**: The immutable boundary for Sports Intelligence AI is PostgreSQL persistence in `match_contexts`. Once written, rows in `match_contexts`, `feature_snapshots`, and `data_quality_reports` are immutable historical records with cryptographic `context_hash` verification.
- **Test Evidence**:
  - `test_match_context_immutability_attribute_frozen_and_nested_behavior` verifies that attribute mutation is blocked by Pydantic, demonstrates nested list behavior, and verifies that the authoritative boundary is DB persistence and hash validation.

---

## 6. Celery Task Error Semantics
- **Behavior**:
  - In `src/sports_intelligence/workers/tasks/context.py`, the worker catches `HistoricalFixtureMetadataUnavailable`.
  - Logs a structured warning with fixture ID, as_of timestamp, and reason (no traceback).
  - Explicitly marks the Celery `Job` record as `FAILED` and records a corresponding attempt in `job_attempts` with `error_class="HistoricalFixtureMetadataUnavailable"`.
  - Re-raises the exception so Celery handles worker accounting correctly.
  - Zero context, feature, or quality records are persisted.
- **Test Evidence**:
  - `test_historical_metadata_unavailable_task_and_refusal_persistence` verifies the ledger status, clean logging, and absence of persisted context rows.

---

## 7. Migration 0010 & 0011 Verification
- **Migration 0010**:
  - Corrected revision docstring from `cb9a7f960dbe` to `0010`.
- **Migration 0011**:
  - Revision: `0011` (down_revision: `0010`).
  - Columns: `observed_league_name` (`VARCHAR(255)`, nullable), `observed_league_slug` (`VARCHAR(255)`, nullable) on `fixture_metadata_snapshots`.
  - Backfill: Safe SQL `UPDATE fixture_metadata_snapshots fms SET observed_league_name = l.name, observed_league_slug = l.slug FROM leagues l WHERE fms.league_id = l.id`.
  - Downgrade: Drops columns `observed_league_slug` and `observed_league_name`.
  - Lifecycle: `upgrade head` -> `downgrade -1` -> `upgrade head` -> `alembic check` produces "No new upgrade operations detected" (zero drift).

---

## 8. Test & Verification Summary
- **Unit Tests**: `uv run pytest -q -m "not integration"` → **360 passed, 99 deselected in 4.06s** (100% pass)
- **Integration Tests**: `TEST_DATABASE_URL=... TEST_REDIS_URL=... uv run pytest -q -m integration` → **99 passed, 360 deselected in 18.72s** (100% pass)
- **Full Pytest**: `uv run pytest -q` → **459 passed in 19.29s** (100% pass)
- **Ruff Check**: `uv run ruff check .` → All checks passed!
- **Ruff Format**: `uv run ruff format --check .` → 177 files already formatted.
- **Mypy**: `uv run mypy src` → Success: no issues found in 119 source files.
- **Alembic**: `alembic check` → Clean, 0 drift.
- **Docker Compose**: `docker compose config -q` and `docker compose --profile telegram config -q` → Clean.

---

## 9. Next Steps
- Commit and push to `origin/build/m6`.
- Verify GitHub Actions CI run on exact remote HEAD.
- Do NOT merge `build/m6` to `main`.
- Do NOT start M7.
- Development remains LOCAL ONLY.
