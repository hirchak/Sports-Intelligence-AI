# Review Handoff

Use this file when handing the repository to ChatGPT, Kimi, another engineer, or a fresh coding-agent session.

Update it before every milestone review.

---

# Review status

**Ready for review:** YES  
**Development phase:** LOCAL DEVELOPMENT ONLY  
**Milestone:** M1 + M1.1 fixes — awaiting final review  
**Review target branch:** `build/m1`  
**Review target commits:** `18c0a25` (DB/Redis lifecycle + migration),
`6b19704` (Celery), `93b3d3a` (CI/docs/state), `d0038dc` (handoff),
**`973c674` (M1.1 fixes)** — see Git section  
**CI status:** green on `build/m1` (unit, integration with isolated
Postgres/Redis services, compose validation)  
**Previous review:** M1 → PASS WITH FIXES; fixes implemented in M1.1  
**Previous accepted state:** `main` = `7000c32` (M0 accepted, tag `v0.1-m0`)

---

# What changed since the last review

M1.1 fixes (all items from the PASS WITH FIXES verdict):

1. **Isolated integration database.** Integration tests — including the
   destructive migration cycle (`downgrade base` + reapply) — never touch
   the dev database anymore:
   - dedicated `sports_intel_test` database, auto-created by
     `make test-integration` on the local Postgres;
   - `TEST_DATABASE_URL` always points at it; Redis test traffic uses db 15;
   - CI runs against its own ephemeral Postgres service container with
     `sports_intel_test`;
   - guard `tests/helpers.py::require_test_database` refuses any
     `TEST_DATABASE_URL` whose database name does not end with `_test`
     (loud `RuntimeError`, not a silent skip; unit-tested);
   - verified: `sports_intel` table snapshot identical before and after
     the integration suite.
2. **Exception-safe lifespan cleanup.** Cleanup wrapped in `try/finally`
   via `src/sports_intelligence/api/resources.py::close_resources`:
   - Redis `aclose()` and engine `dispose()` are guaranteed to run on any
     exit, including exceptions raised during the lifespan;
   - a failure of one cleanup does not block the other (both are attempted,
     each failure logged);
   - tests: unit tests for failure isolation + a test that raises inside
     the lifespan context and proves both resources were still closed.
3. **Docs**: `docs/LOCAL_DEVELOPMENT.md` documents the test-database
   isolation policy and the guard.

---

# What should the reviewer verify?

- integration tests (including the destructive migration cycle) can only
  run against a `_test` database; the dev DB is untouched;
- lifespan cleanup runs on exceptional exit and tolerates cleanup failures;
- migration 0001 applies/downgrades/reapplies on a fresh test database;
- Celery queues/routes match `09` §25; no football tasks leaked into M1;
- MOCK mode remains keyless;
- no scope creep into M2+ (no sports/odds/search/LLM/Telegram code);
- compose isolation (ports, volumes, project name).

---

## Commands claimed as passing

```bash
uv sync --frozen --dev
uv run pytest -q -m "not integration"        # 41 passed
make test-integration                        # 3 passed, isolated sports_intel_test DB
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

Negative check (guard): pointing `TEST_DATABASE_URL` at the dev database
makes integration tests fail loudly with `RuntimeError` — verified.

CI runs unit + integration (isolated service containers) + compose
validation on every push; all three jobs green on `build/m1`.

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
- `src/sports_intelligence/api/resources.py` (exception-safe cleanup)
- `src/sports_intelligence/api/readiness.py`
- `tests/helpers.py` (test-DB guard)
- `tests/integration/conftest.py` + `test_db_resources.py` (isolated services)
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
