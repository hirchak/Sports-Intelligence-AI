# Architecture

M0–M9 independently accepted; M10 adds local operational readiness. LOCAL DEVELOPMENT ONLY.

```text
Telegram UI → private FastAPI/control → deterministic Celery/Beat planner
  → provider adapters/collectors → PostgreSQL immutable observations/snapshots
  → deterministic quality/features → immutable MatchContext
  → configured LLM → deterministic validation/ranking → stored forecast/UI
Results → versioned truth → deterministic settlement → frozen evaluation
Frozen contexts → isolated experiments/replay → comparison → qualitative proposals → human action
```

Telegram never runs forecasting/business logic. Workers receive identifiers, read frozen state and audit
jobs/attempts. PostgreSQL is canonical; Redis owns transient broker/result/cache/locks and quota reservations.
API resources have a shared exception-safe lifecycle. `/health` is process liveness; `/ready` checks DB/Redis.
The API remains an internal private control plane; human operator access is via trusted loopback/Docker
network or Telegram allowlist, not a public multi-user identity service.

## Components

| Component | Implemented behavior |
|---|---|
| API/bot | Typed bounded commands/read models, queued expensive work, allowlisted Russian UI |
| Sports/odds/search adapters | Env-only keys, safe errors, normalization, physical request ledger, batching where supported |
| Collectors | Snapshot freshness before fetch, shared league/team identities, Redis coalescing, quotas/reserves |
| Quality/features/context | Missing differs from zero; point-in-time source selection, exact immutable context/hash |
| Prediction/ranking | Frozen prompt/model/config/policy, PRIMARY/CHALLENGER, odds projections, bounded repair/retry/fallback |
| Settlement/evaluation | regulation_v1 result versions, original captured probability/price truth, metrics_v1 and explicit sample sizes |
| Replay/improvement | Frozen historical population, isolated M9 tables, paired/full metrics, compatible human experiment authorization |
| Operations | Local bootstrap/restore/recovery, JSON redacted correlation/task logs, rotated container logs, private production example |

Queues: control, sports_io, research_io, llm, evaluation, notifications. Worker concurrency defaults two,
prefetch one; broker connection/publish attempts are bounded. LLM calls have separate persisted budgets.
No scheduler uses an LLM. Default schedules/live experiment/analyst gates stay disabled.

## Evidence authority

Provider content hashes deduplicate raw bodies; observation events retain retrieval time. UTC persists;
APP_TIMEZONE controls display/discovery days. Frozen source and feature/quality/prompt/model/policy identities
allow exact reconstruction. Current reference metadata, later lineups/prices/results cannot enter replay.
WITHOUT_ODDS also masks research text; it is not a pure causal odds-only experiment. Missing historical
contexts fail NOT_REPLAYABLE, never backfilled from current APIs. M9's population is captured contexts,
not an all-fixture census. Proposals do not mutate code, prompts, routes, weights or production automatically.

## Topology and recovery

Project-scoped Compose containers, network, Postgres/Redis volumes and env. Development ports are
loopback only. `compose.production-example.yaml` removes all published ports, explicitly runs production
API command and disables debug/docs. No external network/volume/database dependency is declared.
Application images use uid10001; Postgres/Redis use standard upstream image entrypoints.

Restarting services preserves Postgres truth. Redis loss may lose broker messages, locks and reservation
counters. A possibly paid RUNNING claim must be inspected, never blindly reclaimed. Manual rerun is explicit
and preserves old records. This MVP intentionally does not add an outbox/distributed recovery platform.
See OPERATIONS and PRODUCTION_READINESS for limits and evidence; unattended multi-day operation is unproven.

ADRs 0001–0012 document stack, topology, modes, schema scope, provider/evidence authority, forecasting,
result metrics and frozen proposal-only replay. M10 changes no forecasting architecture or schema history.
