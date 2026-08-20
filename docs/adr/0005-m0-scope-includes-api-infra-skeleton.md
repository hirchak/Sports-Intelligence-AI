# ADR-0005: M0 scope includes API/infrastructure skeleton

**Date:** 2026-08-20  
**Status:** Accepted  
**Milestone:** M0

## Context

Master spec §36 assigns FastAPI, Postgres, Redis, Celery, migrations and
structured logs to M1. However the user's explicit M0 instruction and
`19_PROMPT_TO_START_DEEPSEEK.md` require FastAPI skeleton, PostgreSQL/Redis
service definitions, config validation and logging foundation already in M0.
User instructions take precedence over specs.

## Decision

M0 delivers the *skeleton* level of those items:

- FastAPI app factory with `GET /health` and `GET /ready`;
- Docker Compose definitions for Postgres 16 and Redis 7 with health checks;
- `Settings` with startup validation and mock mode;
- structured JSON logging foundation;
- Alembic scaffold (no revisions yet);
- no database models, no Celery, no aiogram.

The full M1 scope (Celery + Beat, database models, first real migration,
queue plumbing) remains in M1.

## Alternatives

- Strict master-spec M0 (config+CI only) — rejected: it contradicts the
  explicit user instruction.

## Consequences

- M1 starts from a verified skeleton instead of a blank repository.
- Reviewers must judge M0 by the combined checklist (user instruction), not by
  master §36 alone.

## Rollback/Migration

None required; scope split between M0/M1 is documented here.
