# Implementation Status

**Project:** Sports Intelligence AI
**Development phase:** LOCAL DEVELOPMENT ONLY
**Current milestone:** M7.1 — Canonical odds contract acceptance fix (PASS / ACCEPTANCE VERIFIED; independent review pending)
**Last updated:** 2026-10-01 (Codex)
**Last known good commit:** 11b6e782ab7256607992b70cc0d0dee4ebe92a3a (tag v0.7-m6, PR #8 merged into main)

---

# 1. Current objective

Milestone review verdicts:
- M4 → **PASS / ACCEPTED** (HEAD `0d0cd4a631c067a29c21ce584e806a47c534dc82`, merged in PR #6 `2e4683a`, tagged `v0.5-m4`)
- M5 / M5.3 → **PASS / ACCEPTED** (HEAD `b38229b0874e9ab992ae25ea2a63e1e6109f8ca7`, merged in PR #7 `fb256ecaf2ca1a97c64f1dba8d491cff6b935c91`, tagged `v0.6-m5`)
- M6 → **FAIL** (reviewed HEAD `fff8df75c520696f6c25a14e19ded7b6711e7688`)
- M6.1 → **FAIL** (reviewed HEAD `08d253fe90883f11456b402563f4065fc4b00072`)
- M6.2 → **FAIL** (reviewed HEAD `a307096b131b9b59fe01a799a299a26b167477d0`)
- M6.3 → **FAIL** (reviewed HEAD `2b2dfaa30e84e9cf3a4c509093bf031f722bc6ec`, review findings: mutable league metadata dependency in historical replay, non-deterministic provider mapping order, Pydantic immutability claim discrepancy, Celery task refusal traceback)
- M6.4 → **FAIL** (reviewed HEAD `0621aa576aacd21860bd6695a698f3d85082231a`, review findings: false historical backfill in migration 0011 populating pre-existing snapshots from mutable leagues table at migration time; fallback in select_evidence to mutable League attributes and "Unknown" sentinels; missing legacy pre-0011 regression test)
- M6.5 → **PASS / ACCEPTED** (pre-merge HEAD `cec7210cf440b9cc06c040611e477cfed9ad5472`, implementation `86cc3ddcbb7625723ab1fb442cac65c53be46b87`, CI run `36837924850`)
- **M6 overall → PASS / ACCEPTED** (branch `build/m6`)
- **M7 → IMPLEMENTED / VERIFIED; independent review pending**, authorized scope: `docs/M7_SCOPE.md`; independent review required before merge.

Accepted M6 is merged into `origin/main` at `11b6e782ab7256607992b70cc0d0dee4ebe92a3a`, tagged `v0.7-m6`.
Verified local/remote `build/m7` starts at exactly that commit with a clean tree.
M7 implementation authorized by `docs/M7_SCOPE.md`; old review failures below remain historical evidence.
LOCAL DEVELOPMENT ONLY. No M8, merge/tag of M7, deployment, Hetzner or Hermes interaction.
M7.1 code HEAD `07658d8e9fdd29f0e642447fd1639efb0b08aa47` passed local acceptance and remote CI run `36910780514` (all jobs SUCCESS). Main remains `11b6e782ab7256607992b70cc0d0dee4ebe92a3a` / `v0.7-m6`. M7 is unmerged; M8 is not started.


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

## M3.1 — Minimal fix (final M3 review: PASS WITH TWO SMALL FIXES)

- **Telegram callback acknowledgement is guaranteed exactly once.** The
  shared `_answer_from_callback` helper now calls `answer_callback`
  before editing/sending; every callback handler delegates through it
  on its response path; the explicit `answer_callback` calls that
  previously preceded the helper were removed (no double-acknowledge).
  Result: malformed `fx:` / `pg:` / `rf:` payloads still get a safe
  Russian-language UI response (`Неизвестное действие.` + Back button)
  AND the Telegram client stops its "loading" indicator.
- **Startup failure is non-zero.** `bot.__main__.main()` now suppresses
  `KeyboardInterrupt` only; `SystemExit` (e.g. raised by `run()` when
  `TELEGRAM_BOT_TOKEN` is empty) propagates so the process exits with
  the failure code. Normal Ctrl+C remains a clean shutdown.
- **Token never logged.** The startup refusal path uses a static
  constant message; no token interpolation. Regression test asserts no
  record message on that path contains `sports_intel`, `postgres` or
  any token-like fragment.
- **Scope guard** — explicitly out of M3/M3.1 and not touched:
  scheduler, automatic discovery, sports collectors, odds, lineups /
  injuries, quota manager, research, MatchContext, LLM prediction,
  live football analysis. The Telegram bot remains a thin UI over the
  FastAPI backend.
- **Regression tests** added for malformed callbacks (`fx:not-a-uuid`,
  `pg:not-a-date:99`, `rf:not-a-date`) — assert `answer_callback` was
  called, the user receives a safe response, and no backend call was
  made — and for the startup-failure path (SystemExit + non-zero exit +
  token-free log message).

## M4 — Automated Match Data Collection + Odds + Quota/Freshness (branch `build/m4`)

- **Scheduler**: Celery Beat entries (discovery 09:00 / refresh 13:00
  Warsaw, pre-match scan `*/15`) built only when `scheduler_enabled`
  (default False — quota-safe); timezone via `conf.timezone` =
  `APP_TIMEZONE` (DST-safe); discovery reuses M2 idempotency identity.
- **Pre-match scanner**: DB-only planner (`pre_match_scan.py`) — selects
  upcoming enabled-league fixtures (aliased home/away join), decides
  MORNING vs PREMATCH categories by kickoff windows T-120/60/20 config,
  dispatches collectors through the framework; every collector re-checks
  freshness under a Redis coalescing lock.
- **Freshness policy** (`freshness.py`): per-category configurable TTLs +
  shorter PREMATCH TTLs; None captured_at always stale.
- **QuotaManager** (`quota.py`): deterministic pure `decide()` with
  P0–P3 priorities, reserve budget, degradation modes
  NORMAL/CONSERVE/CRITICAL/RESERVE_ONLY; header parser for API-Football +
  The Odds API; acquire/record persist to the ledger.
- **Framework ordering guarantee**: freshness → quota → coalesce-lock →
  fetch → persist → ledger; denied quota never reaches the provider
  (`QuotaUnavailableError`).
- **Request coalescing** (`locks.py`): Redis SET-NX locks with
  token-checked Lua release, JSON-safe result publication for waiters
  (dataclass asdict), timeout fallback.
- **Collectors**: standings, team_stats, availability
  (UNKNOWN/KNOWN_NONE/KNOWN_PRESENT — silence ≠ healthy), lineups
  (confirmed flag preserved; unavailable ≠ empty), form_inputs (MOCK
  placeholder), odds (immutable snapshot sets, implied/no-vig at persist).
- **Odds provider boundary**: typed protocol + keyless MOCK + contract-
  tested The Odds API v4 normalizer (`parse.py`: whitelist, h2h mapping,
  totals→ou_15/ou_25 by point, dedup) + live adapter with bounded retry,
  normalized ProviderError hierarchy, apiKey never logged.
- **Migration 0004** (+ ORM sync): standings/team_statistics/team_form/
  availability/lineup snapshots, odds_snapshot_sets + odds_prices,
  external_api_requests + quota_buckets; UUID PKs, UTC, immutable
  append-only snapshot families, DESC composite indexes;
  alembic check clean at head.
- **job_attempts closed**: worker executions record attempts via
  `record_job_attempt` (redacted error class only).
- **Status API**: `/v1/fixtures/{id}/status` (per-category freshness),
  `/v1/system/status`; strictly read-only.
- **Database-first UX proven by test**: GET fixtures/detail/status flow
  writes zero `external_api_requests` rows.
- **Tests**: 264 unit + 59 integration green; Ruff/format clean;
  strict mypy clean (87 files); compose validation OK.

## M4.1 — Corrective fixes (M4 review: FAIL)

- Sentinel regression: ApiFootballProvider never returns mock data.
- Two team snapshots from one provider response (availability/lineups).
- Pre-match planner selects only future fixtures.
- Redis coalesce locks publish real snapshot refs to waiting tasks.

## M4.2 — Corrective fixes (M4.1 review: FAIL)

- ForecastPhase MORNING vs PREMATCH driven by kickoff vs now.
- Availability writes home and away snapshots with UNKNOWN fallback.
- Sequential job attempts per job.
- Standings/team_stats shared across fixtures.

## M4.3 — Corrective fixes (M4.2 review: FAIL)

- Odds capability gating (no silent mock in sandbox/live).
- OddsProvider.request_markets() maps alternate_totals.
- Fixture-level lineup refresh aggregates both teams.
- Due generation identity: captured + TTL while fresh.
- Quota generation keyed to observation generation.
- The Odds API daily limit inferred from used + remaining.
- FAILED job requeue with same job UUID.
- Provider failure telemetry in ledger.

## M4.4 — Focused correctness fixes (M4.3 review: FAIL)

- API-Football /teams/statistics v3 normalization (loses→losses, goals
  totals, clean_sheet, failed_to_score; missing values stay None).
- Season identity pinned end-to-end: PreMatchDecision.season_id, exact
  Season resolver, `StandingsCollector.latest_snapshot` and
  `TeamStatisticsCollector.latest_snapshot` filter by season_id (missing
  season strictly returns (None, None) preventing cross-season fallback).
- Fixed `TeamStatisticsCollector.persist()` to omit invalid `source_fingerprint`
  argument matching `TeamStatisticsSnapshot` schema.
- Stable TTL refresh opportunity: due:missing without snapshot, scanner
  skips fresh snapshots, stale identity stable across scanner runs.
- QuotaBucket.observed_at derived from response finished_at.

## M5 — Web Research Subsystem (branch `build/m5`)

- **Domain Models & DTOs** (`src/sports_intelligence/research/models.py`):
  `ExtractedClaimDTO`, `ResearchDocumentDTO`, `ResearchRunResultDTO`.
- **Search Provider Boundary** (`src/sports_intelligence/providers/search/`):
  - Typed `SearchProvider` Protocol returning `SearchResponse` containing `SearchResultItem` lists.
  - `MockSearchProvider`: deterministic offline provider with canned responses, query fallbacks, error injection, call history, and JSONB-safe serialization.
  - `TavilySearchProvider`: production-ready adapter with bounded timeouts, retries (up to 3 attempts with exponential backoff and jitter), 4xx non-retryable handling, canonical URL normalization, secret redaction, and rate limit parsing.
  - Strict provider factory (`build_search_provider`): gating based on `app_env`, `search_provider`, and `search_api_key`. Refuses silent mock in live environments without explicit override.
- **Claim Extractor & Conflict Detection** (`src/sports_intelligence/research/`):
  - `build_research_queries`: bounded (max 6), deterministic queries per fixture based on team names, kickoff date, and forecast phase (`MORNING` broad preparation vs `PREMATCH` lineup/fitness refresh).
  - `deduplicate_search_results`, `normalize_url` (strips tracking parameters, query fragments, trailing slashes), `content_sha256`.
  - `RuleBasedClaimExtractor` / `MockClaimExtractor`: extracts claims across 8 categories (`AVAILABILITY`, `SUSPENSION`, `ROTATION`, `LINEUP`, `MANAGER_STATEMENT`, `TACTICAL`, `TRAVEL`, `TEAM_NEWS`), assigns team ownership, confidence scores, and extraction metadata.
  - `detect_conflicts`: detects contradictory claims (e.g. absent vs present for the same subject/player or team); strictly preserves both claims, flags `conflict_flag=True`, links `conflicting_claim_id`, and attaches audit metadata (never discards or merges contradictory claims).
  - `get_research_for_fixture`: anti-leakage audit service enforcing `as_of` temporal filtering (`retrieved_at <= as_of` and `published_at <= as_of`) for historical replay and point-in-time consistency.
- **Database Persistence & Migrations** (`src/sports_intelligence/db/`):
  - Models: `ResearchRun`, `ResearchDocument`, `ResearchClaim` with descending composite indexes (`ix_research_runs_fixture_captured`, `ix_research_docs_fixture_retrieved`, `ix_research_claims_fixture_type`) and foreign keys.
  - Alembic Migration `0006_m5_research_documents_claims.py`: clean downgrade and upgrade, fully verified by `alembic check`.
- **Collector & Workers Framework** (`src/sports_intelligence/collectors/` & `workers/`):
  - `ResearchCollector`: registered in framework (`name="research"`, `category=FreshnessCategory.RESEARCH`, `priority=Priority.P3`), supports coalescing locks (`research:{fixture_id}`), raw payload storage in `raw_provider_payloads`, and snapshot persistence.
  - Pre-match scanner: includes `FreshnessCategory.RESEARCH` in scan plan and TTL evaluations.
  - Celery tasks: `sports_intelligence.workers.tasks.research` routed to `research_io` queue.
- **REST API Routes** (`src/sports_intelligence/api/`):
  - `GET /v1/fixtures/{fixture_id}/research`: returns documents and claims with optional `as_of` query parameter.
  - `GET /v1/fixtures/{fixture_id}/status`: reflects `research` category freshness state (`fresh`, `stale`, `unknown`) and last refresh timestamp.
- **Graceful Degradation / Optionality**:
  - When `SEARCH_PROVIDER` is empty or disabled, or `RESEARCH_ENABLED=False`, zero external searches run, and the pipeline operates normally with empty research runs recorded as `NO_USEFUL_RESULTS`.

## M5.1 — Corrective fixes (M5 review: FAIL)

All review items implemented and independently verified:
- **Tavily retrieval-time capturing after response**: `retrieved_at` captured strictly after awaiting HTTP completion (`response = await self._client.post(...)`). Verified by delay-injected clock test.
- **Claim-level temporal safety**: Added timezone-aware `extracted_at` to `ResearchClaim`, composite index `ix_research_claims_fixture_extracted`, Alembic migration `0007_m51_claim_extracted_at_and_fk.py`, and point-in-time filtering `claim.extracted_at <= as_of`.
- **Search quota & ledger matching real HTTP calls**: `ResearchCollector` owns per-search-request accounting (`owns_quota = True`). Framework outer quota reservation skipped; each query performs `reserve(cost=1)` and records telemetry in ledger. Quota stoppage halts queries gracefully; fresh research skips search with zero provider calls.
- **Conflict referential integrity**: Preserves stable claim IDs end-to-end; added self-referential `DEFERRABLE INITIALLY DEFERRED` FK on `research_claims.conflicting_claim_id`; reciprocal references (`A.conflicting_claim_id == B.id` and `B.conflicting_claim_id == A.id`) directly queryable in PostgreSQL.
- **SearchProvider resource cleanup**: Closed via `aclose()` in `_run_collect_job()` `finally` block across success, quota denial, provider failure, and DB persistence failure. Unrelated sports/odds providers are not instantiated for research tasks.
- **Real structured research states**: Formally differentiates `DISABLED`, `PROVIDER_ERROR`, `NO_USEFUL_RESULTS`, `EXTRACTION_UNAVAILABLE`, and `AVAILABLE`.
- **Historical view consistency**: Default Option B (`mode="latest_run"`) returns evidence strictly belonging to the latest run at or before `as_of` without mixing run statuses and documents; optional Option A (`mode="accumulated"`) returns historical accumulated claims.
- **100% offline mock tests**: All automated tests run against mocks with zero real external search calls.

## M5.2 — Corrective fixes (M5.1 review: FAIL)

- **Retry orchestration in ResearchCollector**: Moved search retries from provider to collector level — each physical HTTP attempt now gets its own quota reserve and ledger entry.
- **Configurable claim extraction**: Added `research_claim_extraction_enabled: bool = True` to `Settings` as a first-class configuration field and removed dead condition checks.
- **Read API disabled status**: `GET /v1/fixtures/{fixture_id}/research` returns `DISABLED` state when research capability is disabled and no run exists.
- **Partial provider failure visibility**: Surfaces as `PROVIDER_ERROR` with failure diagnostics (`queries_planned`, `queries_attempted`, `queries_succeeded`, `partial_failure`, `provider_error_class`) stored in `details_jsonb` while preserving retrieved documents and claims.
- **Strict query parameter validation**: Query parameter `mode` typed as `Literal["latest_run", "accumulated"]` in API and service layer; invalid values rejected with HTTP 422.

## M5.3 — Runtime correctness fixes (M5.2 review: FAIL)

- **PROVIDER_ERROR retry job identity**: Replaced the `(None, None)` hack in `ResearchCollector.latest_snapshot()` with true `(captured_at, run_id)`; exposed state-aware `latest_run_info()` and `refresh_due()`; scanner generates deterministic `error_due:<epoch>` opportunity keys (`epoch = captured_at + error_retry_ttl`, default 900s). Tested full scanner lifecycle: no job before retry due, new job enqueued after retry due, de-duplicated within opportunity, second error opens later generation, success resumes normal 6h TTL.
- **Explicit QUOTA_DENIED state**: Differentiated local quota denial from external provider failures. Added `ResearchState.QUOTA_DENIED`; quota denial before first request yields 0 provider calls, 0 ledger rows, status `QUOTA_DENIED`, and reason in details; partial quota denial preserves retrieved documents and claims with status `QUOTA_DENIED`.
- **Accurate failure observation timestamps**: Every external attempt tracks its clock observation time; failures and partial failures record the exact post-failure observation timestamp on `ResearchRun.captured_at`; documents keep their own `retrieved_at`; historical `as_of` between document retrieval and failure does not reveal the later failed run.
- **Respect Retry-After for 429**: `compute_retry_delay()` parses `Retry-After` header on `ProviderRateLimitError`, bounded by `research_max_retry_after_seconds` (default 30s); deterministic exponential backoff fallback; injectable sleeper and clock for offline tests.
- **Fixture status capability-awareness**: Extended `CategoryState` Literal to include `"disabled"`; `GET /v1/fixtures/{fixture_id}/status` reports research freshness as `"disabled"` when research capability is disabled and no run exists.

## M6 — Deterministic Feature Builder + Data Quality Engine + Immutable MatchContext (branch `build/m6`)

- **Prerequisite Form Inputs Fix**: Extended mock provider canned completed fixtures to 10 fixtures (`src/sports_intelligence/providers/sports/mock.py`); updated `FormInputsCollector` default window_size to 10 and populated `is_home` and `result` fields; added `FreshnessCategory.TEAM_FORM` dispatch to `execute_plan()` in `pre_match_scan.py`.
- **Database Schema & Models (Migration 0008)**:
  - `feature_snapshots`: versioned (`features_v1`), composite unique on `(fixture_id, forecast_phase, as_of)`.
  - `data_quality_reports`: versioned (`quality_v1`), composite unique on `(fixture_id, forecast_phase, as_of)`, storing overall score, band (`gold`, `silver`, `bronze`, `abstain`), `can_predict`, and dimension scores.
  - `match_contexts`: versioned (`context_v1`), composite unique on `(fixture_id, forecast_phase, as_of)`, storing canonical context document and SHA-256 `context_hash`.
  - Migration cycle verified: `upgrade head`, `downgrade -1`, `upgrade head`, `alembic check` with 0 schema drift.
- **Point-in-Time Evidence Selector (`sports_intelligence.context.selector`)**:
  - Pure point-in-time queries strictly enforcing `<= as_of` across Fixture, Standings (exact league + season match), Team Stats, Form, Availability, Lineups, Odds (current + previous for movement), and Research (`get_research_for_fixture(mode="latest_run")`).
  - Zero leakage of future records.
- **Source Provenance Manifest (`sports_intelligence.context.provenance`)**:
  - Machine-readable manifest mapping each category to table, snapshot_id, provider, captured_at, payload reference.
  - Composite SHA-256 `source_fingerprint` uniquely capturing the source evidence snapshot state.
- **Deterministic Feature Builder V1 (`sports_intelligence.features.builder`)**:
  - Pure deterministic math calculating form PPG, goals for/against, scoring/conceding rates, clean sheets, home/away splits.
  - Schedule rest days and 7d/14d match congestion.
  - Standings rank and points deltas.
  - Availability counts and state.
  - Market no-vig probabilities and odds movement.
  - Strict preservation of `None` for missing data (never converts missing to 0.0). Missing diagnostics tracked in `missing_features`.
- **Deterministic Data Quality Engine (`sports_intelligence.quality.engine`)**:
  - Evaluates 7 dimensions (`fixture_identity`, `form`, `season_stats`, `availability`, `odds`, `research`, `lineups`).
  - Lineups policy strictly enforced: in `MORNING` phase, lineups are N/A and excluded from denominator; in `PREMATCH` phase, evaluated per publication/confirmation state.
  - Critical missing rules: `can_predict = False` if odds or form missing.
  - Quality bands: gold (>=0.85), silver (>=0.70), bronze (>=0.50), abstain (<0.50).
- **MatchContext V1 Schema & Idempotent Persistence (`sports_intelligence.context.models`, `builder`)**:
  - Strictly ordered 13 sections per spec.
  - Canonical JSON serialization with SHA-256 `context_hash`.
  - Idempotent upsert/re-read semantics in `build_and_persist_match_context`.
- **Celery Worker Task & Orchestration**:
  - Background task `context.build_match_context` on queue `evaluation`.
  - Pre-match scanner dispatches context build job when all required collector jobs are fresh.
- **Read-Only API Endpoints**:
  - `GET /v1/fixtures/{fixture_id}/quality`: returns quality report with dimension scores and quality band.
  - `GET /v1/fixtures/{fixture_id}/context`: returns full immutable MatchContext document and context hash.
  - Zero live external calls, read-only DB access.

## M6.1 — Correctness, Provenance, Freshness, and Orchestration Pass (branch `build/m6`)

- **Immutable Fixture Metadata Observation Model (`fixture_metadata_snapshots`)**:
  - Migration 0009: table `fixture_metadata_snapshots` tracking point-in-time fixture identity (kickoff, status, venue, round, league_id, season_id, observed team names, payload_id).
  - Added `payload_id` (ForeignKey to `raw_provider_payloads.id`, nullable=True) to `team_form_snapshots`.
  - Selector queries `fixture_metadata_snapshots` `<= as_of`.
- **Fixture Identity in Provenance**:
  - Added fixture metadata snapshot to source manifest and composite source fingerprint.
- **Research Provenance**:
  - Exposed real `ResearchRun.id` in `FixtureResearchView`.
  - Manifest includes run ID, status, selected document IDs, claim IDs, URLs, and extraction version.
- **Complete Odds Provenance**:
  - Included both current and previous odds snapshot set IDs in source manifest and fingerprint.
- **Deterministic Multi-Bookmaker Aggregation**:
  - Consensus median per market/selection across bookmakers.
  - Movement = current consensus median - previous consensus median.
- **Form Selection Filtering**:
  - Selector strictly filters `window_size == 10` and `scope == "overall"`.
- **Provider-Scoped Team External IDs**:
  - Match standings/team stats external IDs using `provider == snapshot.provider`.
- **Preserve Missing != 0 in Form Math**:
  - Do not convert missing GF/GA to 0. Do not treat missing GA as clean sheet or missing GF as failed to score.
- **Real Freshness in Data Quality**:
  - Evaluate snapshot age at `as_of` using configured phase TTLs. Populate `stale_sources` and penalties.
- **Canonical Lineup Publication States**:
  - `CONFIRMED`, `NOT_YET_PUBLISHED`, `UNSUPPORTED`, `PROVIDER_ERROR`.
- **Distinguish Research Not-Collected from NO_USEFUL_RESULTS**:
  - Distinguish `no_run_collected` (0.50 score + warning) from `NO_USEFUL_RESULTS` (0.85 score), `DISABLED`, `PROVIDER_ERROR`, `QUOTA_DENIED`.
- **Configurable Quality Policy**:
  - Runtime configurable weights/thresholds via Settings.
- **Context-Build Readiness Semantics**:
  - Scanner refuses context build if required collector job is `PENDING`, `RUNNING`, or has pending enqueues.
- **Source-Generation Context Build Identity**:
  - Idempotency key: `context_build:{fixture_id}:{phase}:{schema_version}:{source_fingerprint}`.
- **Safe Context Job Retry**:
  - CAS transition `FAILED -> PENDING` on retry with same UUID.
- **Concurrent Context Build Idempotency**:
  - Safe upsert / unique conflict handling across `feature_snapshots`, `data_quality_reports`, `match_contexts`.
- **Feature-Level Provenance**:
  - Feature family provenance map linking feature groups to source snapshot IDs stored in `feature_provenance_jsonb`.
- **API Input Validation**:
  - Typed `ForecastPhase` enum query parameter (HTTP 422 on invalid).

## M6.2 — Final Acceptance-Hardening Pass (branch `build/m6`)

- **Historical Migration 0003 Integrity**:
  - Reverted `0003_provider_evidence_history_and_indexes.py` to be 100% byte-for-byte identical to `origin/main` (SHA-256 verified).
- **Authoritative Fixture Metadata & Historical Fallback Removal**:
  - FixtureMetadataSnapshot is authoritative for historical MatchContext fixture metadata.
  - When no snapshot exists `<= as_of`, status is `"METADATA_UNAVAILABLE"`, `venue=None`, `round=None`, `fixture_metadata_snapshot_id=None`. Does NOT fall back to mutable canonical Fixture status (e.g. "FT").
  - Data quality flags `"fixture_metadata_missing"` in `critical_missing`, evaluating band to `"abstain"` and setting `can_predict=False`.
  - When snapshot exists `<= as_of`, uses its `league_id`, `season_id`, `home_team_id`, `away_team_id`, observed team names, kickoff_at, venue, round, status, provider, provider_fixture_id, captured_at, payload_id, source_version, and fetches league using the snapshot's `league_id`.
- **Migration 0009 Legacy Baseline Backfill**:
  - Migration 0009 backfills `legacy_baseline` snapshot for pre-existing fixtures at `clock_timestamp()` (NOT backdated).
  - Added `policy_fingerprint` to `data_quality_reports` table and model.
  - Updated unique constraint `uq_data_quality_reports_identity` to include `policy_fingerprint`.
  - Symmetrical downgrade drops constraint, columns, and tables cleanly.
- **Complete Fixture Provenance**:
  - Source manifest fixture_metadata record includes `snapshot_id`, `provider`, `captured_at`, `payload_id`, `provider_fixture_id`, `source_version`, `league_id`, `season_id`, `home_team_id`, `away_team_id`. No fake legacy IDs.
  - When missing, records `snapshot_id=None`, `details={"error": "fixture_metadata_missing", "authoritative": False}`.
- **Runtime Quality Settings Wiring**:
  - Implemented `build_quality_policy(settings: Settings) -> QualityPolicy`.
  - Context worker builds `QualityPolicy` and `FreshnessPolicy` from real `resolved_settings` and passes them to `build_and_persist_match_context`.
  - Removed hardcoded staleness penalties: uses `staleness_penalty` and `max_staleness_penalty` from `QualityPolicy`.
- **Strict Quality Configuration Validation**:
  - `Settings.validate_quality_settings` and `QualityPolicy.__post_init__` validate: all weights >= 0, total active weight > 0, `0 <= min_predict_score <= 1`, `0 <= usable <= good <= excellent <= 1`, `staleness_penalty >= 0`, `0 <= max_staleness_penalty <= 1`.
- **Quality Policy Fingerprint & Identity**:
  - Deterministic SHA-256 `policy_fingerprint` from canonical JSON of `QualityPolicy.to_dict()`.
  - Persisted in `data_quality_reports.policy_fingerprint` and bound in `uq_data_quality_reports_identity`.
  - Distinct policies for the same evidence and as_of create separate quality report identities and persist without conflict.
- **Build Configuration Generation in Context Job Identity**:
  - Deterministic `compute_build_config_fingerprint` from context schema version, feature schema version, quality schema version, policy fingerprint, and research enabled.
  - Pre-match scanner constructs job key: `context_build:{fixture_id}:{phase}:{source_fingerprint}:{build_config_fingerprint}`.
- **Deterministic Market Snapshot Serialization**:
  - Sorted OddsPrice rows deterministically by `(market, selection, bookmaker, line, decimal_odds, id)`.
  - Replaced misleading singular `bookmaker` with `bookmakers: list[str]`.
  - Insertion order in database does not affect canonical JSON or `context_hash`.
- **Compatible Previous Odds Snapshot Requirement**:
  - Query strictly requires `OddsSnapshotSet.provider == odds_set.provider` and `captured_at < odds_set.captured_at`.
  - Cross-provider snapshots are never paired for movement; movement defaults to None.
- **Strict Typed MatchContext Schema**:
  - Converted `MatchContextV1` and all section models to Pydantic with `ConfigDict(extra="forbid", frozen=True)`.
  - Validates full context before canonical serialization, hash, and persistence. Unexpected extra fields fail immediately with `ValidationError`.
- **Complete Structured Research Claim Source References**:
  - Added `ResearchClaimSource` with document_id, url, domain, title, published_at, retrieved_at, content_hash, provider.
  - Every claim in MatchContext contains a structured `source` reference.
- **Historical Provider Mapping Semantics & Isolation**:
  - `ProviderEntityId` queries filter `first_seen_at <= as_of_utc`.
  - `get_home_external_id(provider)` and `get_away_external_id(provider)` return `None` when the requested provider is unmapped (never falls back to an arbitrary provider).
- **MORNING Lineups Fully N/A**:
  - Lineups dimension weight excluded from score denominator.
  - Missing lineups do not hurt; stale lineups do not enter `stale_sources` and do not trigger staleness penalties or warnings.

## M6.3 — Reproducibility and Historical-Authority Pass (branch `build/m6`)

- **Authoritative Fixture Metadata & Historical Refusal**:
  - Context selector and builder strictly enforce `FixtureMetadataSnapshot` as the single source of truth for fixture dimensions.
  - When no `FixtureMetadataSnapshot` exists with `captured_at <= as_of`, the context builder raises typed `HistoricalFixtureMetadataUnavailable` error instead of falling back to mutable canonical `Fixture` attributes (e.g. status, kickoff, teams).
  - No `FeatureSnapshot`, `DataQualityReport`, or `MatchContext` is persisted for historical builds lacking authoritative metadata.
  - Worker safely handles `HistoricalFixtureMetadataUnavailable` without exposing internal traces or crashing workers.
- **End-to-End Metadata Snapshot Team IDs**:
  - Authoritative `home_team_id` and `away_team_id` from the selected snapshot are propagated to all downstream queries: availability, lineups, standings, team stats, and form.
  - Provider mapping lookup resolves `ProviderEntityId` using the snapshot's authoritative team IDs with `first_seen_at <= as_of_utc`.
- **Complete Provider Mapping Provenance**:
  - Source manifest records all resolved provider entity mappings under `provider_mappings` section with `provider`, `internal_id`, `external_id`, `entity_type`, and `first_seen_at`.
- **Deterministic Source Manifest Fingerprint**:
  - Deterministic serialization of the entire source manifest (fixture metadata, evidence snapshots, and provider entity mappings) into canonical JSON, computing a reproducible SHA-256 `source_fingerprint`.
- **Explicit Freshness Policy Identity & Snapshot**:
  - Introduced `FreshnessPolicy` dataclass with `freshness_policy_snapshot` dictionary and SHA-256 `freshness_policy_fingerprint`.
  - Added Alembic migration `0010_m6_3_freshness_policy.py` adding `freshness_policy_fingerprint` to `data_quality_reports` table and updated unique constraint `uq_data_quality_reports_identity` across `(fixture_id, phase, as_of, schema_version, source_fingerprint, policy_fingerprint, freshness_policy_fingerprint)`.
  - Migration includes clean symmetrical downgrade.
- **ContextBuildPolicy**:
  - Unified `QualityPolicy` and `FreshnessPolicy` into `ContextBuildPolicy`.
  - Computes `build_config_fingerprint` embedded in Celery task idempotency key: `context_build:{fixture_id}:{phase}:{source_fingerprint}:{build_config_fingerprint}`.
- **Strict Pydantic MatchContext Schema**:
  - Enforced `ConfigDict(extra="forbid", frozen=True)` across all 13 sections and root `MatchContextV1`.
- **Full Test & CI Validation**:
  - All 453 tests passing (357 unit + 96 integration).
  - Ruff, format, and mypy (118 source files) 100% clean.
  - Alembic migration lifecycle verified with zero schema drift.
  - GitHub Actions run `36831445894` passed all 3 jobs on exact remote HEAD `5fb6c604617c7f93117e6d42d623a92082461981`.

## M6.4 — Acceptance-Fix Pass (branch `build/m6`)

- **Historical League Metadata Authority**:
  - Eliminated dependency on mutable canonical `League.name` and `League.slug` during historical context reconstruction.
  - Created migration `0011_m6_4_historical_league_metadata.py` adding `observed_league_name` and `observed_league_slug` to `fixture_metadata_snapshots`.
  - Backfilled existing snapshot records from `leagues` table at migration time; clean symmetrical downgrade drops columns.
  - Context selector (`select_evidence`) reads league identity directly from `FixtureMetadataSnapshot.observed_league_name` and `observed_league_slug`.
  - Provenance builder captures observed league name and slug under `fixture_metadata.details`.
  - Regression verified: mutating `League` row after historical `as_of` leaves historical MatchContext identity, source fingerprint, and context hash 100% identical.
- **Deterministic Provider-Mapping Selection and Order**:
  - Query ordering in `select_evidence` explicitly orders by `ProviderEntityId.provider.asc(), ProviderEntityId.first_seen_at.desc(), ProviderEntityId.external_id.asc(), ProviderEntityId.id.asc()`.
  - When multiple mappings exist for a provider `<= as_of`, deterministically selects the latest `first_seen_at` (tie-broken by `external_id` then `id`). Future mappings (`first_seen_at > as_of`) are excluded.
  - Mappings in `SelectedFixtureInfo.home_provider_mappings` and `away_provider_mappings` are canonically sorted by `(provider, -first_seen_at.timestamp(), external_id, str(mapping_id))`.
  - Regression verified: identical logical mappings inserted in opposite orders produce identical `SelectedFixtureInfo`, `source_manifest`, `source_fingerprint`, and `context_hash`.
- **Pydantic Immutability Claim Audit**:
  - Audited documentation and test suite regarding immutability guarantees.
  - Clarified that `ConfigDict(frozen=True)` provides attribute-level freezing (preventing attribute reassignment or adding new attributes), but standard Python mutable containers (e.g. `list.append()`) are not deeply frozen by Pydantic.
  - Formalized that the authoritative immutability boundary is persistence in PostgreSQL: `match_contexts` rows are immutable historical snapshots.
  - Added unit test `test_match_context_immutability_attribute_frozen_and_nested_behavior` explicitly demonstrating attribute freeze and documenting deep container behavior.
- **Celery Task Error Semantics**:
  - Context build Celery task catches `HistoricalFixtureMetadataUnavailable` specifically.
  - Logs a structured warning (zero unexpected traceback dumps).
  - Marks Celery job `FAILED` in the database ledger (`jobs` and `job_attempts`).
  - Re-raises the exception for Celery worker failure accounting.
  - Regression verified: no `MatchContextRecord`, `FeatureSnapshot`, or `DataQualityReport` persisted; job recorded as `FAILED` with `error_class="HistoricalFixtureMetadataUnavailable"`.
- **Migration & Documentation Hygiene**:
  - Fixed migration `0010_m6_3_freshness_policy.py` revision docstring from `cb9a7f960dbe` to `0010`.
  - Migration `0011` verified through `upgrade head` -> `downgrade -1` -> `upgrade head` -> `alembic check` with zero schema drift.

## M6.5 — Historical-Truthfulness Acceptance Pass (branch `build/m6`)

- **Elimination of False Historical Backfill**:
  - In migration `0011_m6_4_historical_league_metadata.py`, removed the SQL query updating pre-existing `fixture_metadata_snapshots` from current mutable `leagues` table at migration time.
  - Pre-0011 snapshots do not acquire migration-time values; legacy rows truthfully retain `NULL` for `observed_league_name` and `observed_league_slug`.
  - Symmetrical downgrade cleanly drops columns with zero data residue.
- **Elimination of Mutable League Fallback**:
  - In `select_evidence`, removed all fallbacks to mutable `League` table row attributes (`league_obj.name`/`league_obj.slug`) and eliminated invented string sentinels (`"Unknown"`/`"unknown"`).
  - Simplified mutable `Fixture` locator to an existence check (`select(Fixture.id)`).
  - If display league identity is unobserved in historical snapshot, `league_name` and `league_slug` evaluate to `None`.
- **Display Metadata Nullability**:
  - Made `SelectedFixtureInfo.league_name`, `SelectedFixtureInfo.league_slug`, and `FixtureIdentitySection.league_name`/`league_slug` nullable (`str | None = None`).
  - Core `league_id` remains strictly authoritative and non-null.
- **Truthful Quality & Provenance Reporting**:
  - In `evaluate_data_quality`, missing observed league display identity records a structured warning (`"Observed league display identity unavailable in historical metadata snapshot"`) and missing field (`field="observed_league_display"`).
  - Missing display fields do not trigger `fixture_metadata_missing` in `critical_missing` and do not block `can_predict` when core IDs and kickoff are present.
  - Manifest truthfully records `null` for `observed_league_name` and `observed_league_slug`.
- **Comprehensive Regression Verification**:
  - Added unit test `test_match_context_with_none_league_display_metadata_serializes_cleanly` verifying `None` display fields serialize cleanly to canonical JSON (`"league_name":null`) with valid SHA-256 hash.
  - Added 10-step integration regression test `test_legacy_pre_0011_metadata_snapshot_does_not_acquire_migration_league_values` covering steps A through J: schema 0010 downgrade, legacy insert at T0, migration 0011 upgrade at T1 without backfill, context build between T0 and T1, absent mutable values, truthful provenance, League mutation at T2, and replay reproducibility with matching context hash and source fingerprint.

---

## M7 — LLM prediction, routing, baselines and deterministic ranking

- Provider-independent Mock/OpenAI-compatible/OpenAI/MiniMax/OpenCode Go HTTP architecture;
  structured JSON/Pydantic, explicit credentials, low supported sampling, bounded retries and one repair globally.
- Deterministic routes/capabilities/health/fallback with actual model/usage/request metadata persisted.
- Versioned prompt/config/policy hashes frozen at enqueue; semantic reuse and explicit immutable reruns.
- All 12 V1 selections, compact grounded evidence, abstention vs valid NO_BET, no ensembles.
- Separate captured no-vig baseline and unadjusted independent Poisson with truthful missing inputs/limits.
- PRIMARY/CHALLENGER and WITH/WITHOUT_ODDS; conservative masking removes research free text too.
- Deterministic filters, stable rank, exact odds snapshot/time, all considered reasons persisted.
- Migration 0012 adds seven M7 tables; existing ledger and Job/JobAttempt semantics retained.
- Analyze API queues llm jobs; list/detail endpoints and thin Russian Telegram screens read DB-backed API.
- Opt-in context completion hook integrates with existing MORNING/PREMATCH scanner/context flow.
- Local gates: 531 unit + 128 integration = 659 passed; Ruff/format/mypy clean (142 source files).
- Fresh and populated M6 migration cycles/drift check + Compose and Telegram profile validation passed.
- Zero real LLM calls (no configured runtime credentials); no new live Telegram verification.
- See [PREDICTIONS.md](PREDICTIONS.md) / ADR 0010. Implementation CI `36890119992` passed; independent review pending.


### M7.1 — M4 canonical odds contract acceptance fix (PASS / ACCEPTANCE VERIFIED)

- Reviewed starting HEAD: `b0dd35c3606449d95c3be0723ded5f78a2883e67` on clean `build/m7`.
- M4 normalizer persists `h2h_1x2` with `home/draw/away`; M7 accepted aliases `h2h`/`1x2` but omitted the canonical market.
- M7 baseline now maps all three spellings into one complete 1X2 group. Missing bookmaker or any missing/cross-book selection cannot form the benchmark.
- Double Chance baseline still skips M4's overlapping, sum-1 generic normalization and derives all three DC values from a complete same-bookmaker M4 1X2 group.
- M7 odds synthetic context and M4 MockOddsProvider normalized output use `h2h_1x2`; outgoing Odds API request key remains `h2h`.
- Regressions assert HOME/DRAW/AWAY benchmark, all three DC sums, ranking with real canonical rows, incomplete-market refusal, same-book isolation, canonical mock output, and the full M7 keyless E2E.
- Focused checks so far: **33 unit/M4-provider tests passed; 27 M7 integration tests passed**.
- No DB/schema or live-provider changes. Full acceptance suite, docs closeout, push and exact remote CI remain pending.

---

# 3. In progress

M7.1 code accepted by all local gates and CI. Final docs-only handoff CI is pending; then STOP for independent review. Binding scope: [M7_SCOPE.md](M7_SCOPE.md).
M6 accepted merge/tag confirmed. M7.1 code CI is green on `07658d8e…`; final docs-only HEAD CI is pending.

---

# 4. Acceptance tests passed (actually run, M6.5 state)

- `uv run pytest -q -m "not integration"` → **361 passed, 100 deselected in 3.73s**
- Integration suite (isolated `sports_intel_test` DB + Redis db15) →
  **100 passed, 361 deselected in 15.82s** (all M2/M3/M4/M5 integration tests
  plus M6 strict anti-leakage, context build idempotency, Celery task execution, API endpoints,
  metadata authority overrides, policy fingerprints, deterministic odds serialization, provider isolation,
  M6.3 HistoricalFixtureMetadataUnavailable refusals, M6.4 historical league immutability,
  M6.4 deterministic provider mapping ordering, M6.4 Celery task refusal persistence,
  and M6.5 pre-0011 legacy snapshot truthful replay without false backfill)
- Full test suite (`uv run pytest -q`) → **461 passed in 17.65s**
- `uv run ruff check .` / `ruff format --check .` → clean (All checks passed! / 177 files formatted)
- `uv run mypy src` → **Success: no issues found in 119 source files** (strict)
- `alembic upgrade head` / `downgrade -1` / `upgrade head` / `alembic check` → clean (No new upgrade operations detected)
- `docker compose config -q` and `docker compose --profile telegram config -q` (+dev) → OK
- Secret scan: clean (zero credentials committed; no secrets in tracked files)
- Determinism check: zero live external API calls, zero LLM calls, zero betting recommendations.


## M3-era live smoke (historical, still valid)

- Docker live smoke: full stack incl. `sports-telegram`; MOCK discovery
  job SUCCEEDED via Celery; duplicate POST → `already_queued`.

---

# 5. External integrations

## Verified live

- **API-Football fixture discovery** — bounded live smoke (M2: 2 requests,
  M2.1: 1 request): real response, normalization, persistence, repeat
  idempotency, evidence history, rate-limit headers, `timezone` parameter.
  Full production use not yet exercised (single date, single league).
- **Tavily search provider** — bounded live smoke (M5: 2 requests total):
  1 provider-level query check + 1 collector-driven run for real fixture
  (`Brentford vs Tottenham`). Verified HTTP contract, RFC 2822 publication date
  parsing, ResearchDocument persistence, ResearchClaim extraction (8 claims),
  anti-leakage `as_of` temporal query, and zero credential leakage.

## Mocked / not yet verified

- Odds provider (interface only, M4)
- Runtime LLM providers (M7 HTTP contract-tested with injected transports; no live runtime calls)

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
- migrations `0001` through `0012` locally verified on a fresh isolated test DB; implementation CI `36890119992` passed
  (apply → repeat → downgrade → reapply); ORM↔migration drift check clean.
- Historical revision `0003_provider_evidence_history_and_indexes.py` verified 100%
  byte-for-byte identical to `origin/main` (SHA-256 identical).

Latest migration:
- `0012_m7_prediction_engine` (M0–M6 historical migration files unchanged).
- M7 verified on fresh `sports_intel_m7_test`, populated M6→M7, downgrade/re-upgrade and zero drift.

Local DB preservation required:
- no, until meaningful live test data exists

---

# 9. API/quota status

Provider:
- API-Football — selected (ADR-0007); verified via bounded live smokes
  (M2/M2.1). Sportmonks remains a documented migration path.

Quota telemetry:
- implemented (M4): `QuotaManager` + ledger (`external_api_requests`,
  `quota_buckets`); degradation modes NORMAL/CONSERVE/CRITICAL/
  RESERVE_ONLY; provider headers parsed from API-Football and The Odds
  API formats. Live-provider quota telemetry not yet exercised
  (MOCK-only so far).

Cache:
- request coalescing via Redis locks + freshness TTLs (M4). No HTTP
  response cache yet (spec 11 future work).

---

# 10. Current model/runtime configuration

Development lead:
- Codex (development agent; separate from runtime providers)

Runtime prediction model:
- not selected empirically

LLM provider routing:
- M7 deterministic config/health/capability router implemented; MOCK defaults, real calls gated.

---

# 11. Current Git state

Branch: `build/m7`; M7.1 code HEAD `07658d8e9fdd29f0e642447fd1639efb0b08aa47`.
M7.1 CI run `36910780514`: unit/lint/type, integration, Compose all SUCCESS.
Accepted base/main remains `11b6e782ab7256607992b70cc0d0dee4ebe92a3a` (`v0.7-m6`).
Final docs-only HEAD CI is verified separately. Do not modify main or merge/tag M7.

---

# 12. Next action

STOP for independent review after final documentation HEAD verification. M8 and deployment remain unauthorized.

---

# 13. Reviewer notes

**Final review verdict (2026-08-21): M2 PASS — M2 ACCEPTED.**
Safe to begin M3: YES.

**Final review verdict (2026-08-21): M3 PASS — M3 ACCEPTED.**
Safe to begin M4: YES.

**Final review verdict (2026-09-29): M4 PASS — M4 ACCEPTED.**
Safe to begin M5: YES.

**Review verdict (2026-09-29): M5 FAIL — focused M5.1 required.**
**Review verdict (2026-09-29): M5.1 FAIL — focused M5.2 required.**
**Review verdict (2026-09-29): M5.2 FAIL — focused M5.3 required.**
**Final review verdict (2026-09-29): M5.3 / M5 PASS — M5 ACCEPTED.**
Accepted implementation remote HEAD: `b38229b0874e9ab992ae25ea2a63e1e6109f8ca7`.
Safe to begin M6: YES (following merge and tag).

**Review verdict (2026-09-30): M6 FAIL — focused M6.1 required.**
Reviewed HEAD: `fff8df75c520696f6c25a14e19ded7b6711e7688`
Verdict: FAIL

**Review verdict (2026-09-30): M6.1 FAIL — focused M6.2 required.**
Reviewed HEAD: `08d253fe90883f11456b402563f4065fc4b00072`
Verdict: FAIL

**Milestone M6.2: Final Acceptance-Hardening Pass completed and AWAITING INDEPENDENT REVIEW.**
Quality Bands: `excellent` (>= 0.90 default), `good` (>= 0.80), `usable_with_warnings` (>= 0.65), `abstain` (< 0.65 or critical missing).
All 14 work items and 19 regression scenarios verified.

---

# 14. Future roadmap (post-M3, NOT implemented)

Documented future requirements only; no implementation yet, no live
subsystem design at this stage.

- The scheduled pipeline (M4+) must populate PostgreSQL automatically,
  independent of Telegram usage. Telegram fixture screens must read
  essentially-ready data from the DB.
- An availability / lineup collector may in the future perform bounded
  pre-kickoff refresh close to kickoff.
- A confirmed / new lineup snapshot may in the future create a new
  `PREMATCH_FINAL` prediction rather than overwriting `MORNING`.
- Future live analytics is a separate post-v1 extension, not part of
  M3 / M4.

M3.1 explicitly does NOT implement any of this and does not design a
live subsystem.

A reviewer should start by reading:

1. `AGENTS.md`
2. this file
3. `docs/CURRENT_TASK.md`
4. `docs/REVIEW_HANDOFF.md`
5. relevant specification
6. Git diff `main..build/m2`
