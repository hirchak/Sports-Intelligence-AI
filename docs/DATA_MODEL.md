# Data Model

Status: **M2** — discovery schema implemented (migration 0002); odds/research/
prediction tables arrive in M4+.
Authoritative design: `10_DATABASE_AND_DATA_LIFECYCLE.md`.

## Principles (from spec)

- PostgreSQL is the runtime source of truth; GitHub stores code/schema/migrations.
- UUID internal primary keys; provider IDs stored separately in
  `provider_entity_ids (provider, entity_type, external_id)` with unique
  `(provider, entity_type, external_id)`.
- All timestamps UTC in the database; display in `Europe/Warsaw`.
- Snapshots are immutable once referenced by a prediction.
- Raw provider payloads deduplicated by `payload_hash`.
- Alembic for every schema change; destructive migration requires ADR.

## Planned entities (implemented in M1+)

| Group        | Tables                                                                     |
|--------------|----------------------------------------------------------------------------|
| Reference    | `leagues`, `seasons`, `teams`, `fixtures`, `provider_entity_ids`            |
| Snapshots    | `raw_provider_payloads`, `standings_snapshots`, `team_form_snapshots`, `team_statistics_snapshots`, `availability_snapshots`, `lineup_snapshots`, `odds_snapshot_sets`, `odds_prices`, `research_documents`, `research_claims`, `data_quality_reports`, `feature_snapshots`, `match_contexts` |
| Prediction   | `prediction_runs`, `market_predictions`, `ranked_candidates`, `prompt_versions`, `model_configs` |
| Outcomes     | `fixture_results`, `prediction_settlements`, `evaluation_runs`, `evaluation_metrics` |
| Experiments  | `experiments`, `experiment_variants`, `experiment_results`, `improvement_proposals` |
| Operations   | `jobs`, `job_attempts`, `audit_logs`, `settings`                             |

Key access paths must be indexed: `fixtures(kickoff_at)`,
`fixtures(league_id, kickoff_at)`, `fixtures(status, kickoff_at)`,
`odds_prices(snapshot_set_id, market)`, `jobs.idempotency_key` unique.

## Implemented in M1 (migration 0001)

### jobs

`id` (UUID PK), `job_type`, `fixture_id` (nullable, no FK yet), `status`
(indexed), `idempotency_key` (unique), `priority`, `scheduled_for`,
`created_at`/`updated_at` (UTC), `correlation_id`.

### job_attempts

`id` (UUID PK), `job_id` (FK → jobs, CASCADE), `attempt_number`, `worker`,
`started_at`/`finished_at`, `status`, `error_class`,
`error_message_redacted`; unique `(job_id, attempt_number)`.

Scope decision: ADR-0006.

## Implemented in M2 (migration 0002)

- `leagues` — slug unique, name, country, enabled.
- `seasons` — league FK, name, unique (league_id, name).
- `teams` — name, country.
- `fixtures` — league/season/team FKs, kickoff_at (UTC, indexed),
  venue/round nullable, status; unique natural key
  (league_id, home_team_id, away_team_id, kickoff_at); indexes for
  kickoff/league/status lookups.
- `provider_entity_ids` — provider + entity_type + external_id → internal
  UUID; unique identity; never a primary key.
- `raw_provider_payloads` — provider, endpoint_family, request_fingerprint,
  payload_hash, JSONB payload, retrieved_at; hash-deduplicated.

Upsert strategy and scope decision: ADR-0008. All timestamps UTC.

## Migration workflow

1. edit/add SQLAlchemy models;
2. `alembic revision --autogenerate -m "..."`;
3. review the generated migration;
4. `make migrate` against local compose Postgres;
5. commit the migration file.

Migrations are verified in CI on a fresh PostgreSQL: apply → repeat →
downgrade → reapply (integration test `test_db_resources.py`).
