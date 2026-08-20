# Current Task

**Status:** IN PROGRESS  
**Milestone:** M0  
**Owner/agent:** DeepSeek V4 Pro (lead engineer, OpenCode)  
**Started at:** 2026-08-20  
**Last updated:** 2026-08-20

---

# Task

Initialize the repository and implement M0 only.

---

# Required reading

- `AGENTS.md`
- `00_MASTER_TECHNICAL_SPEC.md`
- `02_DEEPSEEK_V4_PRO_LEAD_ENGINEER.md`
- `19_PROMPT_TO_START_DEEPSEEK.md`
- `docs/IMPLEMENTATION_STATUS.md`
- All architecture-relevant detailed specs (`07`–`18`) — read on 2026-08-20.

---

# Spec-contradiction review (2026-08-20)

1. **M0 scope overlap.** Master spec §36 puts FastAPI/Postgres/Redis/logging in M1,
   but the user instruction and `19_PROMPT_TO_START_DEEPSEEK.md` require their
   *skeletons* already in M0. Resolution: M0 delivers only the skeleton level
   (config, containers, `/health`, `/ready`, logging foundation, Alembic scaffold
   with zero revisions). Celery, aiogram, real models/migrations remain M1.
   → ADR-0005.
2. **Spec file location.** `README_EXECUTION_ORDER.md` allows spec `.md` files in
   the repo root or a `spec/` dir. Specs are kept in the root so all existing
   cross-references (`AGENTS.md`, `docs/*`) stay valid. → ADR-0002.
3. **Provider/odds/search/LLM choices are open** (`17`). M0 does not depend on
   them: mock mode requires no keys; real adapters are out of scope. No decision
   forced.
4. No other contradictions found. Where ambiguous, the safest reversible option
   was chosen and recorded in ADRs/assumptions.

---

# M0 implementation plan

## Phase 1 — repository bootstrap

1. `git init`, remote `git@github.com:hirchak/-.git`.
2. Commit the existing specification pack to `main` (initial commit).
3. Create branch `build/m0` for milestone work (per `16_GITHUB_AI_DEVELOPMENT_CONTROL.md`).

## Phase 2 — Python scaffold (TDD where behavior exists)

- `pyproject.toml` (Python 3.12, hatchling, src layout, package `sports_intelligence`).
- Dependencies: fastapi, uvicorn, pydantic-settings, sqlalchemy[asyncio], asyncpg,
  alembic, redis, httpx. Dev: pytest, pytest-asyncio, ruff, mypy.
  Celery/aiogram/tenacity deferred to their milestones (M1/M3) to avoid unused deps.
- Packages: `core/` (config, logging, time, ids), `api/` (app, routes/health),
  `db/` (session, migrations/), `providers/` (Protocol interfaces only),
  `schemas/`, plus empty packages `bot/ domain/ features/ pipelines/ ranking/
  research/ workers/` for the master-structure layout.
- Config validation: `APP_ENV` in `mock|sandbox|live_local`; in non-mock modes
  configured providers require their API key; comma-separated Telegram user IDs.
- Logging: structured JSON formatter + context fields (correlation/job/fixture/run IDs).
- FastAPI skeleton: `GET /health` (always 200), `GET /ready` (DB SELECT 1 + Redis
  ping; 503 when a dependency is down).
- Mock mode: startup works with zero external keys when `APP_ENV=mock`.

## Phase 3 — infrastructure

- `Dockerfile` (python:3.12-slim, uv, non-root user).
- `compose.yaml` (project `sports-intel`): postgres 16, redis 7, api;
  named volumes `sports_intel_pgdata`/`sports_intel_redisdata`; ports bound to
  127.0.0.1 only: 5433/6380/8000. `compose.dev.yaml` with bind-mount override.
- `.env.example`, `.gitignore`, `.dockerignore`, `Makefile` (dev/test/lint/
  format/typecheck/migrate/lock/check), `opencode.json.example`.
- Alembic scaffold: `alembic.ini`, `db/migrations/env.py` (async engine from
  settings), `script.py.mako`, empty `versions/`. No revisions in M0.
- CI: `.github/workflows/ci.yml` — uv sync frozen, ruff check + format check,
  mypy (src), pytest, `docker compose config -q`.

## Phase 4 — docs

- `README.md`, `docs/ARCHITECTURE.md`, `docs/LOCAL_DEVELOPMENT.md`,
  `docs/DATA_MODEL.md`, `docs/PIPELINES.md`, `docs/TELEGRAM.md`,
  `docs/DEPLOYMENT.md`, `docs/SECURITY.md`, `docs/adr/0001..0005`.

## Phase 5 — verification and handoff

- Run: pytest, `ruff check`, `ruff format --check`, `mypy src`.
- Docker: `docker compose config -q`, `up -d postgres redis api`, verify
  `/health`=200 and `/ready`=200, `alembic upgrade head` + `alembic current`.
- Update `IMPLEMENTATION_STATUS.md`, this file, `AI_WORKLOG.md`, `REVIEW_HANDOFF.md`.
- Secret scan, `git diff` review, commit `M0: scaffold repository and local
  Docker stack` on `build/m0`, tag `v0.1-m0`, push, verify CI.

---

# Scope

Expected M0 scope:

- repository scaffold;
- Python project configuration;
- dependency lock;
- local Docker Compose skeleton;
- FastAPI skeleton;
- Postgres/Redis definitions;
- configuration validation;
- logging foundation;
- test structure;
- CI skeleton;
- documentation structure;
- `.env.example`;
- mock-mode design;
- Git hygiene.

---

# Explicitly out of scope

- Hetzner deployment;
- SSH/server access;
- Hermes integration;
- complete sports API implementation;
- complete Telegram UX;
- real production prediction;
- automatic self-improvement;
- Celery/aiogram (M1/M3);
- database schema models and first migration (M1).

---

# Acceptance criteria (must be verified before completion)

1. `uv sync --frozen` succeeds from a clean checkout; `uv.lock` committed.
2. `pytest` passes; `ruff check .` passes; `ruff format --check .` passes;
   `mypy src` passes.
3. `docker compose config -q` passes without `.env` present (defaults via interpolation).
4. `docker compose up -d postgres redis api` starts; `GET /health` → 200;
   `GET /ready` → 200 with Postgres+Redis up.
5. `alembic upgrade head` and `alembic current` work against the local compose DB.
6. `APP_ENV=mock` requires no external API keys; non-mock modes enforce
   key validation (unit-tested).
7. Structured JSON logs are emitted (unit-tested).
8. No secrets in Git; `.env` ignored; `.env.example` contains only placeholders.
9. Spec pack + M0 implementation committed on `build/m0` with meaningful message;
   CI workflow exists and runs.

---

# Work notes

- 2026-08-20: All specs read; contradictions reviewed; plan defined; starting Phase 1.

---

# Completion

When complete:

- set Status = COMPLETE;
- record commit;
- update `docs/IMPLEMENTATION_STATUS.md`;
- append worklog;
- prepare `docs/REVIEW_HANDOFF.md`;
- stop before M1.
