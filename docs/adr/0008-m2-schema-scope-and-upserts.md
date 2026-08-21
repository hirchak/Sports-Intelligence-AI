# ADR-0008: M2 database schema scope and upsert strategy

**Date:** 2026-08-20  
**Status:** Accepted  
**Milestone:** M2

## Context

M2 needs persistence only for fixture discovery. The user's M2 task defines
the table set explicitly; this ADR pins down identities, uniqueness and the
idempotency strategy.

## Decision

Migration `0002` creates exactly six tables:

1. `leagues` — UUID PK, `slug` unique, name, country (nullable), enabled.
2. `seasons` — UUID PK, `league_id` FK, name/year, `starts_at`/`ends_at`
   (nullable), active; unique `(league_id, name)`.
3. `teams` — UUID PK, name, country (nullable).
4. `fixtures` — UUID PK, FKs to leagues/seasons/teams, `kickoff_at`
   (timestamptz), venue/round (nullable), status; unique
   `(league_id, home_team_id, away_team_id, kickoff_at)`; indexes on
   `(kickoff_at)`, `(league_id, kickoff_at)`, `(status, kickoff_at)`.
5. `provider_entity_ids` — UUID PK, provider, entity_type, external_id,
   `internal_entity_id` (UUID), first/last seen; unique
   `(provider, entity_type, external_id)`; index on `internal_entity_id`.
6. `raw_provider_payloads` — UUID PK, provider, endpoint_family,
   request_fingerprint, payload_hash, payload JSONB, retrieved_at,
   response_status (nullable); unique `(provider, endpoint_family,
   payload_hash)` for hash-based dedup.

Provider IDs are never internal primary keys. All timestamps UTC.

Upsert strategy: PostgreSQL `INSERT … ON CONFLICT DO UPDATE/NOTHING`
through SQLAlchemy `dialect.postgresql.insert`:

- leagues/teams/seasons/fixtures upsert by their unique keys (DO UPDATE on
  mutable fields where meaningful);
- provider mappings DO NOTHING on conflict (identity is immutable);
- raw payloads DO NOTHING on hash conflict (dedup);
- discovery is fully idempotent: re-running yields zero duplicates.

## Alternatives

- `SELECT` + `INSERT` in application code — rejected: race-prone under
  concurrent discovery jobs.
- Full football domain schema now — rejected (scope guard; odds/research/
  prediction tables arrive with M4+).

## Consequences

- Future milestones extend this schema with new migrations; nothing here
  needs destructive rework.
- `internal_entity_id` in `provider_entity_ids` intentionally carries no FK
  so one mapping table serves leagues/teams/fixtures/seasons uniformly.

## Rollback/Migration

`alembic downgrade 0001` drops the six tables (no production data yet).

---

# Amendment (M2.1)

1. **Indexes reconciled.** The original ADR text listed composite indexes
   `(league_id, kickoff_at)` and `(status, kickoff_at)`, but migration 0002
   created single-column indexes only. Migration 0003 creates the real
   composite indexes `ix_fixtures_league_kickoff` and
   `ix_fixtures_status_kickoff` and drops the redundant single-column
   `ix_fixtures_league_id` / `ix_fixtures_status` (covered by the
   composites' leading columns). `ix_fixtures_kickoff_at` stays for
   date-only queries.
2. **Atomic identity acquisition.** The find → create entity → mapping
   `DO NOTHING` path was race-prone for entities without a natural key
   (teams, fixtures). Both now use a single-statement PostgreSQL CTE
   arbiter: the unique mapping insert decides the winner, and the entity
   row is created with the mapping's internal id inside the same statement.
   Concurrent discoveries therefore produce exactly one entity row and one
   mapping. Leagues stay slug-based (slug is the deterministic natural
   identity) with mapping insert `DO NOTHING` + re-select.
3. **League `enabled` sync.** `upsert_league_id` now updates `enabled` on
   conflict, so seed/config changes propagate false → true → false.
4. **Evidence model.** Raw evidence restructured per ADR-0009
   (content/observation split).
