# Current Task

**Task:** M6.3 Focused Reproducibility and Historical-Authority Pass (Recovery, Verification, CI & Documentation)
**Status:** COMPLETE (Awaiting Independent Review)
**Branch:** `build/m6`
**Base:** `origin/main` (`fb256ecaf2ca1a97c64f1dba8d491cff6b935c91`, tag `v0.6-m5`)
**Implementation Commit:** `5fb6c604617c7f93117e6d42d623a92082461981`
**GitHub Actions Run:** `36831445894` (SUCCESS)

## Description
Recovered, verified, committed, pushed, and validated all M6.3 reproducibility and historical-authority implementation files on `build/m6`. Resolved the remote delivery mismatch from `fe8f6145c86e1d5f133d69b1e488aea05b20089f`.

## Outcomes
- **Historical Fixture Metadata Authority**: Context builder raises `HistoricalFixtureMetadataUnavailable` when no `FixtureMetadataSnapshot` exists `<= as_of`. No fallback to mutable canonical `Fixture` metadata. Refuses to persist incomplete/speculative `FeatureSnapshot`, `DataQualityReport`, or `MatchContext`.
- **End-to-End Metadata Team IDs**: All downstream evidence selection (provider entity mappings, standings, team stats, form, availability, lineups) strictly uses `fixture_info.home_team_id` and `fixture_info.away_team_id` from the snapshot.
- **Provider Mapping Provenance**: Added `provider_mappings` section to the source manifest capturing provider entity lookups evaluated historically (`first_seen_at <= as_of_utc`).
- **Deterministic Source Manifest Fingerprint**: Canonical SHA-256 fingerprint generated from the complete source manifest (fixture metadata, evidence snapshots, provider mappings).
- **Explicit Freshness Policy & Fingerprint**: Introduced `FreshnessPolicy` dataclass with `freshness_policy_snapshot` and deterministic SHA-256 `freshness_policy_fingerprint`. Persisted in `data_quality_reports.freshness_policy_fingerprint` via migration 0010.
- **ContextBuildPolicy**: Combines `QualityPolicy` and `FreshnessPolicy`, producing a deterministic `build_config_fingerprint` embedded in Celery task idempotency keys.
- **Strict Pydantic MatchContext Schema**: Enforced `ConfigDict(extra="forbid", frozen=True)` across all 13 sections and root `MatchContextV1`.
- **Full Verification**: 357 unit tests, 96 integration tests, 453 total pytest passing. Ruff lint and format clean. Mypy 118 source files clean. Alembic upgrade/downgrade/check verified with zero schema drift. Docker compose config valid. GitHub Actions run 36831445894 succeeded 100%.

## Next Steps
- Await independent review of M6.3.
- DO NOT merge M6 into `main`.
- DO NOT start M7.
- Development remains strictly LOCAL ONLY.
