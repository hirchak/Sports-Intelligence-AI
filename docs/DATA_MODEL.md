# Data Model

Status: **planned** — no SQLAlchemy models and no migrations exist in M0.
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

## Migration workflow (from M1)

1. edit/`add` SQLAlchemy models;
2. `alembic revision --autogenerate -m "..."`;
3. review the generated migration;
4. `make migrate` against local compose Postgres;
5. commit the migration file.

M0 status: `alembic.ini` + async `env.py` configured and verified against the
local Postgres (`alembic upgrade head` runs with zero revisions and creates
the `alembic_version` table).
