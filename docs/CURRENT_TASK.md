# Current Task

**Task:** M6.3 Focused Reproducibility and Historical-Authority Pass
**Status:** COMPLETE (Awaiting Review)

## Description
Implemented and verified all final reproducibility and historical-authority fixes for M6.3 on `build/m6`.

## Outcomes
- Fixed all legacy historical fixture authority gaps: Context builder correctly throws `HistoricalFixtureMetadataUnavailable` when no metadata snapshot exists <= `as_of`.
- Updated Metadata snapshot usage: Context strictly uses `FixtureMetadataSnapshot` for team names, league IDs, and venue fields, never falling back to mutable canonical `Fixture`.
- Made provider entity mappings part of provenance: Extracted mappings are recorded and isolated historically.
- Explicit freshness policies: Introduced `FreshnessPolicy` to resolve settings configurations and manage staleness mathematically.
- Included freshness policies in build configs: `ContextBuildPolicy` wraps quality and freshness configurations, producing a complete reproducible fingerprint.
- Removed arbitrary generic provider IDs from Context output in favor of full mapping objects.
- Finished strict Pydantic schemas for all MatchContextV1 sections.
- Kept all accepted M6.2 architectures.

## Next Steps
- Stop and await independent review of M6.3.
- DO NOT MERGE M6.
- DO NOT START M7.
