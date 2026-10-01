# Current Task

**Task:** Finalize Independently Accepted Milestone M6 (Phase A — Documentation Cleanup & Merge Preparation)
**Status:** M6 ACCEPTED — DOCS CLEANUP IN PROGRESS
**Branch:** `build/m6`
**Base:** `origin/main` (`fb256ecaf2ca1a97c64f1dba8d491cff6b935c91`, tag `v0.6-m5`)

## Milestone Acceptance Status
- **Milestone:** M6 (M6.5 Historical-Truthfulness Acceptance Pass)
- **Independent Review Verdict:** **PASS / ACCEPTED**
- **Accepted Pre-Merge Branch HEAD:** `cec7210cf440b9cc06c040611e477cfed9ad5472`
- **Implementation Commit:** `86cc3ddcbb7625723ab1fb442cac65c53be46b87`
- **Final CI Run for Accepted HEAD:** `36837924850` (Conclusion: SUCCESS across all 3 jobs)
- **Branch Pushed:** Yes (`origin/build/m6` synchronized with local HEAD)

## Summary of Accepted M6 Behavior
1. **Historical Metadata & Anti-Leakage Authority**:
   - Strict refusal via `HistoricalFixtureMetadataUnavailable` when no metadata snapshot exists `<= as_of`.
   - Migration 0011 contains zero migration-time backfill from mutable tables; legacy pre-0011 snapshots truthfully retain `NULL` for `observed_league_name` and `observed_league_slug`.
   - Evidence selector reads league identity strictly from metadata snapshot (`None` if unobserved), completely eliminating mutable `League` fallback queries and placeholder string sentinels.
   - Tested and verified: historical MatchContext identity, source fingerprint, and context hash are 100% reproducible and invariant to subsequent mutations of the `League` row.
2. **Deterministic Provider Mapping Selection & Ordering**:
   - Explicit SQL ordering: `ORDER BY provider ASC, first_seen_at DESC, external_id ASC, id ASC`.
   - Deterministic selection of latest mapping `<= as_of` per provider; exclusion of future mappings (`first_seen_at > as_of`).
   - Canonical list sorting: `(provider, -first_seen_at.timestamp(), external_id, str(mapping_id))`.
3. **Pydantic Immutability & Persistence Boundary**:
   - `ConfigDict(frozen=True)` enforces attribute-level freezing.
   - Immutable persistence boundary enforced by application/data-lifecycle policy on `match_contexts`, `feature_snapshots`, and `data_quality_reports`.
   - SHA-256 `context_hash` persisted for deterministic identity and integrity comparison.
4. **Celery Task Error Semantics**:
   - Clean structured warning on `HistoricalFixtureMetadataUnavailable` (zero traceback dumps).
   - Marks Celery job `FAILED` in `jobs` and `job_attempts` ledger; re-raises for worker failure accounting.
   - Zero context, feature, or quality records persisted on refusal.

## Verification
- Unit tests: 361 passed (100%)
- Integration tests: 100 passed (100%)
- Total tests: 461 passed (100%)
- Ruff lint & format: clean (177 files formatted, 0 errors)
- Mypy (119 files): clean (0 issues)
- Alembic migration check: clean (0 drift)
- Docker Compose validation: clean

## Next Actions
1. Complete docs-only commit on `build/m6` and push.
2. Verify GitHub Actions CI run on docs-only HEAD.
3. Open PR `build/m6` -> `main`.
4. Merge accepted M6 into `main`.
5. Create and push annotated release tag `v0.7-m6` on merged `main`.
6. Create and push `build/m7` from merged `main` (M7 NOT STARTED).
