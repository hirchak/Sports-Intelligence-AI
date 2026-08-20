# Architecture

Status: M0 skeleton — boundaries defined, business logic arrives in later milestones.

## Layered boundaries

```text
Telegram UI
    ↓
application/control layer
    ↓
orchestrator/jobs
    ↓
collectors/providers
    ↓
PostgreSQL snapshots
    ↓
deterministic features
    ↓
MatchContext
    ↓
LLM prediction
    ↓
deterministic validation/ranking
    ↓
persistence/publishing
```

## Non-negotiable rules

- Telegram contains no prediction/business logic.
- Orchestrator is deterministic.
- LLM is not the scheduler.
- LLM does not settle results.
- LLM does not calculate basic odds math.
- Providers are behind adapters.
- MatchContext is immutable after prediction.
- Every prediction has `as_of`.
- Historical replay cannot use future data.
- Improvement agents cannot silently mutate production.

## Components (current state)

| Component            | Milestone | State in M0                                        |
|----------------------|-----------|----------------------------------------------------|
| FastAPI control API  | M1        | Skeleton: `GET /health`, `GET /ready`              |
| PostgreSQL 16        | M1        | Compose service + async engine factory; no models  |
| Redis 7              | M1        | Compose service; readiness check only              |
| Celery + Beat        | M1        | Not present (deferred)                             |
| Alembic              | M1        | Scaffold configured, zero revisions                |
| Structured logging   | M1        | JSON formatter + context fields (correlation/job)  |
| Sports provider      | M2        | `SportsDataProvider` Protocol only                 |
| Odds provider        | M4        | `OddsProvider` Protocol only                       |
| Search provider      | M5        | `SearchProvider` Protocol only                     |
| LLM provider         | M7        | `LLMProvider` Protocol + `LLMResult` only          |
| Telegram bot         | M3        | Reserved package                                  |
| Feature/context/…    | M6+       | Reserved packages                                  |

## Config and modes

`Settings` (pydantic-settings) validates at startup:

- `APP_ENV` in `mock | sandbox | live_local`;
- non-mock modes require API keys for every configured provider;
- unknown environment variables are rejected (`extra="forbid"`).

See `docs/adr/0004-runtime-modes-and-config-validation.md`.

## Docker topology

Compose project `sports-intel`: `sports-postgres`, `sports-redis`,
`sports-api`. Named volumes `sports_intel_pgdata` / `sports_intel_redisdata`.
All host ports bound to 127.0.0.1 only (5433/6380/8000).
See `docs/adr/0003-local-docker-topology.md`.

## Decision records

- `docs/adr/0001-python-package-manager-uv.md`
- `docs/adr/0002-repository-layout-src.md`
- `docs/adr/0003-local-docker-topology.md`
- `docs/adr/0004-runtime-modes-and-config-validation.md`
- `docs/adr/0005-m0-scope-includes-api-infra-skeleton.md`
