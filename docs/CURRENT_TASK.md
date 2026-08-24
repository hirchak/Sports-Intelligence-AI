# Current Task

**Status:** COMPLETE (M4.2) — awaiting independent review
**Milestone:** M4.2 — focused corrective implementation after M4.1 review **FAIL**
**Owner/agent:** ox-alpha (OpenCode)
**Started at:** 2026-08-24
**Last updated:** 2026-08-24

---

# Task

Independent review of M4.1 returned **FAIL** (runtime/contract blockers).
M4.2 on `build/m4` implements the focused fixes WITHOUT redesigning the
correct M4.1 components:

1. **Collector job refresh identity**: replaced the permanent
   `collect:{name}:{lock_hash}:{phase}` key with deterministic
   refresh-opportunity identity — lineups use explicit T-window ids
   (`t120`/`t60`/`t20`), TTL categories use deterministic time buckets
   tied to the category TTL. Repeated scans inside one opportunity
   dedupe; a later window/expired-TTL opens a NEW job (proven by test).
2. **Lineup policy wired into real execution**: `lineup_poll_due()` is
   now the LineupCollector `refresh_due` override used by the framework
   (fast check + winner double-check); `decide_categories` no longer
   uses the `max(window)+60` approximation (PREMATCH starts exactly at
   the outermost window); NOT_YET_PUBLISHED at T-120 permits T-60,
   CONFIRMED stops polling, started fixtures are never polled; the
   generic 24h lineup TTL never overrides window logic.
3. **Fixture-level team snapshots**: availability/lineup persists BOTH
   fixture teams from ONE observation, driven by actual
   `fixture.home_team_id`/`away_team_id`; a side the provider did not
   cover is never CONFIRMED (conservative NOT_YET_PUBLISHED/UNKNOWN);
   empty responses persist explicit state for both sides; published
   refs contain BOTH team refs; synchronized home+away test: exactly 1
   provider call, 2 separated snapshots, each waiter gets its own UUID.
4. **Odds events contract**: `resolve_event` accepts the actual
   top-level JSON array from GET /v4/sports/{sport}/events;
   contract-faithful array fixtures; no-match/ambiguity remain hard
   errors.
5. **Odds markets**: real double-chance names (`Arsenal or Draw` …)
   normalized to canonical selections; `alternate_totals` supplies exact
   O/U 1.5/2.5 lines when the featured totals market omits them;
   canonical `ou_15`/`ou_25` preserved.
6. **No-vig completeness**: no-vig is derived ONLY on a complete
   expected selection set (1X2, double-chance, two-sided O/U, BTTS);
   incomplete markets never normalized.
7. **Odds fixture mapping**: home/away names loaded EXPLICITLY by id
   (no unordered SQL IN); reversed-row-order regression test.
8. **Odds quota cost**: `sports.collect` calls
   `OddsProvider.estimate_cost(markets, regions)` and reserves that cost
   BEFORE the network call (4 markets × 1 region → 4, not 1);
   `actual_cost` reconciled from `x-requests-last`.
9. **Quota reservation baseline**: Redis reservation is based on the
   provider's LATEST OBSERVED remaining minus reservations since that
   observation (not a fresh counter vs the full limit); tested at
   limit=100/observed=4 with concurrent P0/P1; P0 reserve preserved.
10. **Fail closed**: discovery fails closed when quota protection cannot
    initialize for REAL providers (MOCK stays keyless); Redis client
    closed in finally.
11. **API-Football /teams/statistics**: parser matches the actual v3
    contract (response = single object); contract-faithful fixture;
    bounded live smoke allowed only with a local SPORTS_API_KEY.
12. **Status API**: both-team category state is fresh only when BOTH
    snapshots exist and are fresh; one fresh + one missing → unknown;
    PREMATCH freshness semantics applied when the fixture is inside the
    pre-match horizon.

# Acceptance tests (M4.2) — run

- repeated collector-job refresh opportunity (dedupe then new job on
  T60) — integration;
- T120→T60→T20 runtime flow through the framework (not just pure
  function) — integration;
- synchronized home+away lineup collection: 1 provider call, 2
  snapshots, correct per-team refs — integration;
- contract-faithful The Odds API top-level array events + no-match +
  ambiguity;
- odds real double-chance + alternate totals contract fixtures;
- incomplete-market no-vig never normalized — unit;
- odds estimated-cost reservation (4 markets × 1 region) — integration;
- partially-depleted quota concurrency (observed remaining 4, P0/P1) —
  integration;
- real-provider quota-init failure → job FAILED + zero provider calls —
  integration;
- status one-team-missing → unknown, not fresh — integration;
- reversed-row-order odds mapping — integration;
- full suite, migrations + alembic check, Ruff/format, strict mypy
  (87 files), Compose, secret scan.

# Verification (actually run)

- `uv run pytest -q -m "not integration"` → **254 passed**
- integration suite (`sports_intel_test` + Redis db15) → **49 passed**
- `uv run ruff check .` / `ruff format --check .` → clean
- `uv run mypy src` → **no issues in 87 source files** (strict)
- `docker compose config -q` (+telegram profile) → OK
- Secret scan → clean

# Known limitations

- The Odds API live path is contract-tested; live verification only if
  credentials configured (never blocks acceptance).
- One bounded /teams/statistics live smoke is allowed only when a local
  SPORTS_API_KEY exists; not run here (no key).
- Odds batch (league-level) endpoint remains a future optimization;
  event-specific calls happen only after strict resolution.

---

# Completion

- Status: COMPLETE on `build/m4`. No merge to main; M5 not started.
- Review verdict to record: M4 → FAIL; M4.1 → FAIL; M4.2 awaiting
  independent review.