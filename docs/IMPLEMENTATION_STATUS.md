# Implementation Status

**Project:** Sports Intelligence AI  
**Development phase:** LOCAL DEVELOPMENT ONLY  
**Current milestone:** M2 — implemented, awaiting review  
**Last updated:** 2026-08-20 (DeepSeek V4 Pro via OpenCode)  
**Last known good commit:** see section 11

---

# 1. Current objective

M1 implemented on branch `build/m1`. Awaiting independent review before
merging to `main` and starting M2.

No Hetzner deployment is authorized.

No Hermes access/dependency is authorized.

---

# 2. Completed

## M0 + M0.1 (accepted: independent review verdict PASS)

- Repository scaffold, FastAPI skeleton, config validation, JSON logging,
  Docker stack, Alembic scaffold, CI, docs, ADRs 0001–0005.
- Finalized in `main` via PR #2 (`7000c32`); tag `v0.1-m0` on `8d28138`.
- Repository renamed to `hirchak/Sports-Intelligence-AI`; URLs updated.

## M1 — Core Infrastructure (branch `build/m1`)

- **DB infrastructure**: shared SQLAlchemy 2 `AsyncEngine` +
  `async_sessionmaker` created in the FastAPI lifespan and stored on
  `app.state`; FastAPI session dependency (`get_session`); engine disposed
  on shutdown. `/ready` uses the shared engine (M0.1 technical debt resolved).
- **Redis infrastructure**: shared async Redis client via lifespan;
  `/ready` uses it; closed on shutdown (verified by test).
- **FastAPI lifespan**: creates DB/Redis resources, startup connectivity
  validation (log-only, API stays up when dependencies are down),
  clean shutdown; no global mutable state — everything injected via
  `create_app(settings)`.
- **Celery**: app factory + module-level app; Redis broker `/0` and result
  backend `/1`; JSON serialization, `enable_utc=True`, beat timezone
  `Europe/Warsaw`; queues `control, sports_io, research_io, llm, evaluation,
  notifications`; route patterns for future task modules; one real task
  (`control.ping`); empty beat schedule. No football tasks.
- **Docker Compose**: api + postgres + redis + worker + beat
  (`sports-intel` project, loopback ports, named volumes).
- **Alembic**: first real migration `0001` — `jobs` + `job_attempts`
  (Operations group only; scope proposal: ADR-0006). Verified apply →
  repeat → downgrade → reapply on a fresh database in tests and CI.
- **Tests**: 37 total (34 unit + 3 integration). Integration tests run
  against real Postgres/Redis service containers in CI.
- **CI**: unit job + new integration job (postgres/redis service
  containers) + compose validation; no external sports/LLM APIs.
- MOCK mode remains fully keyless.

## M1.1 — Fix milestone (independent review: PASS WITH FIXES)

Review fixes implemented:

- **Isolated integration database.** Integration tests (including the
  destructive migration cycle) run only against a dedicated
  `sports_intel_test` database: `make test-integration` auto-creates it,
  `TEST_DATABASE_URL` always points at it, CI uses its own ephemeral
  Postgres service database, Redis test traffic uses db `15`. A guard
  (`tests/helpers.py::require_test_database`) refuses any URL whose
  database name does not end with `_test` — loud failure, not a skip.
  Verified: dev DB `sports_intel` table list identical before/after the
  integration suite.
- **Exception-safe lifespan cleanup.** Cleanup moved to `try/finally`
  (`api/resources.py::close_resources`): on any exit (including exceptions)
  both Redis `aclose()` and engine `dispose()` are attempted; a failure of
  one cleanup does not block the other. Tests: exceptional-exit simulation
  proves both resources are closed; unit tests prove failure isolation.

## M2 — Sports Provider + Fixture Discovery (branch `build/m2`)

- **Provider choice**: API-Football as first real `SportsDataProvider`
  (ADR-0007: reason, boundaries, alternatives, Sportmonks migration path).
- **Typed DTOs** (M1 tech debt closed for the discovery path):
  `ProviderLeague`, `ProviderSeason`, `ProviderTeam`, `ProviderFixture`,
  `FixtureDiscoveryResult`, `ProviderResponseMetadata` — no
  `dict[str, Any]` in the discovery flow; missing fields stay explicit
  `None`; kickoff normalized to UTC.
- **API-Football adapter**: async httpx, configurable base URL, env-only
  API key, timeout, bounded retry (3 attempts, jitter; auth non-retryable),
  normalized `ProviderError` hierarchy, rate-limit metadata, safe logging
  (key never logged — covered by test), injected transport for tests,
  one shared client per provider instance.
- **Batch-first discovery**: one date-level request fetches all fixtures
  of the day; enabled leagues filtered locally; `ProviderCapabilities`;
  N+1 guard test proves a single provider call for N fixtures.
- **Raw evidence**: `raw_provider_payloads` persisted with provider,
  endpoint family, request fingerprint, payload hash (dedup), JSONB
  payload, retrieved_at. No secrets stored.
- **Migration 0002** (ADR-0008): `leagues`, `seasons`, `teams`,
  `fixtures`, `provider_entity_ids`, `raw_provider_payloads` — UUID PKs,
  UTC, unique constraints + indexes; PostgreSQL upserts
  (`ON CONFLICT DO UPDATE/NOTHING`); provider IDs never primary keys.
  No odds/prediction/research tables.
- **Discovery service**: deterministic; re-runs duplicate nothing
  (integration-verified); stores provider identity on mappings.
- **League configuration**: YAML (`config/leagues.yaml`, all leagues
  disabled by default; `config/leagues.mock.yaml` demo with one enabled
  league), documented seed path (`make seed`).
- **API**: `GET /v1/fixtures` (date/league filters), `GET /v1/fixtures/{id}`
  (404 on missing), `POST /v1/jobs/discover` — creates a `jobs` row with
  idempotency key and enqueues the Celery task; no long-running provider
  call inside the handler; duplicate POSTs reuse the job.
- **Celery**: `sports.discover_fixtures` on `sports_io`, updates job
  status RUNNING→SUCCEEDED/FAILED; no other tasks; no automatic schedule
  (zero quota spend unless explicitly triggered).
- **Mock mode**: `MockSportsDataProvider` from recorded, sanitized
  API-Football-shaped responses; keyless; used by CI and tests.
- **Contract tests**: recorded response → normalized DTO; null handling;
  UTC conversion; home/away identity; malformed payload; timeout/429/500/
  auth; API key leak test; external-ID mapping; idempotency; league
  filtering; N+1 guard.
- **Live smoke (bounded, 2 API calls)**: real API-Football key present in
  local `.env` → discovery of 2026-08-21 fetched 383 fixtures in ONE
  request, filtered to 1 enabled league fixture (Arsenal vs Coventry),
  persisted raw payload (401 KB, hash), teams/season/fixture created;
  repeat run: 0 created / 1 updated / payload dedup — idempotent.
  Rate limiting respected; key absent from all logs.

---

# 3. In progress

None. M1 waits for review.

---

# 4. Acceptance tests passed (actually run)

- `uv run pytest -q -m "not integration"` → **63 passed**
- `make test-integration` (isolated `sports_intel_test` DB) → **10 passed**
  (discovery persistence, idempotency, league filtering, API filters,
  job idempotency, N+1 guard, migration cycle, readiness)
- `uv run ruff check .` / `ruff format --check .` → clean
- `uv run mypy src` → **no issues in 50 source files** (strict)
- `docker compose config -q` (+dev) → OK
- Docker smoke: 5 services up; `/health`/`/ready` 200; mock AND live
  discovery through the real stack (see section 5); `GET /v1/fixtures`
  returns normalized rows; job SUCCEEDED; dev/test DB isolation intact
- Secret scan: API key present only in local `.env` (gitignored); absent
  from logs, tests and Git

---

# 5. External integrations

## Verified live

- **API-Football fixture discovery** — bounded live smoke (2 requests):
  real response, normalization, persistence, repeat idempotency, raw
  payload dedup, rate-limit headers observed. Full production use not yet
  exercised (single date, single league).

## Mocked / not yet verified

- Odds provider (interface only, M4)
- Search provider (interface only, M5)
- Runtime LLM providers (interface only, M7)
- Telegram bot (config fields only, M3)

---

# 6. Known issues / blockers

- Docker Desktop (macOS) multi-service bake build bug — per-service build
  workaround documented in `docs/LOCAL_DEVELOPMENT.md`.
- Starlette pinned `<1.0` (httpx TestClient deprecation in 1.x).
- Celery untyped upstream → `type: ignore[untyped-decorator]` on tasks.
- Live API-Football runs happen only via explicit job POSTs (no schedule),
  so quota spend is fully manual in M2 — intentional.

## Scheduled technical debt

- ~~M2: normalized provider DTOs instead of `dict[str, Any]`~~ → done for
  the discovery path (odds/search/LLM protocols get typed at their
  milestones).
- **M4:** QuotaManager + request ledger (adapter already captures
  rate-limit headers).
- **M4:** job_attempts rows for worker attempts (M2 updates only
  `jobs.status`).

---

# 7. Architecture/spec deviations

- M0 scope included API/Postgres/Redis/logging skeletons per explicit user
  instruction → ADR-0005.
- Spec `.md` files kept in repository root → ADR-0002.
- Non-standard local host ports 5433/6380 → ADR-0003.
- Validation policy (`extra="ignore"`, `env_ignore_empty`, `NoDecode`) →
  ADR-0004.
- M1 migration scope limited to `jobs`/`job_attempts` → ADR-0006.
- API-Football chosen as first provider → ADR-0007.
- M2 schema scope (six tables, upsert strategy) → ADR-0008.
- Enabled-league filter matches provider league IDs regardless of the
  provider key in `provider_ids` (mock emulates api_football IDs) —
  documented assumption, no ADR needed.

---

# 8. Database/migrations

Status:
- migrations `0001` (jobs) + `0002` (discovery) applied locally and
  verified in CI on a fresh DB (apply → repeat → downgrade → reapply).

Latest migration:
- `0002_create_discovery_tables`

Local DB preservation required:
- no, until meaningful live test data exists

---

# 9. API/quota status

Provider:
- not selected/verified (open decision, `17_OPEN_QUESTIONS_AND_CONFIG_DEFAULTS.md`)

Quota telemetry:
- not implemented (M4)

Cache:
- not implemented (M2+)

---

# 10. Current model/runtime configuration

Development lead:
- DeepSeek V4 Pro (this session)

Runtime prediction model:
- not selected empirically

LLM provider routing:
- not implemented (M7)

---

# 11. Current Git state

Branch:
- `build/m2` (M2 work); `main` = `25dda83` (M1 accepted, tag `v0.2-m1`)

Commit:
- M2 commits recorded in `docs/REVIEW_HANDOFF.md` after commit

Working tree:
- clean before M2 commits

---

# 12. Next action

1. Independent review of M2 (see `docs/REVIEW_HANDOFF.md`).
2. After acceptance: merge `build/m2` into `main`.
3. Only then start M3 with explicit user approval.

---

# 13. Reviewer notes

A reviewer should start by reading:

1. `AGENTS.md`
2. this file
3. `docs/CURRENT_TASK.md`
4. `docs/REVIEW_HANDOFF.md`
5. relevant specification
6. Git diff `main..build/m1`
