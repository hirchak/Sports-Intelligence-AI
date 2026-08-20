# Architecture

Status: M1 — core infrastructure implemented; business logic arrives in later milestones.

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

| Component            | Milestone | State in M1                                        |
|----------------------|-----------|----------------------------------------------------|
| FastAPI control API  | M1        | `/health`, `/ready`; lifespan-managed resources    |
| PostgreSQL 16        | M1        | Compose service; shared async engine; `jobs`/`job_attempts` |
| Redis 7              | M1        | Compose service; shared client; Celery broker/backend |
| Celery + Beat        | M1        | App + worker + beat; 6 queues; `control.ping` task |
| Alembic              | M1        | First migration (0001) applied/downgraded in CI    |
| Structured logging   | M1        | JSON formatter + context fields (correlation/job)  |
| Sports provider      | M2        | `SportsDataProvider` Protocol only                 |
| Odds provider        | M4        | `OddsProvider` Protocol only                       |
| Search provider      | M5        | `SearchProvider` Protocol only                     |
| LLM provider         | M7        | `LLMProvider` Protocol + `LLMResult` only          |
| Telegram bot         | M3        | Reserved package                                  |
| Feature/context/…    | M6+       | Reserved packages                                  |

## Resource lifecycle (M1)

The FastAPI lifespan creates exactly one shared `AsyncEngine`,
`async_sessionmaker` and async Redis client per process, stores them on
`app.state`, and disposes/closes them on shutdown. `/ready` uses these
shared resources — no per-request engine creation. Startup validation
probes DB and Redis and logs the result without crashing the API.

## Celery layout (M1)

Queues per `09_AGENT_CATALOG_AND_ORCHESTRATION.md` §25:

```text
control        infrastructure tasks (default queue)
sports_io      provider IO, rate-limited
research_io    search provider IO
llm            expensive, low concurrency
evaluation     batch metrics work
notifications  Telegram pushes (M3+)
```

Redis `/0` is the broker, `/1` the result backend. JSON serialization,
`enable_utc=True`, beat timezone = `APP_TIMEZONE`. Route patterns for
future task modules are preconfigured; the only real task in M1 is
`control.ping`. See ADR-0006.

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
- `docs/adr/0006-m1-migration-scope-and-celery-queue-layout.md`
