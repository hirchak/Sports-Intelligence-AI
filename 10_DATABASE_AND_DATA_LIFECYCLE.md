# Database and Data Lifecycle
## PostgreSQL Schema, Snapshot Strategy and Portability

PostgreSQL is the source of truth for runtime state.

GitHub is the source of truth for code, schemas, migrations and configuration templates.

The database itself must **not** be committed to Git.

---

# 1. Design goals

The data model must support:

- reproducible predictions;
- provider changes;
- many leagues;
- many seasons;
- many prediction models;
- morning vs pre-match predictions;
- evaluation;
- historical replay;
- data retention;
- later migration from laptop to Hetzner.

---

# 2. Time policy

Store all timestamps as UTC in PostgreSQL.

Display using configured timezone:

```text
Europe/Warsaw
```

Every snapshot has:

```text
observed_at
retrieved_at
valid_for/as_of semantics where relevant
```

Do not use local-time-only database columns for event truth.

---

# 3. Primary keys

Use UUID internal IDs.

Never use provider fixture/team IDs as internal primary keys.

Provider mapping table:

```text
provider_entity_ids
- id UUID
- provider
- entity_type
- external_id
- internal_entity_id
- first_seen_at
- last_seen_at
```

Unique:

```text
(provider, entity_type, external_id)
```

---

# 4. Reference tables

## leagues

```text
id
slug
name
country
enabled
created_at
updated_at
```

## seasons

```text
id
league_id
name/year
starts_at
ends_at
active
```

## teams

```text
id
name
country
logo_url optional
created_at
updated_at
```

## fixtures

```text
id
league_id
season_id
home_team_id
away_team_id
kickoff_at
venue
round
status
home_score nullable
away_score nullable
created_at
updated_at
```

Important indexes:

```text
fixtures(kickoff_at)
fixtures(league_id, kickoff_at)
fixtures(status, kickoff_at)
fixtures(home_team_id, kickoff_at)
fixtures(away_team_id, kickoff_at)
```

---

# 5. Raw provider payloads

Purpose:
- auditability;
- adapter debugging;
- exact historical evidence.

Suggested:

```text
raw_provider_payloads
- id
- provider
- endpoint_family
- request_fingerprint
- payload_hash
- payload_jsonb
- retrieved_at
- response_status
- source_fixture_id nullable
- expires_at nullable
```

Deduplicate identical payload bodies with `payload_hash`.

A new reference can point to an existing payload when content is identical.

PostgreSQL JSONB/TOAST handles reasonably sized payloads; large long-term archives may later move to object storage.

---

# 6. Snapshot tables

Do not overwrite important historical snapshots.

## standings_snapshots

Key dimensions:
- league
- season
- captured_at

## team_form_snapshots

```text
team_id
as_of
window_size
scope (overall/home/away)
metrics_jsonb
source_version
```

## team_statistics_snapshots

```text
team_id
league_id
season_id
captured_at
metrics_jsonb
```

## availability_snapshots

```text
fixture_id
team_id
captured_at
players_jsonb
impact_flags_jsonb
conflicts_jsonb
```

## lineup_snapshots

```text
fixture_id
team_id
captured_at
confirmed boolean
formation
players_jsonb
```

## odds_snapshots

Prefer normalized rows plus snapshot metadata.

Metadata:

```text
odds_snapshot_sets
- id
- fixture_id
- captured_at
- provider
```

Rows:

```text
odds_prices
- id
- snapshot_set_id
- bookmaker
- market
- selection
- decimal_odds
- implied_probability
- no_vig_probability nullable
```

Indexes:

```text
(fixture_id, captured_at desc)
(snapshot_set_id, market)
```

## research_documents

```text
id
fixture_id
url
domain
title
published_at
retrieved_at
content_hash
relevance_score
```

## research_claims

```text
id
document_id
fixture_id
team_id nullable
claim_type
claim_text
confidence
valid_from nullable
valid_until nullable
```

---

# 7. Feature and context tables

## feature_snapshots

```text
id
fixture_id
forecast_phase
as_of
schema_version
features_jsonb
source_fingerprint
created_at
```

Unique enough to prevent accidental duplicate generation.

## match_contexts

```text
id
fixture_id
forecast_phase
as_of
schema_version
context_jsonb
context_hash
data_quality_report_id
feature_snapshot_id
created_at
```

`context_hash` makes exact reproducibility easy.

Never mutate an existing context after prediction.

---

# 8. Model and prompt version tables

## prompt_versions

```text
id
prompt_name
semantic_version
git_commit
content_hash
created_at
active
```

Prompt source remains in Git.

DB stores runtime identity.

## model_configs

```text
id
provider
model_id
temperature
max_tokens
structured_mode
config_jsonb
created_at
```

Never store secret keys here.

---

# 9. Prediction tables

## prediction_runs

```text
id
fixture_id
match_context_id
forecast_phase
model_config_id
prompt_version_id
status
started_at
completed_at
latency_ms
input_tokens nullable
output_tokens nullable
provider_request_id nullable
error_code nullable
```

## market_predictions

```text
id
prediction_run_id
market
selection
model_probability
confidence
evidence_for_jsonb
evidence_against_jsonb
risk_flags_jsonb
```

## ranked_candidates

```text
id
prediction_run_id
market_prediction_id
odds_snapshot_set_id nullable
captured_odds nullable
market_no_vig_probability nullable
edge nullable
expected_value nullable
rank
displayed boolean
filter_reason nullable
```

---

# 10. Result and evaluation tables

## fixture_results

```text
fixture_id unique
status
home_score
away_score
extra_time_home nullable
extra_time_away nullable
penalties_home nullable
penalties_away nullable
provider
confirmed_at
```

## prediction_settlements

```text
id
market_prediction_id
result
settled_at
settlement_version
```

Result enum:

```text
WIN
LOSS
PUSH
VOID
UNSETTLED
```

## evaluation_runs

```text
id
period_start
period_end
created_at
config_version
```

## evaluation_metrics

Dimensions:

```text
evaluation_run_id
metric_name
metric_value
sample_size
league_id nullable
market nullable
model_config_id nullable
prompt_version_id nullable
forecast_phase nullable
bucket nullable
```

---

# 11. Jobs and operations

## jobs

```text
id
job_type
fixture_id nullable
status
idempotency_key unique
priority
scheduled_for
created_at
updated_at
correlation_id
```

## job_attempts

```text
id
job_id
attempt_number
worker
started_at
finished_at
status
error_class
error_message_redacted
```

## audit_logs

Store:
- manual analyze;
- settings changes;
- experiment approvals;
- important admin actions.

---

# 12. Configuration persistence

Static defaults live in Git YAML.

Runtime-overridable settings can live in DB.

Example:

```text
settings
- key
- value_jsonb
- version
- updated_at
- updated_by
```

Every high-impact setting change gets an audit record.

---

# 13. Retention strategy

Do not delete data that is required to reconstruct a published prediction.

## Keep indefinitely initially

- fixtures;
- MatchContexts used for predictions;
- feature snapshots used for predictions;
- prediction runs;
- market predictions;
- odds snapshot referenced by a displayed prediction;
- results;
- settlements;
- evaluation metrics;
- prompt/model metadata.

## Deduplicate / prune more aggressively

- duplicate raw payloads;
- unused research search candidates;
- operational logs;
- intermediate snapshots never referenced by a prediction.

Suggested policy should be configurable, e.g.:

```text
job logs: 30–90 days
unreferenced raw payloads: 30–90 days
referenced raw prediction evidence: longer/indefinite
```

Do not hard-delete before a cleanup report shows what will be removed.

---

# 14. Database size philosophy

For a private football system, structured metadata is relatively small compared with media workloads.

The main growth risks are:

- storing duplicate raw JSON repeatedly;
- saving full web pages;
- excessively frequent odds snapshots;
- verbose logs.

Controls:

- content hashes;
- retention;
- normalized odds;
- bounded research excerpts/claims;
- log rotation;
- configurable odds refresh frequency.

Do not prematurely introduce a separate data warehouse.

---

# 15. Local storage

During local development:

- PostgreSQL lives in a Docker named volume on the laptop;
- Redis is disposable;
- source code lives in Git;
- secrets live in local `.env`;
- DB data is not pushed to GitHub.

Example conceptual volumes:

```text
sports_intel_pgdata
sports_intel_redisdata
```

---

# 16. Migration to Hetzner

Migration path:

```text
local Postgres
→ freeze local writes
→ pg_dump
→ copy dump securely
→ start production Postgres
→ run migrations
→ pg_restore
→ verify counts/hashes
→ start workers/bot
```

If production is intended to start fresh, skip data restore and create a clean DB.

Never copy Docker volume directories manually between operating systems.

Use PostgreSQL dump/restore.

---

# 17. Schema migrations

Alembic required.

Rules:

- every schema change has migration;
- migration tested from empty DB;
- migration tested from previous milestone DB where practical;
- migration checked into Git;
- destructive migration requires backup/ADR.

---

# 18. Database acceptance criteria

- [ ] Fresh DB can migrate to latest.
- [ ] Provider IDs do not serve as internal PKs.
- [ ] Prediction can reconstruct exact MatchContext.
- [ ] Old prediction snapshots are immutable.
- [ ] Duplicate raw payloads can be deduplicated.
- [ ] Fixture query by date/league is indexed.
- [ ] Latest odds query is indexed.
- [ ] Jobs have unique idempotency keys.
- [ ] Local data can be exported with `pg_dump`.
- [ ] Restore test works.
