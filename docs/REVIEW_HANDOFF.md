# Review Handoff

Use this file when handing the repository to ChatGPT, Kimi, another
engineer, or a fresh coding-agent session.

Update it before every milestone review.

---

# Review status

**Ready for review:** YES  
**Development phase:** LOCAL DEVELOPMENT ONLY  
**Milestone:** M4.1 — corrective implementation after M4 review **FAIL**  
**Review target branch:** `build/m4` (NOT merged to main)  
**Review target commit:** `2fa0316` — M4.1 corrective fixes after M4
review FAIL  
**Previous accepted state:** `main` = `7d23c9d` (M3 accepted via PR #5)  
**Review scope:** diff `main..build/m4` (M4 + M4.1)

---

# Independent review history

- **M4 review verdict (2026-08-24):** **FAIL — M4 is NOT mergeable.**
  Core automatic/live-data paths contained correctness and
  data-integrity failures. M4.1 implemented on `build/m4`.
- **M4.1:** awaiting independent review.

---

# What changed in M4.1 (the 14 required fixes)

## 1. Scheduled discovery execution

- New Beat target `sports.schedule_discovery(slot)` (slot ∈
  {morning, refresh}) in `workers/tasks/scheduling.py`. It resolves
  today in APP_TIMEZONE, loads LeagueConfig + version, captures
  provider + timezone, creates-or-gets a proper `jobs` row with a
  slot-distinct idempotency key, and enqueues
  `sports.discover_fixtures` with the full immutable tuple
  (job_id, fixture_date, version, timezone). Enqueue failure marks the
  job FAILED.
- Beat schedule now targets the wrapper (with `args: ["morning"]` /
  `["refresh"]`, queue `control`). Morning and refresh are distinct
  idempotent runs — the 13:00 refresh is never suppressed by the
  successful 09:00 run (test proves distinct keys).
- Eager execution test proves Job creation + full-tuple enqueue with no
  argument errors.
- Discovery pipeline passes through quota reservation + ledger before
  the provider HTTP call (started_at before request, duration incl.
  HTTP, status/error class/headers recorded).

## 2. No fake sports data in real-provider paths

- `SportsDataProvider` protocol extended with typed methods:
  `get_standings`, `get_team_statistics`, `get_availability`,
  `get_lineups`, `get_completed_fixtures` (DTOs in `providers/dto.py`).
- `ApiFootballProvider` implements all five against real endpoints
  (/standings, /teams/statistics, /injuries, /fixtures/lineups,
  /fixtures?status=ft-aet-pen) with pure parser functions; it NEVER
  reads `_MOCK_*` constants (those live only in `MockSportsDataProvider`).
- Collectors resolve internal UUIDs → provider external ids via
  `provider_entity_ids` (never send internal UUIDs as API-Football ids).
- Sentinel regression tests: real adapter + MockTransport returning
  distinctive values; each collector persists EXACTLY those values;
  canned Arsenal/Coventry/Mock United never appear.

## 3. Team-specific availability/lineup persistence

- One provider request per fixture returns BOTH teams; the collector
  persists ONE snapshot PER TEAM from that single observation (players
  are never concatenated/merged).
- `latest_snapshot` includes `team_id` for team-scoped entities.
- Test: one fixture, two teams → exactly two correctly separated
  snapshots (KNOWN_PRESENT home, UNKNOWN away in MOCK).

## 4. Bounded, state-aware lineup windows

- `lineup_poll_due()` policy: no polling for started fixtures; CONFIRMED
  stops polling; within-window per-window refresh (T-120 unconfirmed
  does NOT block T-60/T-20); outside all windows → no poll.
- Lineup snapshots carry `publication_state`
  (NOT_YET_PUBLISHED / CONFIRMED / UNSUPPORTED / PROVIDER_ERROR) via
  migration 0005; absence is never an empty confirmed lineup.
- Planner uses Warsaw calendar-day → UTC boundaries
  (`utc_window_for_local_day`) and only future/not-started fixtures.
- `PreMatchDecision.phase` propagates into `CollectorContext` so
  PREMATCH freshness TTLs are actually applied.

## 5. Coalescing correctness

- Framework flow: fast freshness hit → real persisted snapshot id →
  lock (correctness/budget boundary) → winner double-check → quota
  reserve → provider fetch → raw evidence + snapshot persist → ledger →
  publish REAL persisted refs.
- Waiters NEVER call the provider, NEVER persist a second copy, NEVER
  write another ledger row; they return the winner's persisted UUID.
- Freshness hit returns the actual existing snapshot id (never a random
  UUID).
- The "still contended → fetch anyway" fallback is REMOVED: a contended
  lock without a published result raises `LockContendedError`.
- 10-caller synchronized integration test: 1 provider call / 1
  snapshot / 1 ledger row / all callers get the same UUID.

## 6. QuotaManager semantics

- Thresholds are percentages of the ACTUAL observed limit
  (`effective_reserve` clamps the absolute reserve into the CRITICAL
  band so CRITICAL stays reachable — tested at limits 100/500/7500).
- CONSERVE pauses P3; CRITICAL pauses P2/P3 (preserves P0/P1);
  RESERVE_ONLY allows P0 only; reserve protection denies non-P0 work
  that would breach the floor.
- Concurrency-safe reservation via atomic Redis INCRBY counters keyed
  provider/window/period (integration test: 10 workers, exactly 4
  succeed against usable budget).
- Estimated cost supported (credits), not just request counts.

## 7. Provider-specific quota headers

- `parse_quota_headers(provider, headers)`: API-Football → daily
  (x-ratelimit-requests-limit/remaining) + minute
  (X-RateLimit-Limit/Remaining); The Odds API →
  x-requests-remaining / x-requests-used / x-requests-last = COST (not
  minute remaining).

## 8. Request-ledger telemetry

- `record_success` / `record_failure`: started_at BEFORE the network
  request, duration covering the HTTP operation, status code where
  known, normalized error class, actual response quota headers,
  estimated + actual cost, cache/coalesced status. Failures are
  visible (error_class + status_code persisted).

## 9. The Odds API integration

- Correct endpoint contract:
  `/v4/sports/{sport_key}/events/{provider_event_id}/odds` and the free
  events listing for resolution.
- `odds_sport_key` per internal league (string) from LeagueConfig.
- `resolve_event` matches strictly by team names + kickoff tolerance;
  zero matches and multiple matches are hard `ProviderMappingError`s —
  never guessed.
- Resolved mappings persisted in `odds_event_mappings` (migration 0005)
  for reuse.
- Internal fixture UUIDs NEVER placed in external URLs (test asserts
  exact path uses sport key + provider event id).

## 10. Raw evidence linkage

- Framework stores content-deduped raw payloads + observation rows
  (`store_raw_evidence`) BEFORE snapshot persist; every M4 snapshot
  carries `payload_id` → raw payload (test asserts non-null + raw row
  exists). Repeated identical payload creates a new observation but
  reuses the content blob (M2 semantics).

## 11. job_attempts

- `record_job_attempt` derives attempt_number per job (1, 2, 3…);
  uniqueness races retried then fail loud (never silently swallowed);
  worker identity = real `hostname:pid`.

## 12. Pre-match scanner dispatches jobs

- Scanner is cheap: DB scan → deterministic plan → enqueue
  `sports.collect` jobs with proper `jobs` rows + attempt recording.
  No external collectors run inline in the Beat task.
- Exception-safe finally: Redis client, provider clients, DB engine all
  closed.

## 13. Form inputs

- `FormInputsCollector` derives deterministic W/D/L from normalized
  completed-fixture results (window last-N), persisted as
  `team_form_snapshots`; no LLM, no settlement logic.

## 14. Status API correctness

- `/v1/system/status` reports the ACTUAL degradation mode via
  `QuotaManager.observe` (no hard-coded NORMAL).
- Fixture freshness: team_stats/availability/lineups require BOTH teams
  fresh; lineup availability is publication-aware (CONFIRMED for all
  teams).
- Uses `Priority` enum properly (no string + type-ignore).
- Read endpoints remain DB-only (zero external calls — integration
  proven).

---

# Verification (actually run on this machine)

- `uv run pytest -q -m "not integration"` → **242 passed**
- Integration suite (`sports_intel_test` + Redis db15) → **41 passed**
  (M2/M2.4 regressions, schema-drift `alembic check`, migration cycle
  incl. 0005 + new M4.1 integration file)
- `uv run ruff check .` / `ruff format --check .` → clean
- `uv run mypy src` → **no issues in 86 source files** (strict)
- `docker compose config -q` (+telegram profile) → OK
- Secret scan → clean

# Known limitations (documented, intentional)

1. Form inputs = deterministic completed-result history; prediction/form
   features are M7+ scope.
2. The Odds API live path contract-tested; live verification only if
   credentials configured (never blocks acceptance).
3. Pre-match scan enqueues per (collector, lock-key, phase); batching
   odds across fixtures and per-collector queue fan-out are future
   optimizations.

# Scope guard respected

No research, MatchContext, LLM, prediction, candidate ranking,
settlement, live in-play, Hetzner, Hermes.

---

# Suggested review order

1. `AGENTS.md`, this file, `docs/CURRENT_TASK.md`
2. Git diff `main..build/m4`
3. Key files:
   - `src/sports_intelligence/collectors/framework.py` (lock/evidence/
     refs flow)
   - `src/sports_intelligence/collectors/quota.py`
   - `src/sports_intelligence/providers/sports/api_football.py`
   - `src/sports_intelligence/providers/odds/{factory,parse,base,mock}.py`
   - `src/sports_intelligence/workers/tasks/{scheduling,collect,pre_match}.py`
   - `tests/integration/test_m4_collectors.py`
   - `tests/unit/test_scheduled_discovery.py`,
     `tests/unit/test_api_football_categories.py`,
     `tests/unit/test_odds_mapping.py`

# Next action after PASS

Merge `build/m4` into `main`, tag `v0.5-m4`. Only then start M5 with
explicit user approval.
