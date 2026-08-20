# Review Handoff

Use this file when handing the repository to ChatGPT, Kimi, another engineer, or a fresh coding-agent session.

Update it before every milestone review.

---

# Review status

**Ready for review:** YES  
**Development phase:** LOCAL DEVELOPMENT ONLY  
**Milestone:** M1 — Core Infrastructure, awaiting review  
**Review target branch:** `build/m1`  
**Review target commits:** `18c0a25` (DB/Redis lifecycle + migration),
`6b19704` (Celery), `93b3d3a` (CI/docs/state) — see Git section  
**CI status:** green on `build/m1` (unit, integration with Postgres/Redis
services, compose validation)  
**Previous accepted state:** `main` = `7000c32` (M0 accepted, tag `v0.1-m0`)

---

# What changed

M1 turned the M0 skeleton into core infrastructure:

1. **DB**: shared SQLAlchemy 2 `AsyncEngine` + `async_sessionmaker` created
   in the FastAPI lifespan, stored on `app.state`; `get_session` dependency;
   engine disposed on shutdown. `/ready` no longer creates a per-request
   engine (M0.1 technical debt resolved).
2. **Redis**: shared async client via lifespan; used by `/ready`; closed on
   shutdown (verified by test).
3. **Lifespan**: resource creation, startup connectivity validation
   (log-only, API stays up), clean shutdown; no global mutable state —
   `create_app(settings)` injects everything.
4. **Celery**: app factory, Redis broker `/0` + result backend `/1`, JSON,
   UTC; queues `control, sports_io, research_io, llm, evaluation,
   notifications`; route patterns; `control.ping` task; empty beat schedule.
5. **Compose**: api + postgres + redis + worker + beat (loopback ports,
   named volumes, `sports-intel` project).
6. **Migration 0001**: `jobs` + `job_attempts` only — scope proposal and
   rationale in ADR-0006.
7. **CI**: new integration job with Postgres/Redis service containers;
   migration cycle tested on a fresh database.
8. **Docs/state** updated; ADR-0006 added.

---

# What should the reviewer verify?

- lifespan resources are created once and cleaned up; `/ready` uses shared
  resources;
- migration 0001 applies/downgrades/reapplies on a fresh database;
- Celery queues/routes match `09` §25; no football tasks leaked into M1;
- integration tests exercise real services, unit tests stay service-free;
- MOCK mode remains keyless;
- no scope creep into M2+ (no sports/odds/search/LLM/Telegram code);
- compose isolation (ports, volumes, project name).

---

# Commands claimed as passing

```bash
uv sync --frozen --dev
uv run pytest -q -m "not integration"        # 34 passed
uv run pytest -q -m integration              # 3 passed (needs TEST_DATABASE_URL/TEST_REDIS_URL)
uv run ruff check .
uv run ruff format --check .
uv run mypy src
docker compose config -q
docker compose up -d --build                 # api/postgres/redis/worker/beat
curl http://127.0.0.1:8000/health            # 200
curl http://127.0.0.1:8000/ready             # 200
docker compose run --rm sports-api alembic upgrade head
docker compose exec sports-worker celery -A sports_intelligence.workers.celery_app call control.ping --args='["smoke"]'
```

CI runs unit + integration (service containers) + compose validation on
every push; all three jobs green on `build/m1`.

Reviewer must not assume tests passed based on status text alone.

---

# Known limitations

- No orchestrator/job scheduling logic yet — queues and jobs schema exist,
  but pipelines arrive in M2+.
- `control.ping` is the only task; `beat_schedule` is empty.
- Celery is untyped upstream: mypy overrides treat celery/kombu as untyped;
  the ping task carries `type: ignore[untyped-decorator]`.
- starlette pinned `<1.0` (httpx TestClient deprecation in 1.x).
- Docker Desktop (macOS) multi-service bake bug — per-service build
  workaround documented in `docs/LOCAL_DEVELOPMENT.md`.
- Scheduled debt: M2 must replace `dict[str, Any]` provider interfaces with
  normalized DTO/Pydantic schemas (recorded in IMPLEMENTATION_STATUS).

---

# Files of highest relevance

- `src/sports_intelligence/api/app.py` (lifespan)
- `src/sports_intelligence/api/readiness.py`
- `src/sports_intelligence/db/models/jobs.py`
- `src/sports_intelligence/db/migrations/versions/0001_*.py`
- `src/sports_intelligence/workers/celery_app.py`
- `docs/adr/0006-m1-migration-scope-and-celery-queue-layout.md`
- `compose.yaml`, `.github/workflows/ci.yml`
- `docs/IMPLEMENTATION_STATUS.md`
- Git diff `main..build/m1`

---

# Questions for reviewer

1. Is the lifespan/resource design safe under concurrent requests and
   restarts?
2. Is the migration scope (jobs/job_attempts only) correct, or did something
   belong in M1 that is missing?
3. Are the queue layout and task routing ready for M2 without rework?
4. Do tests prove real behavior (including failure paths) rather than only
   happy paths?
5. Is the next milestone safe to start?

---

# Reviewer output expected

```text
VERDICT: PASS / PASS WITH FIXES / FAIL

P0 critical
P1 high
P2 medium
P3 low

Tests independently run:
...

Required fixes before next milestone:
...

Safe to begin next milestone:
YES / NO
```
