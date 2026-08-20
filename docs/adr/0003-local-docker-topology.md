# ADR-0003: Local Docker topology (project, ports, volumes)

**Date:** 2026-08-20  
**Status:** Accepted  
**Milestone:** M0

## Context

Master spec §6 requires its own Compose project name, network, containers and
volumes, and forbids public exposure of Postgres/Redis. Hermes isolation
requires predictable, non-conflicting local ports.

## Decision

- Compose project name: `sports-intel` (matches production naming).
- Services in M0: `sports-postgres` (postgres:16-alpine),
  `sports-redis` (redis:7-alpine), `sports-api` (local Dockerfile).
- Named volumes: `sports_intel_pgdata`, `sports_intel_redisdata`.
- Host ports bound to loopback only:
  - Postgres `127.0.0.1:5433 -> 5432`
  - Redis `127.0.0.1:6380 -> 6379`
  - API `127.0.0.1:8000 -> 8000`
- Non-standard Postgres/Redis host ports reduce collision risk with other
  local software. Container-internal ports remain standard.
- The API container receives container-network URLs (`postgres:5432`,
  `redis:6379`) via explicit `environment:` overrides, while `.env.example`
  holds host-side URLs for local tooling.

## Alternatives

- Standard host ports 5432/6379 — rejected: likely to conflict with existing
  local services.

## Consequences

- Deterministic local bootstrap; no Hermes port/volume overlap.
- Host tools (psql, redis-cli) and the API container use different connection
  strings; this is documented in `.env.example` and `docs/LOCAL_DEVELOPMENT.md`.

## Rollback/Migration

Ports are configuration-only; changing them does not affect application code.
