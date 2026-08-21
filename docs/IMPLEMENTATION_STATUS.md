# Implementation Status

**Project:** Sports Intelligence AI  
**Development phase:** LOCAL DEVELOPMENT ONLY  
**Current milestone:** M3 — Telegram base UI / private control plane —
implemented, awaiting final review (M2 accepted via `v0.3-m2`)  
**Last updated:** 2026-08-21 (DeepSeek V4 Pro via OpenCode)  
**Last known good commit:** see section 11

---

# 1. Current objective

M2 (including M2.1–M2.4 fixes) passed independent final review
(verdict: **PASS — M2 ACCEPTED**), merged to `main` via PR #4, tagged
`v0.3-m2`.

M3 (Telegram base UI / private control plane) is implemented on
`build/m3` and awaiting independent review. Do not start M4 before
acceptance.

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
- **Raw evidence**: `raw_provider_payloads` (deduplicated content: payload
  hash + JSONB) plus `provider_observations` (per-retrieval events with
  fingerprint/retrieved_at, ADR-0009). No secrets stored.
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

## M2.1 — Fix milestone (independent review: PASS WITH FIXES)

All review items implemented:

- **retrieved_at semantics**: captured AFTER the final successful response
  (post-retry); regression test with retry/delay proves the timestamp is
  not the pre-request time.
- **Immutable evidence history** (ADR-0009): deduplicated content
  (`raw_provider_payloads`) + append-only `provider_observations` (one row
  per retrieval event with its own `retrieved_at`); replay can resolve the
  snapshot available at `as_of`. Migration 0003 includes a data migration
  for existing rows. Verified: repeat discovery appends an observation
  while content stays deduplicated.
- **Atomic provider identity**: PostgreSQL CTE arbiter for teams and
  fixtures — concurrent discoveries produce exactly one Team row and one
  mapping (concurrency test with `asyncio.gather`). Fixture refresh
  updates mutable metadata in place (same UUID; kickoff-change test).
- **League `enabled` sync**: `upsert_league_id` updates `enabled` on
  conflict (false→true→false test).
- **Per-provider enabled leagues**: discovery resolves enabled IDs for the
  CURRENT provider; zero enabled → empty summary with 0 external calls
  (test); `config/leagues.mock.yaml` carries explicit `mock:` +
  `api_football:` IDs.
- **Timezone**: "today" via `APP_TIMEZONE`; `?date=` converted to
  timezone-aware UTC boundaries for DB queries; API-Football request
  includes `timezone=APP_TIMEZONE`; canonical DB timestamps remain UTC;
  unit tests incl. DST transition (25h day) and local/UTC midnight.
- **Provider safety**: `mock` only when explicitly configured; unknown
  values fail fast with `ProviderConfigError` (typo test).
- **Job enqueue failure**: failed enqueue marks the job FAILED (502
  response); repeated POST re-enqueues the SAME job row (no duplicates)
  and resets it to PENDING (test covers both phases).
- **Missing data**: no invented "Unknown"/"UNKNOWN" — team/league names
  nullable in DTO/DB; missing fixture status (required identity) fails
  validation.
- **ADR-0008 reconciled**: composite indexes `(league_id, kickoff_at)` and
  `(status, kickoff_at)` actually created in migration 0003; redundant
  single-column indexes dropped.

## M2.2 — Short fix milestone (final M2.1 review: PASS WITH FIXES)

All review items implemented:

- **Canonical request fingerprint**: deterministic
  `provider:endpoint_family:sorted(params)` — includes date AND timezone
  (all response-affecting params); stored in `provider_observations`;
  tests: same date+tz → same fingerprint, different tz → different,
  order-independent, provider-distinct.
- **FAILED-job requeue race fixed**: conditional (CAS) status transition
  `transition_job_status_if(FAILED → PENDING)` — HTTP enqueue logic can
  never downgrade RUNNING/SUCCEEDED; regression test simulates a worker
  transition between `apply_async` and the HTTP-side update (job stays
  RUNNING). Full outbox remains M4.
- **ORM metadata synchronized with migration 0003**: composite
  `Index("ix_fixtures_league_kickoff")` and
  `Index("ix_fixtures_status_kickoff")` added to the ORM; stale
  single-column `index=True` on league/status removed (kickoff single
  index intentionally kept for date-only queries); schema drift verified
  via `alembic check` at head in integration tests/CI (no new upgrade
  operations).
- **Hardened atomic identity race**: arbiter resolution no longer uses
  `scalar_one()` without fallback — bounded safe resolution (winner row →
  use; empty → fresh SELECT mapping; bounded retry) with no orphan
  Team/Fixture possible; targeted synchronized-start concurrency test
  (6 participants, barrier): exactly 1 mapping, exactly 1 Team, all
  callers received the same UUID.
- **Worker initialization exception-safe**: engine created before
  provider/config init; any init failure now disposes the engine and
  closes the provider (independent cleanups), marks the job FAILED when
  the DB is available, and re-raises the original exception (tests:
  integration marks FAILED; unit proves dispose + re-raise with
  unreachable DB).

## M2.3 — Minimal fix (final M2.2 review: PASS WITH ONE REQUIRED FIX)

- **Idempotency key per `09` spec**: manual discovery job identity is now
  `discover:{provider}:{date}:v{league_config_version}:{timezone}` — the
  LeagueConfig `version` is the canonical mechanism (enabled-league list
  never appears in the key); timezone included because the provider
  request depends on it. Rule documented: any semantic change to
  `config/leagues.yaml` must bump `version`.
- Tests: duplicate POST with same identity → no new job/enqueue;
  config-version change → new job + enqueue; timezone change → distinct
  identity; FAILED-job retry keeps the same job UUID.
- Stale IMPLEMENTATION_STATUS strings synced (In-progress block, provider
  selected/verified, reviewer diff `main..build/m2`, raw-evidence
  description post-ADR-0009).

## M2.4 — Minimal safety fix (final M2.3 review: PASS WITH ONE SMALL SAFETY FIX)

- **Job identity now binds execution semantics**: the Celery discovery
  task receives `job_id`, `fixture_date`,
  `expected_league_config_version`, `discovery_timezone` (the values
  encoded in the idempotency identity at enqueue time). The worker loads
  the LeagueConfig and refuses to run when the loaded `version` differs
  from the expected one: deterministic
  `LeagueConfigVersionMismatchError`, zero provider requests, job marked
  FAILED. The worker may never execute a different semantic
  configuration than the one encoded in the job identity.
- **Timezone from the job, not mutable settings**:
  `FixtureDiscoveryService` receives `discovery_timezone` from the task
  payload; `settings.app_timezone` is no longer re-read at execution.
- Regression tests: enqueued v1 + worker sees v1 → executes and
  SUCCEEDS; config drifts to v2 before execution → 0 provider calls +
  job FAILED; a job with `Europe/Warsaw` uses Warsaw even when current
  settings say `Europe/London`; existing MOCK discovery/idempotency
  tests stay green.
- No migration; no live smoke (quota preserved).

## M3 — Telegram base UI / private control plane (branch `build/m3`)

- **Thin UI over the backend**: aiogram 3 bot (`sports_intelligence.bot`
  package) talks to the FastAPI control plane exclusively through a
  typed `BackendClient` (health/ready, fixtures list, fixture detail,
  discovery enqueue). Handlers never touch provider adapters, DB,
  LLM or raw response dictionaries; all backend/network failures are
  normalized into bot-safe errors (no URLs, bodies, stack traces or
  secrets ever reach Telegram).
- **Private access control**: central `AllowlistMiddleware` registered
  for both messages and callback queries using
  `TELEGRAM_BOT_TOKEN` + `TELEGRAM_ALLOWED_USER_IDS`. Unknown users get
  a minimal "Доступ запрещён." message (or a silent callback answer);
  handlers never duplicate the check. Empty allowlist denies everyone.
- **Russian UI, single language**: all Telegram-facing text lives in
  `bot/strings.py`; commands and callbacks render the same Russian
  strings; bug-free, deterministic text (no f-string concatenation at
  call sites).
- **Button-based navigation**: every screen reachable from the main
  menu `Сегодня / Найти / Здоровье / Помощь`; every screen has a single
  «← Назад» button returning to the main menu; the find menu offers
  yesterday / today / tomorrow as quick picks alongside the
  `/fixtures ГГГГ-ММ-ДД` hint for arbitrary dates. Commands remain as a
  power-user fallback (`/start /help /dashboard /today /fixtures
  [date] /match <uuid> /health /discover [date]`).
- **Inline callbacks**: short stable payloads (`fx:<uuid>`,
  `pg:<date>:<page>`, `rf:<date>`, `disc`, `health`, `menu:*`) — no
  secrets, no JSON, under Telegram's 64-byte limit; fixture view,
  pagination, refresh, discover, health, main menu. Malformed/
  tampered payloads are answered harmlessly; repeated taps rely on
  backend idempotency (no second idempotency scheme inside Telegram).
- **Rendering**: /today grouped by league ordered by kickoff; kickoff
  shown in `APP_TIMEZONE` (DB stays UTC); Russian month abbreviations
  (янв., фев., …, авг., …); missing team names rendered as "—"
  (stored data never mutated); pagination (8 per page, Prev/Next +
  Refresh); HTML escaping for all backend-provided strings.
- **Transport separated from handlers**: `TelegramTransport` protocol
  (send_text / edit_text / answer_callback) with an aiogram
  implementation and an in-memory fake — 72 deterministic bot unit
  tests require no token and no network.
- **Docker Compose `telegram` profile**: isolated `sports-telegram`
  service (no exposed ports), internal networking to `sports-api`,
  bot env via `BOT_BACKEND_BASE_URL`; the ordinary api/postgres/redis/
  worker/beat stack starts without any Telegram credentials.
- **Live Telegram smoke** (real token + allowlisted user, bounded):
  /start /today /health /discover + inline fixture tap (initial
  English commands) verified through bot/worker logs; Russian
  main-menu + button navigation verified live (screenshot by user).
  MOCK-mode discovery round-trip verified idempotent (0 created /
  3 updated; duplicate POST → `already_queued`). Note: one accidental
  live API-Football call was consumed before the smoke was pinned to
  MOCK (documented in the worklog; quota-safe default restored
  afterwards).

---

# 3. In progress

None. M3 is implemented on `build/m3`; the branch awaits independent
review.

---

# 4. Acceptance tests passed (actually run)

- `uv run pytest -q -m "not integration"` → **151 passed** (72 new
  Telegram bot tests: access, formatting, backend client, handlers,
  callbacks, menu navigation; no token required)
- `make test-integration` (isolated `sports_intel_test` DB) → **26 passed**
  (incl. M2.4 identity-binding regressions, targeted concurrency,
  enqueue-race regression, fingerprint, schema-drift `alembic check`,
  worker init failure, migration cycle)
- `uv run ruff check .` / `ruff format --check .` → clean
- `uv run mypy src` → **no issues in 62 source files** (strict)
- `docker compose config -q` and `docker compose --profile telegram
  config -q` (+dev) → OK
- Docker live smoke: full stack incl. `sports-telegram` (telegram
  profile); bot long-polls; /start /today /health /discover + inline
  fixture tap verified through typed backend client; MOCK discovery
  job SUCCEEDED via Celery (4-arg identity payload), duplicate POST →
  `already_queued` (idempotent)
- Secret scan: token/user IDs only in local `.env` (gitignored)

---

# 5. External integrations

## Verified live

- **API-Football fixture discovery** — bounded live smoke (M2: 2 requests,
  M2.1: 1 request): real response, normalization, persistence, repeat
  idempotency, evidence history, rate-limit headers, `timezone` parameter.
  Full production use not yet exercised (single date, single league).

## Mocked / not yet verified

- Odds provider (interface only, M4)
- Search provider (interface only, M5)
- Runtime LLM providers (interface only, M7)

## Verified live (M3)

- **Telegram bot** — bounded local smoke with real token and allowlisted
  user: /start, /today, /health, /discover (job enqueued through the
  backend) and an inline fixture tap all served correctly; MOCK-mode
  discovery round-trip verified idempotent through the full stack.

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
- M2 schema scope (six tables, upsert strategy) → ADR-0008 (amended in
  M2.1: atomic CTE arbiter, composite indexes, enabled sync).
- Immutable provider observation history → ADR-0009.

---

# 8. Database/migrations

Status:
- migrations `0001` (jobs), `0002` (discovery), `0003` (evidence history +
  composite indexes + nullable team name) applied locally and verified in
  CI on a fresh DB (apply → repeat → downgrade → reapply).

Latest migration:
- `0003_provider_evidence_history_and_indexes`

Local DB preservation required:
- no, until meaningful live test data exists

---

# 9. API/quota status

Provider:
- API-Football — selected (ADR-0007); verified via bounded live smokes
  (M2/M2.1). Sportmonks remains a documented migration path.

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
- `build/m3` (M3 work); `main` = `c737f80` (M2 accepted, tag `v0.3-m2`)

Commit:
- M3 commits recorded in `docs/REVIEW_HANDOFF.md` after commit

Working tree:
- clean after the M3 commits

---

# 12. Next action

1. Independent review of M3 (see `docs/REVIEW_HANDOFF.md`).
2. After acceptance: merge `build/m3` into `main`, tag `v0.4-m3`.
3. Only then start M4 with explicit user approval.

---

# 13. Reviewer notes

**Final review verdict (2026-08-21): M2 PASS — M2 ACCEPTED.**
Safe to begin M3: YES.

A reviewer should start by reading:

1. `AGENTS.md`
2. this file
3. `docs/CURRENT_TASK.md`
4. `docs/REVIEW_HANDOFF.md`
5. relevant specification
6. Git diff `main..build/m2`
