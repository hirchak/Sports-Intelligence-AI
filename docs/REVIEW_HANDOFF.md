# Review Handoff: M6.3 Reproducibility and Historical-Authority Pass

## Context
Branch: `build/m6`
Milestone: M6

This is the focused M6.3 reproducibility and historical-authority pass requested after the M6.2 failure.

## Changes Made
1. **Fix Legacy Historical Fixture Authority Completely**: Context building correctly relies strictly on `FixtureMetadataSnapshot`. It explicitly blocks falling back to mutable `Fixture` metadata when evaluating historical periods. If no snapshot exists `HistoricalFixtureMetadataUnavailable` is thrown.
2. **Use Metadata Snapshot Team IDs End-to-End**: Team/League fields are pulled safely from `FixtureMetadataSnapshot`.
3. **Canonicalize the Entire Source Manifest Fingerprint**: Manifest serialization is fully deterministic.
4. **Explicit Freshness Policy Identity**: Introduced `FreshnessPolicy` and wrapped inside `ContextBuildPolicy` to manage evaluation freshness cleanly.
5. **Strict MatchContext Schema**: Pydantic `ConfigDict(extra="forbid", frozen=True)` is enforced across all 13 MatchContextV1 sections.
6. **Tests Fixed**: Adjusted 350 unit tests and 93 integration tests to abide by strict Pydantic dot notation (`ctx.section.field` vs `ctx["section"]["field"]`) and proper instantiation of `ContextBuildPolicy`. Exception assertions were corrected to handle `HistoricalFixtureMetadataUnavailable`.

## Verification Status
- Lint & Format: PASS
- Mypy: PASS
- Unit Tests: PASS (350)
- Integration Tests: PASS (93)
- Migration Tests: PASS
- Database Schema: Unchanged since M6.2 (Migrations preserved byte-for-byte relative to origin/main base).

## Pending Review
Reviewers: please verify M6.3 compliance. No deployment, M7, or Hermes work has been conducted. Local development only.
