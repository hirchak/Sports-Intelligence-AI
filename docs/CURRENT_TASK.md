# Current Task

**Task:** M6.4 Acceptance-Fix Pass (Historical League Authority, Deterministic Provider Mappings, Immutability Audit, Task Semantics)
**Status:** COMPLETED — VERIFIED LOCALLY, READY FOR COMMIT & PUSH
**Branch:** `build/m6`
**Base:** `origin/main` (`fb256ecaf2ca1a97c64f1dba8d491cff6b935c91`, tag `v0.6-m5`)

## Description
Perform a narrowly scoped M6.4 acceptance-fix pass resolving review findings:
1. Historical League Metadata Authority: eliminated dependence on mutable `League.slug` and `League.name` for historical MatchContext replay by capturing `observed_league_name` and `observed_league_slug` on `FixtureMetadataSnapshot` via migration 0011.
2. Deterministic Provider Mapping Selection and Order: explicit deterministic query ordering (`provider.asc(), first_seen_at.desc(), external_id.asc(), id.asc()`), latest `<= as_of` selection per provider, and canonical sort ordering in `SelectedFixtureInfo`, `source_manifest`, and `MatchContext`.
3. MatchContext Immutability Audit: reconciled documentation and test suite regarding attribute-level Pydantic freeze vs deep nested container immutability, clarifying that PostgreSQL immutable snapshots (`match_contexts`) form the authoritative boundary. Added test `test_match_context_immutability_attribute_frozen_and_nested_behavior`.
4. Celery Task Error Semantics: `HistoricalFixtureMetadataUnavailable` is logged cleanly as a warning with structured metadata (zero unhandled tracebacks) while marking Celery job `FAILED` in the database ledger (`jobs` and `job_attempts`) and re-raising for worker accounting.
5. Migration & Doc Hygiene: fixed migration 0010 revision docstring, created migration 0011 with clean backfill and symmetrical downgrade, zero Alembic drift.

## Verification
- Unit tests: 360 passed (100%)
- Integration tests: 99 passed (100%)
- Total tests: 459 passed (100%)
- Ruff lint & format: clean
- Mypy (119 files): clean
- Alembic migration check: clean (0 drift)
- Docker Compose validation: clean

## Next Steps
- Stage and commit M6.4 changes.
- Push to `origin/build/m6`.
- Monitor GitHub Actions CI until green on exact remote HEAD.
- Do NOT merge M6. Do NOT start M7. Development remains LOCAL ONLY.
