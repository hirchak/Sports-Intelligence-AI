# Current Task

**Task:** M6.5 Historical-Truthfulness Acceptance Pass (Remove False Historical Backfill, Remove Mutable League Fallback, Legacy Pre-0011 Regression Coverage)
**Status:** COMPLETED — VERIFIED LOCALLY, READY FOR COMMIT & PUSH
**Branch:** `build/m6`
**Base:** `origin/main` (`fb256ecaf2ca1a97c64f1dba8d491cff6b935c91`, tag `v0.6-m5`)

## Description
Perform the final narrowly-scoped M6.5 historical-truthfulness acceptance pass resolving the remaining review findings:
1. Remove False Historical Backfill: In migration `0011_m6_4_historical_league_metadata.py`, removed the `UPDATE fixture_metadata_snapshots` query. Pre-0011 snapshots do not acquire migration-time values from the mutable `leagues` table; legacy rows truthfully retain `NULL`. Symmetrical downgrade drops columns.
2. Remove Mutable League Fallback: In `select_evidence`, eliminated fallback to mutable `League` row attributes (`league_obj.name`/`league_obj.slug`) and eliminated placeholder sentinels (`"Unknown"`/`"unknown"`). Simplified mutable `Fixture` locator to an existence check (`select(Fixture.id)`). If not observed in historical snapshot, `league_name` and `league_slug` evaluate to `None`.
3. Model Nullability: Made `SelectedFixtureInfo.league_name`, `SelectedFixtureInfo.league_slug`, and `FixtureIdentitySection` display fields nullable (`str | None = None`).
4. Truthful Quality & Provenance Reporting: In `evaluate_data_quality`, missing observed league display identity is reported in `warnings` and `missing_fields` (`field="observed_league_display"`), while preserving `can_predict` (authoritative `league_id` and core IDs remain intact).
5. Comprehensive Legacy Regression Coverage: Added unit test `test_match_context_with_none_league_display_metadata_serializes_cleanly` and full 10-step integration regression test `test_legacy_pre_0011_metadata_snapshot_does_not_acquire_migration_league_values` covering steps A through J (schema 0010 downgrade, legacy insert at T0, migration 0011 upgrade at T1 without backfill, context build between T0 and T1, absent mutable values, truthful provenance, League mutation at T2, replay reproducibility).

## Verification
- Unit tests: 361 passed (100%)
- Integration tests: 100 passed (100%)
- Total tests: 461 passed (100%)
- Ruff lint & format: clean (177 files formatted, 0 errors)
- Mypy (119 files): clean (0 issues)
- Alembic migration check: clean (0 drift)
- Docker Compose validation: clean

## Next Steps
- Stage and commit M6.5 changes.
- Push to `origin/build/m6`.
- Monitor GitHub Actions CI until green on exact remote HEAD across all 3 jobs.
- Do NOT merge M6. Do NOT start M7. Development remains LOCAL ONLY.
