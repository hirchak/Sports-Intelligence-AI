# Review Handoff: Milestone M6 Accepted (Merge Preparation)

**Milestone:** M6 — Deterministic Feature Builder + Data Quality Engine + Immutable MatchContext (PASS / ACCEPTED)
**Branch:** `build/m6`
**Base:** `origin/main` (`fb256ecaf2ca1a97c64f1dba8d491cff6b935c91`, tag `v0.6-m5`)
**Implementation Commit:** `86cc3ddcbb7625723ab1fb442cac65c53be46b87`
**Accepted Pre-Merge Branch HEAD:** `cec7210cf440b9cc06c040611e477cfed9ad5472`
**Final CI Run for Accepted HEAD:** `36837924850` (Conclusion: SUCCESS across all 3 jobs)
**Development Phase:** LOCAL DEVELOPMENT ONLY (No Hetzner, no SSH, no Hermes, no deployment, no M7, no LLM calls)

---

## 1. Scope & Objective
Milestone M6 has been independently reviewed and **ACCEPTED** (verdict: PASS / ACCEPTED).
This handoff records the final verified state before merging `build/m6` to `main`:
1. **Eliminated False Historical Backfill**: Migration `0011_m6_4_historical_league_metadata.py` adds nullable `observed_league_name` and `observed_league_slug` without migration-time backfill queries. Historical snapshot rows created prior to migration 0011 retain `NULL`.
2. **Eliminated Mutable League Fallback in Evidence Selection**: `select_evidence` reads display league identity strictly from `FixtureMetadataSnapshot.observed_league_name` and `observed_league_slug` (`None` if unobserved). Mutable `Fixture` lookup is an existence-only check (`select(Fixture.id)`). `League` and `Team` tables are not joined, and placeholder sentinels (`"Unknown"`/`"unknown"`) are eliminated.
3. **Nullable Display Metadata Schema**: `SelectedFixtureInfo.league_name`, `SelectedFixtureInfo.league_slug`, and `FixtureIdentitySection.league_name`/`league_slug` are nullable (`str | None = None`). Authoritative `league_id` remains strictly non-null and verified.
4. **Truthful Quality and Provenance Reporting**: When observed league display metadata is `None`, `evaluate_data_quality` flags a structured warning (`"Observed league display identity unavailable in historical metadata snapshot"`) and records a missing field (`field="observed_league_display"`), while preserving `can_predict` (core IDs and kickoff are present). Manifest records `null` for `observed_league_name` and `observed_league_slug`.
5. **Comprehensive Pre-0011 Regression Coverage**: Unit test `test_match_context_with_none_league_display_metadata_serializes_cleanly` and 10-step integration regression test `test_legacy_pre_0011_metadata_snapshot_does_not_acquire_migration_league_values` covering steps A through J.

---

## 2. Source and Test Files Changed in M6.5

### Source Files (4):
1. `src/sports_intelligence/db/migrations/versions/0011_m6_4_historical_league_metadata.py`:
   - Removed `op.execute(UPDATE fixture_metadata_snapshots ...)` backfill query.
   - Upgrade adds `observed_league_name` (`VARCHAR(128)`, nullable) and `observed_league_slug` (`VARCHAR(64)`, nullable).
   - Downgrade drops both columns symmetrically. Pre-0011 legacy snapshots retain `NULL`.
2. `src/sports_intelligence/context/selector.py`:
   - Removed imports of `League` and `Team`.
   - Updated `SelectedFixtureInfo` fields: `league_slug: str | None = None`, `league_name: str | None = None`.
   - Simplified mutable `Fixture` locator to existence-only check: `select(Fixture.id).where(Fixture.id == fixture_id)`.
   - Eliminated fallback to mutable `League` attributes and removed `"Unknown"`/`"unknown"` string sentinels: `league_name = meta_snapshot.observed_league_name`, `league_slug = meta_snapshot.observed_league_slug`.
3. `src/sports_intelligence/context/models.py`:
   - Updated `FixtureIdentitySection`: `league_slug: str | None = None`, `league_name: str | None = None`.
4. `src/sports_intelligence/quality/engine.py`:
   - Added warning and missing_fields entry for `observed_league_display` when display fields are `None`, without adding `fixture_metadata_missing` to `critical_missing` and without blocking `can_predict`.

### Test Files (2):
5. `tests/unit/context/test_context_schema_and_hash.py`:
   - Added `test_match_context_with_none_league_display_metadata_serializes_cleanly`: verifies that `None` display metadata serializes cleanly as `"league_name":null` and `"league_slug":null`, generates a valid 64-character SHA-256 hash, and passes quality missing-field checks.
6. `tests/integration/test_m6_anti_leakage_and_context.py`:
   - Added `test_legacy_pre_0011_metadata_snapshot_does_not_acquire_migration_league_values` covering all 10 steps (A through J).

### Documentation Files (4):
7. `docs/CURRENT_TASK.md`
8. `docs/IMPLEMENTATION_STATUS.md`
9. `docs/AI_WORKLOG.md`
10. `docs/REVIEW_HANDOFF.md`

---

## 3. Historical League Metadata Truthfulness
- **The Problem**: In M6.4, migration 0011 backfilled historical `fixture_metadata_snapshots` rows using the current state of the mutable `leagues` table at migration time T1. Furthermore, `select_evidence` retained a fallback to `league_obj.name` and `"Unknown"`. This meant a snapshot captured at T0 received values read at T1, and historical replays for legacy data still leaked mutable `League` table data into historical contexts.
- **The Solution**:
  - Migration 0011 contains **zero backfill queries**. Historical snapshot rows created prior to migration 0011 retain `NULL` for `observed_league_name` and `observed_league_slug`.
  - `select_evidence` reads display league identity **strictly** from `FixtureMetadataSnapshot.observed_league_name` and `observed_league_slug`. If unobserved, values are `None`.
  - The mutable `Fixture` row is used **strictly** to verify fixture existence (`select(Fixture.id)`). `League` and `Team` tables are not joined or queried.
  - Zero `"Unknown"` or `"unknown"` placeholder sentinels exist in M6 context code.
- **Regression Verification**:
  - `test_legacy_pre_0011_metadata_snapshot_does_not_acquire_migration_league_values` proves:
    - Step A: Downgrade schema to `0010`.
    - Step B: Insert legacy `FixtureMetadataSnapshot` without observed league columns at T0.
    - Step C: Upgrade schema to `0011` at T1.
    - Step D: Verify legacy snapshot in DB has `observed_league_name IS NULL` and `observed_league_slug IS NULL` (no false backfill).
    - Step E: Construct MatchContext at `as_of` between T0 and T1.
    - Step F: MatchContext does not contain T1 mutable league values.
    - Step G: `evidence.fixture.league_name is None`, `ctx.fixture_identity.league_name is None`, while authoritative `league_id` is preserved.
    - Step H: Source manifest details record `null` for observed league columns.
    - Step I: Mutate mutable `League` row in DB at T2 (`name="Super Altered League"`, `slug="super-altered-league"`).
    - Step J: Replay at the same historical `as_of`: `source_fingerprint`, `context_hash`, and identity remain 100% byte-for-byte identical.

---

## 4. Deterministic Provider Mapping Rules (M6.4 Accepted Base)
1. **Query Ordering**: `ORDER BY provider ASC, first_seen_at DESC, external_id ASC, id ASC`.
2. **Multiple Mappings Selection**: Only mappings with `first_seen_at <= as_of_utc` are considered. The first row encountered for each provider is the most recently observed valid mapping (with deterministic tie-breakers `external_id ASC, id ASC`).
3. **List Sorting**: Downstream lists (`home_provider_mappings`, `away_provider_mappings`) are canonically sorted by `(provider, -first_seen_at.timestamp(), external_id, str(mapping_id))`.
- Regression verified: `test_provider_mapping_deterministic_selection_and_ordering_across_insertion_orders` passes across arbitrary insertion orders.

---

## 5. Immutability & Persistence Boundary Semantics
- **Attribute-Level Pydantic Freeze**:
  - Pydantic models with `ConfigDict(frozen=True)` provide **attribute-level freezing**: assigning to model fields (`ctx.fixture_identity = ...`) raises `ValidationError`.
  - However, `ConfigDict(frozen=True)` is **not recursive deep freezing**; standard Python mutable collections nested inside models (e.g., `list`, `dict`) can still be mutated in-place via collection methods (e.g. `list.append()`, `dict["k"] = v`).
- **PostgreSQL Persistence Invariant**:
  - PostgreSQL snapshots (`match_contexts`, `feature_snapshots`, and `data_quality_reports`) are treated as immutable by **application/data-lifecycle policy**.
  - Database schema does not physically prevent `UPDATE` or `DELETE` via triggers or permission revocation; immutability is an architectural invariant maintained by workers, repositories, and CAS transitions.
- **Integrity Tracking via Context Hash**:
  - `context_hash` (SHA-256) is computed from canonical sorted JSON at context assembly time and persisted alongside the snapshot for deterministic identity and integrity comparison across replays.
  - Read endpoints serve persisted snapshots with their stored `context_hash` without recomputing or cryptographically verifying the hash on every read.
- Verified in `test_match_context_immutability_attribute_frozen_and_nested_behavior`.

---

## 6. Celery Task Error Semantics (M6.4 Accepted Base)
- `src/sports_intelligence/workers/tasks/context.py` catches `HistoricalFixtureMetadataUnavailable`.
- Logs a structured warning with fixture ID, as_of timestamp, and reason (no traceback).
- Explicitly marks the Celery `Job` record as `FAILED` and records attempt in `job_attempts` with `error_class="HistoricalFixtureMetadataUnavailable"`.
- Re-raises the exception for Celery worker accounting.
- Verified in `test_historical_metadata_unavailable_task_and_refusal_persistence`.

---

## 7. Migration 0010 & 0011 Verification
- **Migration 0010**: Clean revision `0010`.
- **Migration 0011**:
  - Revision: `0011` (down_revision: `0010`).
  - Columns: `observed_league_name` (`VARCHAR(128)`, nullable), `observed_league_slug` (`VARCHAR(64)`, nullable) on `fixture_metadata_snapshots`.
  - Backfill: **NONE** (truthful legacy nullability preserved).
  - Downgrade: Drops columns `observed_league_slug` and `observed_league_name`.
  - Lifecycle: `upgrade head` -> `downgrade -1` -> `upgrade head` -> `alembic check` produces "No new upgrade operations detected" (zero drift).

---

## 8. Test & Verification Summary
- **Unit Tests**: `uv run pytest -q -m "not integration"` → **361 passed, 100 deselected in 3.73s** (100% pass)
- **Integration Tests**: `TEST_DATABASE_URL=... TEST_REDIS_URL=... uv run pytest -q -m integration` → **100 passed, 361 deselected in 15.82s** (100% pass)
- **Full Pytest**: `uv run pytest -q` → **461 passed in 17.65s** (100% pass)
- **Ruff Check**: `uv run ruff check .` → All checks passed!
- **Ruff Format**: `uv run ruff format --check .` → 177 files already formatted.
- **Mypy**: `uv run mypy src` → Success: no issues found in 119 source files.
- **Alembic**: `alembic check` → Clean, 0 drift.
- **Docker Compose**: `docker compose config -q` and `docker compose --profile telegram config -q` → Clean.

---

## 9. Next Steps
- Open PR `build/m6` -> `main`.
- Merge accepted M6 into `main`.
- Create and push release tag `v0.7-m6` on merged `main`.
- Create and push `build/m7` branch from merged `main`.
- Milestone M7 implementation is NOT STARTED. Development remains LOCAL ONLY.
