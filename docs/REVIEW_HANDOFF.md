# Review Handoff

Use this file when handing the repository to ChatGPT, Kimi, another
engineer, or a fresh coding-agent session.

Update it before every milestone review.

---

# Review status

**Ready for review:** YES  
**Development phase:** LOCAL DEVELOPMENT ONLY  
**Milestone:** M4.2 — focused corrective implementation after M4.1 review **FAIL**  
**Review target branch:** `build/m4` (NOT merged to main)  
**Previous accepted state:** `main` = `7d23c9d` (M3 accepted via PR #5)  
**Review scope:** diff `main..build/m4` (M4 + M4.1 + M4.2)

---

# Independent review history

- **M4 review verdict (2026-08-24):** **FAIL** — M4.1 implemented.
- **M4.1 review verdict (2026-08-24):** **FAIL** — runtime/contract
  blockers; M4.2 implemented on `build/m4`.
- **M4.2:** awaiting independent review.

---

# What changed in M4.2 (per FAIL item)

## 1. Collector job refresh identity

- `collectors/refresh.py`: `refresh_opportunity_suffix()` — lineups →
  explicit T-window id (`t120`/`t60`/`t20`/`no_window`); TTL categories
  → deterministic time bucket (≈ TTL/2, min 5 min).
- `workers/tasks/pre_match.py` `_enqueue` job key now includes the
  opportunity suffix: `collect:{name}:{lock_hash}:{phase}:{opportunity}`.
  Repeated scans inside one opportunity dedupe; a later window / expired
  TTL opens a NEW job (integration test: T120 scan → 1 job; duplicate
  scan → still 1; T60 scan → 2).

## 2. Lineup policy wired into real execution

- `Collector.refresh_due` hook in the framework (fast check + winner
  double-check); `LineupCollector.refresh_due` uses `lineup_poll_due`
  (kickoff from the fixture, latest publication_state, configured
  windows) — the generic 24h lineup TTL never applies.
- `decide_categories` PREMATCH starts exactly at the outermost T-window
  (removed `max+60`).
- Runtime flow proven end-to-end (integration): T-110 NOT_YET_PUBLISHED
  → 1 call; T-50 (T60 window) → 2nd call; published → CONFIRMED; T-10 →
  zero calls.

## 3. Fixture-level team snapshots

- Availability + lineup persists BOTH fixture teams from ONE observation
  using actual `fixture.home_team_id`/`away_team_id`; provider sides map
  via `provider_entity_ids`; uncovered side → conservative
  NOT_YET_PUBLISHED (lineups) / UNKNOWN (availability), never CONFIRMED;
  empty response persists explicit state for both sides.
- Published refs contain BOTH team refs; `_select_ref` returns each
  waiter its own UUID.
- Synchronized home+away test: exactly 1 provider call, 2 separated
  snapshots, correct per-team refs.

## 4. The Odds API events contract

- `resolve_event` accepts the actual top-level JSON array from
  GET /v4/sports/{sport}/events (defensive `data` wrapper tolerated).
  Contract-faithful array fixtures in tests; no-match/ambiguity remain
  `ProviderMappingError`s.

## 5. Odds markets

- Real double-chance names (`Arsenal or Draw`, `Coventry or Draw`,
  `Arsenal or Coventry`) → `home_or_draw` / `draw_or_away` /
  `home_or_away`.
- `alternate_totals` accepted as a totals source so exact O/U 1.5/2.5
  lines are captured even when the featured totals market omits one;
  canonical `ou_15`/`ou_25` preserved.

## 6. No-vig completeness

- `derive_market_view_safe` validates the COMPLETE expected selection
  set (1X2 = home/draw/away; double_chance = 3; O/U = over/under; BTTS =
  yes/no) before computing no-vig; incomplete markets → None (unit
  tests).

## 7. Odds fixture mapping

- Home/away names loaded EXPLICITLY via
  `select(Team.name).where(Team.id == fixture.home_team_id)` (and
  away) — no unordered SQL IN. Reversed-row-order regression test.

## 8. Odds quota cost

- `workers/tasks/collect.py`: for odds, `effective_cost =
  provider.estimate_cost(markets, regions)` reserved BEFORE the network
  call; `actual_cost` reconciled from `x-requests-last` via the ledger.
  Integration test: 4 markets × 1 region → 4 credits.

## 9. Quota reservation baseline

- `QuotaManager.reserve`: baseline = latest OBSERVED remaining;
  reservations since the observation accumulate in the Redis counter;
  post-INCR running total decides (insufficient → rollback; non-P0
  breaching the reserve floor → rollback). Test: observed remaining 4
  (limit 100) → exactly 2 P1 units + 2 P0 reserve units across 10
  concurrent callers.

## 10. Fail closed on quota init failure

- Discovery: real providers FAIL CLOSED if QuotaManager init fails
  (job FAILED, zero provider calls); MOCK may stay ungated. Redis client
  created by discovery is closed in `finally`. Integration test with
  unreachable Redis.

## 11. API-Football /teams/statistics

- Parser matches the actual v3 contract (response = SINGLE object, not a
  list); contract-faithful fixture; standings/injuries/lineups/
  completed-fixtures contracts unchanged. A bounded live smoke is
  allowed only with a local SPORTS_API_KEY (not run here).

## 12. Status API both-team + phase

- `_combined_status`: fresh only when BOTH required snapshots exist AND
  are fresh; one fresh + one missing → `unknown`; any stale → `stale`.
- `_fixture_phase` applies PREMATCH freshness TTLs when the fixture is
  inside the pre-match horizon.
- One-team-missing test: state is `unknown`, never `fresh`.

# Kept from M4.1 (unchanged good work)

scheduler wrapper, external-ID resolution, evidence linkage, coalescing
winner publishing real persisted refs, sequential job attempts,
completed-form inputs, DB-first reads.

---

# Verification (actually run on this machine)

- `uv run pytest -q -m "not integration"` → **254 passed**
- Integration suite (`sports_intel_test` + Redis db15) → **49 passed**
  (incl. M4.2 file: opportunity identity, T-window runtime, home+away
  concurrency, odds cost, partial-depleted quota, fail-closed, status
  one-team-missing, reversed mapping; alembic check + migration cycle)
- `uv run ruff check .` / `ruff format --check .` → clean
- `uv run mypy src` → **no issues in 87 source files** (strict)
- `docker compose config -q` (+telegram profile) → OK
- Secret scan → clean

# Known limitations (documented, intentional)

1. Live The Odds API + live /teams/statistics smokes require local
   credentials; contract tests cover normalization; never blocks
   acceptance.
2. Odds league-level batch endpoint remains a future optimization;
   event-specific calls only after strict resolution.
3. Pre-match scan enqueues per (collector, lock-key, phase, opportunity);
   no inline provider work inside the Beat task.

# Scope guard respected

No research, MatchContext, LLM, prediction, candidate ranking,
settlement, live in-play, Hetzner, Hermes.

---

# Suggested review order

1. `AGENTS.md`, this file, `docs/CURRENT_TASK.md`
2. Git diff `main..build/m4`
3. Key files:
   - `src/sports_intelligence/collectors/refresh.py` (opportunity ids)
   - `src/sports_intelligence/collectors/sports_collectors.py`
     (team-split persist, lineup refresh_due)
   - `src/sports_intelligence/collectors/framework.py` (refresh_due
     hook, now semantics)
   - `src/sports_intelligence/collectors/quota.py` (reservation
     baseline)
   - `src/sports_intelligence/providers/odds/{factory,parse}.py`
   - `src/sports_intelligence/workers/tasks/{pre_match,collect,sports}.py`
   - `src/sports_intelligence/api/routes/status.py`
   - `tests/integration/test_m4_collectors.py`

# Next action after PASS

Merge `build/m4` into `main`, tag `v0.5-m4`. Only then start M5 with
explicit user approval.