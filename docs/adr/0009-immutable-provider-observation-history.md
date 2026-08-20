# ADR-0009: Immutable provider observation history (content/observation split)

**Date:** 2026-08-20  
**Status:** Accepted  
**Milestone:** M2.1

## Context

The M2 design deduplicated raw evidence by payload hash
(`raw_provider_payloads` unique on provider+endpoint_family+payload_hash).
Review finding: content dedup must not destroy immutable observation
history — two identical payloads retrieved at different times must both
leave evidence of their retrieval events, so a future replay can determine
which snapshot was actually available at a given `as_of`
(`14_DATA_QUALITY_PROVENANCE_AND_LEAKAGE.md`).

## Decision

Split storage into two tables:

1. `raw_provider_payloads` (content/blob) — deduplicated content:
   `provider`, `endpoint_family`, `payload_hash` (unique), `payload` JSONB,
   `first_seen_at`. No per-request fields.
2. `provider_observations` (event/snapshot record) — one row per retrieval
   event, append-only and immutable: `payload_id` FK, `provider`,
   `endpoint_family`, `request_fingerprint`, `retrieved_at` (the time the
   final response was received), `response_status` (nullable).

Every discovery run stores the content once (ON CONFLICT DO NOTHING,
fetching the existing id) and ALWAYS appends a new observation row.
Replay can select observations with `retrieved_at <= as_of` and join the
referenced payload — the available snapshot at `as_of` is exactly the
payload referenced by the latest observation before it.

## Alternatives

- Duplicate the full JSONB per event — rejected: large duplicate storage
  for identical content.
- Single table with a counter — rejected: loses per-event `retrieved_at`
  and fingerprint without a second table anyway.

## Consequences

- Immutable history with bounded storage growth.
- `DiscoverySummary.raw_payload_stored` now means "new content stored"
  (dedup hit reports False); observation rows are appended unconditionally.

## Rollback/Migration

`alembic downgrade 0002` drops `provider_observations` and restores the
old columns on `raw_provider_payloads` (data migration reverses: latest
observation per payload is folded back).
