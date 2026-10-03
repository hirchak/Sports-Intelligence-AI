# Local v1 Operations

LOCAL DEVELOPMENT ONLY. All commands address this repository's local Compose project.
Before mutations confirm a local Docker Unix-socket context and the intended COMPOSE_PROJECT_NAME/env.
Future server deployment needs separate explicit owner authorization; none of these instructions permits it.

## Start, stop, restart and health

`make bootstrap` performs the documented locked bootstrap/migrate/seed/start checks. `make up` builds/starts;
`make down` stops while preserving volumes. `docker compose restart sports-api sports-worker sports-beat`
restarts application processes. Do not use down -v, delete volumes or reset canonical state as routine recovery.

Check `/health` and `/ready` (LOCAL_DEVELOPMENT lists ports). In private topology use:

```bash
docker compose exec -T sports-api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=5).status)"
docker compose exec -T sports-worker celery -A sports_intelligence.workers.celery_app inspect ping --timeout=5
docker compose logs --since 10m sports-worker sports-beat
```

`control.ping` can be sent via `celery ... call control.ping` to verify the broker/consumer. It does not
prove sports/LLM connectivity. One Beat instance only. Worker defaults concurrency2/prefetch1;
queues are control/sports_io/research_io/llm/evaluation/notifications. Check DB job state, not only Redis.
Container logs rotate at 10MB ×3 per service; JSON app logs retain correlation/task/job/fixture/run IDs,
status, duration and safe provider failures. LLM usage/latency, quotas, requests and job attempts also live in DB.

## Failed/stalled jobs

```bash
docker compose exec -T sports-postgres psql -X -U sports -d sports_intel -c \
  'SELECT job_type,status,count(*) FROM jobs GROUP BY job_type,status ORDER BY job_type,status'
docker compose exec -T sports-postgres psql -X -U sports -d sports_intel -c \
  'SELECT job_id,attempt_number,status,error_class,started_at,finished_at FROM job_attempts ORDER BY started_at DESC LIMIT 20'
```

Adapt database/user to your env without printing passwords/URLs. Follow job/fixture/prediction/experiment
IDs into structured logs and persisted detail endpoints. HTTP correlation accepts bounded safe characters;
query strings, bodies and auth headers are never request-log fields. Migration logging preserves existing loggers.

FAILED known dispatch may be requeued through its existing safe API path where supported. PENDING missing
broker delivery needs inspection. For prediction/replay RUNNING with an unknown external-call outcome,
inspect attempts/provider metadata first; an explicit new rerun UUID preserves original truth. Never manually
set SUCCEEDED, fabricate output or blindly reset a possibly paid claim. No automatic outbox recovery exists.
M9 interrupted arm claims become NEEDS_INSPECTION; proposal approval does not execute or promote production.

## Incidents

- Quota/provider: read `/v1/system/status` and request/quota ledgers. Keep P0 reserves; pause optional
  research/challenger/experiment work first. Respect bounded 429/backoff. Do not increase budgets to hide failure.
- Redis: readiness becomes503. PostgreSQL forecasts remain readable; cached locks, broker messages and quota
  reservation counters may be lost. Restore Redis, inspect DB PENDING/RUNNING and uncertain paid calls before
  re-enabling live scheduling. Do not infer message redelivery from DB persistence alone.
- PostgreSQL: readiness becomes503; controls cannot persist canonical work. Stop scheduling/writers, restore
  DB availability, check migrations/evidence identities. Generic API500 has no debug traceback. Recover data
  via tested protected backup only under explicit restore authorization; never auto-recreate an existing DB.
- Telegram: API/workers remain independent. Check allowlist/token configuration locally, backend readiness,
  network error classes and duplicate polling conflicts. Restart only the intended bot instance; never print token.
- LLM: malformed/invalid probabilities/repair failure cannot create valid forecasts. Read attempts and actual
  model identity; fallback/budgets remain explicit. A timeout is not evidence that the provider did no paid work.

## Backup, rollback and secrets

Use BACKUP_RESTORE for native dumps/disposable restore checks. Take a protected backup before a controlled
future change. Rollback concept: stop writers, select independently accepted code/schema compatibility,
restore to a clean separate DB, verify hashes/counts, then switch only under an explicit approved process.
No destructive automatic downgrades. M10 is not accepted/tagged merely because implementation tests pass.

Rotation concept: provision a replacement credential outside Git/chat, update the protected local env/secret
mechanism, restart affected services, run a separately authorized bounded smoke, revoke old key, rescan logs/
history. This run does not rotate credentials or configure any remote schedule.

## Capacity and evidence

`scripts/runtime_acceptance.py` permits only disposable sports-m10-* local projects and loopback API.
It exercises queued restart, DB/Redis outages and twelve synthetic predictions, records Docker stats,
DB/Redis size, log bytes and batch duration. Snapshot CPU/RAM on Docker Desktop is local evidence only;
it cannot establish server sizing or multi-day unattended operation. See M10_ACCEPTANCE_REPORT.


## M10 physical transport accounting

Runtime sports/odds factories use one HTTP attempt per invocation; standalone adapters retain their
bounded retry capability. Failed runtime jobs retry through existing explicit/scanner CAS paths and
quota gates, not hidden adapter retries under one ledger row. Cold odds event lookup is logged separately
from paid odds fetch. Its observer is task-local (ContextVar), includes safe headers/status/error timing,
and avoids a phantom paid-call row if lookup fails. A successful event lookup does not reset the pending
paid reservation generation. Aborted lookups may retain conservative reservations until refresh; no
monetary charge is invented. QuotaManager algorithms/cache/provider normalization remain unchanged.

Optional weekly time is configured by IMPROVEMENT_SCHEDULE_DAY_OF_WEEK/HOUR/MINUTE; defaults remain
Monday09:00, disabled. Discovery hour/minute and weekly fields reject invalid calendar values.
