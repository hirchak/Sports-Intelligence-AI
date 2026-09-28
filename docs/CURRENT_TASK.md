# Current Task

**Status:** COMPLETE (M4.4) — awaiting independent review
**Milestone:** M4.4 — focused correctness fixes (4 items) after M4.3 review **FAIL**
**Owner/agent:** ox-alpha (OpenCode)
**Started at:** 2026-08-28
**Last updated:** 2026-08-28

---

# Task

Independent review of M4.3 returned **FAIL** with four focused
correctness fixes. M4.4 on `build/m4` implements exactly those four
items — working M4/M4.1/M4.2/M4.3 components are NOT redesigned.

1. **Correct API-Football /teams/statistics normalization**:
   - Real v3 shape: `fixtures.{played,wins,draws,loses}.{home,away,total}`
     (note `loses` — normalized to `losses`);
   - `goals.for.total.{home,away,total}` and
     `goals.against.total.{home,away,total}` nested extraction;
   - `clean_sheet.{home,away,total}` and
     `failed_to_score.{home,away,total}` flat splits;
   - Normalizes played/wins/draws/losses/goals_for/goals_against/
     clean_sheets/failed_to_score/form; missing values remain None —
     never fabricated zero;
   - SENTINEL_TEAM_STATS updated to a sanitized contract-faithful
     payload; every metric asserted (esp. losses, goals_for,
     goals_against) + a missing-values test.
2. **Pin season identity end-to-end**:
   - `PreMatchDecision.season_id` added (from Fixture.season_id);
   - `execute_plan()` passes the fixture's actual season_id to
     standings/team_stats (never None);
   - `_season_number(league_id)` (active=True LIMIT 1) replaced with an
     exact Season resolver: fetches the exact Season, verifies it
     belongs to the expected league, parses the year deterministically,
     refuses missing/mismatched/ambiguous identity;
   - standings/team_stats lock identity, freshness lookup (`StandingsCollector.latest_snapshot` and `TeamStatisticsCollector.latest_snapshot` both filter by exact season_id), provider
     `season=` parameter and persisted snapshot `season_id` all use the
     exact season;
   - Integration regression: same league with season A=2025 and B=2026;
     fixture on B → provider receives 2026; snapshot persisted with the
     season-B uuid; a fresh season-A snapshot never satisfies season-B
     freshness; A/B lock identities never collide.
3. **Stable TTL refresh opportunity**:
   - no snapshot → `due:missing`;
   - snapshot fresh → the scanner creates NO collector job (cheap
     freshness check before `create_or_get_job()`);
   - snapshot stale → `due:<captured_at + effective_ttl>` — STABLE
     until a new successful snapshot persists (never `due:now`);
   - framework freshness remains the race-safe double-check;
   - Acceptance flow regression: T0+20 fresh → no job; T0+31 stale →
     job A; broker fails → A FAILED; T0+35 → SAME uuid A requeued;
     T0+40 A RUNNING → no duplicate; successful snapshot at T0+41 →
     next scan fresh → no job.
   - Lineup t120/t60/t20 logic unchanged.
4. **Quota observations at response observation time**:
   - `QuotaBucket.observed_at` now derives from `finished_at` (the
     response observation moment), never request `started_at`;
   - Overlap/order regression: two overlapping requests — the LATER
     response becomes the authoritative bucket/generation even if it
     started earlier.

# Verification (actually run)

- `uv run pytest -q -m "not integration"` → **264 passed**
- integration suite (`sports_intel_test` + Redis db15) → **59 passed**
  (incl. new M4.4 tests: two-season isolation, TTL stable opportunity
  acceptance flow, response-time observation ordering, season pinning)
- `uv run ruff check .` / `ruff format --check .` → clean
- `uv run mypy src` → **no issues in 87 source files** (strict)
- `docker compose config -q` (+telegram profile) → OK
- Secret scan → clean

# Known limitations

- No schema migration needed (M4.4 §"no schema migration unless
  necessary").
- No broad live API smoke; a bounded /teams/statistics smoke is allowed
  only with local credentials (not run — no key).
- Local integration runs flush Redis first (reservation counters), as in
  M4.3.

---

# Completion

- Status: COMPLETE on `build/m4`. No merge to main; M5 not started.
- Review verdict to record: M4 → FAIL; M4.1 → FAIL; M4.2 → FAIL;
  M4.3 → FAIL; M4.4 awaiting independent review.