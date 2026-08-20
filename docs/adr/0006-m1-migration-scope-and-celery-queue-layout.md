# ADR-0006: M1 migration scope and Celery queue layout

**Date:** 2026-08-20  
**Status:** Accepted  
**Milestone:** M1

## Context

M1 must create the "first real migration" but must not silently pull the
future football domain schema (M2/M4/M7) forward. The task explicitly asks
for a proposal + ADR when the boundary is ambiguous. Celery also needs a
concrete queue/routing layout before any worker exists.

## Decision

### 1. Migration scope: `jobs` + `job_attempts` only

The first real migration creates exactly two tables, both from the
**Operations** group of `10_DATABASE_AND_DATA_LIFECYCLE.md` §11:

- `jobs` — job_type, fixture_id (nullable, no FK yet), status,
  idempotency_key (unique), priority, scheduled_for, correlation_id,
  created_at/updated_at (UTC);
- `job_attempts` — FK to jobs (CASCADE), attempt_number, worker,
  started_at/finished_at, status, error_class, error_message_redacted,
  unique (job_id, attempt_number).

Rationale: jobs are the core entity of the deterministic orchestrator/queue
infrastructure that M1 builds (idempotency keys are a spec §21 requirement).
Every other table group (reference, snapshots, prediction, outcomes,
experiments) belongs to its pipeline milestone and is deferred.

### 2. Celery queue layout (per `09_AGENT_CATALOG_AND_ORCHESTRATION.md` §25)

Queues: `control`, `sports_io`, `research_io`, `llm`, `evaluation`,
`notifications`. Default queue: `control` (infrastructure tasks).
Redis used as broker (`/0`) and result backend (`/1`). JSON serialization,
`enable_utc=True`, beat timezone = `APP_TIMEZONE` (Europe/Warsaw).
M1 ships one real task (`control.ping`) and an empty `beat_schedule`;
route patterns for future task modules are preconfigured but no football
tasks exist.

### 3. Resource lifecycle

One shared `AsyncEngine` + `async_sessionmaker` and one shared Redis client,
created in the FastAPI lifespan and stored on `app.state`; `/ready` uses
them (M0.1 technical debt resolved). Cleanup in lifespan shutdown.

## Alternatives

- Create the whole operations group now (`audit_logs`, `settings`,
  `external_api_requests`) — rejected: `audit_logs`/`settings` are used by
  Telegram/settings flows (M3+), `external_api_requests` by quota work (M4);
  pulling them forward creates dead tables with no consumers.
- Zero-migration M1 — rejected: the task requires a proven production-safe
  migration path; `jobs`/`job_attempts` are legitimately M1 infrastructure.
- RabbitMQ for broker — rejected: Redis is the accepted stack (spec §4) and
  already present.

## Consequences

- Alembic autogenerate/upgrade/downgrade are proven against a fresh
  PostgreSQL in tests and CI.
- Future migrations extend the schema in their own milestones without
  touching this boundary.

## Rollback/Migration

`alembic downgrade base` drops both tables; no destructive risk.
