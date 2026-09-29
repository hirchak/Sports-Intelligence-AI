# Review Handoff

Use this file when handing the repository to ChatGPT, Kimi, another
engineer, or a fresh coding-agent session.

Update it before every milestone review.

---

# Review status

**Ready for review:** ACCEPTED (Milestone M4 passed independent review)  
**Development phase:** LOCAL DEVELOPMENT ONLY  
**Milestone:** M4 (M4.4 accepted) — merging to main, tagging v0.5-m4  
**Review target branch:** `build/m4` (merging to main)  
**Review target commit:** `0d0cd4a631c067a29c21ce584e806a47c534dc82` — M4 accepted HEAD  
**Previous accepted state:** `main` = `7d23c9d` (M3 accepted via PR #5)  
**Review scope:** diff `main..build/m4` (M4 + M4.1 + M4.2 + M4.3 + M4.4)

---

# Independent review history

- M4 → **FAIL**; M4.1 → **FAIL**; M4.2 → **FAIL**; M4.3 → **FAIL**;
  M4.4 → **PASS / ACCEPTED** (accepted remote HEAD: `0d0cd4a631c067a29c21ce584e806a47c534dc82`).

# What changed in M4.4

## 1. API-Football /teams/statistics normalization

- Real v3 shape: `fixtures.{played,wins,draws,loses}.{home,away,total}`
  (provider spells `loses`; normalized to `losses`);
  `goals.for.total.{home,away,total}` / `goals.against.total.{...}`;
  `clean_sheet.{home,away,total}`; `failed_to_score.{home,away,total}`.
- Metrics: played/wins/draws/losses/goals_for/goals_against/
  clean_sheets/failed_to_score/form; missing → None, never zero.
- Contract-faithful SENTINEL_TEAM_STATS; every metric asserted +
  missing-values test.

## 2. Season identity pinned end-to-end

- `PreMatchDecision.season_id` (from Fixture.season_id) flows through
  `execute_plan()` into standings/team_stats inputs.
- Exact Season resolver replaces the old `active=True LIMIT 1` helper:
  fetches the exact Season row, verifies league ownership, parses the
  year deterministically, refuses missing/mismatched identity.
- Lock identity, freshness lookup (`StandingsCollector.latest_snapshot` and
  `TeamStatisticsCollector.latest_snapshot` both filter by exact season_id,
  returning (None, None) when season_id is None), provider `season=` and
  persisted snapshot `season_id` all use the exact season.
- Fixed `TeamStatisticsCollector.persist()` to omit invalid `source_fingerprint`
  argument matching `TeamStatisticsSnapshot` schema.
- Two-season same-league regression: fixture on season B → provider
  season=2026, snapshot pinned to B uuid, fresh A never satisfies B,
  A/B lock keys distinct.

## 3. Stable TTL refresh opportunity

- no snapshot → `due:missing`; fresh → scanner creates NO job (cheap
  freshness check before create_or_get_job); stale →
  `due:<captured+TTL>` stable until a new snapshot.
- Framework freshness remains the race-safe double-check.
- Acceptance flow regression: T0+20 no job; T0+31 job A; broker fail →
  A FAILED; T0+35 same uuid requeued; T0+40 RUNNING no duplicate;
  T0+41 new snapshot → next scan no job.
- Lineup windows unchanged.

## 4. Quota observations at response time

- `QuotaBucket.observed_at` = `finished_at` (response observation
  moment), never request start.
- Overlap/order regression: later response becomes the authoritative
  generation.

# Verification

- unit → **265 passed**; integration → **59 passed** (isolated
  `sports_intel_test` + Redis db15, incl. alembic check)
- ruff/format clean; strict mypy clean (87 files); compose OK;
  secrets clean; no schema migration needed.

---

# What changed in M4.3 (per FAIL item)

## 1. Odds capability gating (no silent MOCK)

- `build_odds_provider`: APP_ENV=mock + empty/mock → MockOddsProvider;
  sandbox/live_local + empty → **None** (DISABLED); sandbox/live_local +
  mock → requires `odds_allow_mock_override` else ProviderConfigError.
- `Settings.odds_capability_enabled` drives the planner: the pre-match
  scanner never enqueues odds when disabled (planned=1, created=0,
  enqueued=0); `sports.collect` fails closed for odds jobs when
  disabled.
- Regression: live_local + api_football + odds_provider="" → zero odds
  jobs, zero OddsSnapshotSet rows.

## 2. Provider market translation

- `OddsProvider.request_markets()` — provider owns the translation from
  internal product markets to HTTP market keys; guarantees
  `alternate_totals` is requested alongside `totals` (exact O/U 1.5/2.5).
- Cost estimation (`collect.py`, `OddsCollector`) uses the ACTUAL
  provider market set: 5 markets × 1 region → 5 credits reserved before
  the network call.
- Contract test captures the outgoing `markets=` query and asserts
  alternate_totals presence.

## 3. Fixture-level lineup refresh

- `LineupCollector.refresh_due` aggregates BOTH fixture teams' latest
  publication states: CONFIRMED stops polling only when both sides are
  CONFIRMED; home CONFIRMED + away NOT_YET_PUBLISHED still refreshes the
  next window; the requesting team_id in the job payload never
  suppresses a needed later window.
- Scenario integration test covers the full T20 flow.

## 4. TTL refresh-opportunity identity

- Opportunity = actual due generation: `latest_captured_at + effective
  TTL` while fresh; `now` once stale; `due:missing` (stable) when no
  snapshot exists yet.
- Counterexample regression: job created while fresh, time advances
  past the TTL inside the old global bucket → a new opportunity is
  created (never suppressed by an unrelated bucket boundary).
- Framework freshness remains the final safety check.

## 5. Quota observation generations

- Reservation counters are keyed to the observation GENERATION
  (observed_at of the authoritative bucket); a newer observation starts
  a fresh counter — reservations are "since this observation".
- Regression: observed 100 → reserve 4 → new observation 96 → reserve 4
  behaves as 96→92, not 96−4−4; concurrent reservations after a new
  observation counted against the new generation.

## 6. The Odds API quota limit

- `parse_quota_headers("theoddsapi")` infers the daily limit from
  `x-requests-used + x-requests-remaining` (8 + 492 → 500);
  `x-requests-last` remains the actual last-call cost; degradation
  percentages operate on the inferred 500-credit allowance.
- Provider semantics documented in adapter/tests.

## 7. FAILED job requeue

- Collector jobs reuse the SAME job UUID within the same refresh
  opportunity; a stranded FAILED job is re-enqueued via CAS
  (FAILED → PENDING); RUNNING/SUCCEEDED never downgraded. Same logic
  applied to scheduled discovery (`_run_schedule`).
- Tests: broker-failure → job FAILED → next scan same opportunity
  re-enqueues the same uuid; RUNNING job untouched by a later scan.

## 8. Failure telemetry

- `ProviderError.quota_headers` (safe rate-limit headers only) added;
  API-Football 401/403/429/5xx and The Odds API 429/5xx populate it
  plus `status_code`; framework passes them into `record_failure`.
- Ledger test: 429 → status_code 429 + daily_remaining from safe
  headers; no auth headers ever persisted.

## 9. Scanner observability

- `_dispatch_decision` returns planned / jobs_created / jobs_reused /
  jobs_enqueued (+ per-category breakdown); reused jobs are never
  reported as newly enqueued; Redis cleanup is finally-safe on enqueue
  errors (test asserts counters after dedupe and requeue).

# Kept unchanged (good M4.1/M4.2 work)

scheduler wrapper, external-ID resolution, evidence linkage, coalescing
winner publishing real persisted refs, sequential job attempts,
completed-form inputs, DB-first reads, team-split persistence,
no-vig completeness.

---

# Verification (actually run on this machine)

- `uv run pytest -q -m "not integration"` → **262 passed**
- Integration suite (`sports_intel_test` + Redis db15) → **56 passed**
  (incl. M4.3 file; alembic check + migration cycle; a one-time Redis
  flush precedes the local run — counters live in Redis)
- `uv run ruff check .` / `ruff format --check .` → clean
- `uv run mypy src` → **no issues in 87 source files** (strict)
- `docker compose config -q` (+telegram profile) → OK
- Secret scan → clean

# Known limitations (documented, intentional)

1. Live provider smokes require local credentials; contract tests cover
   normalization + failure telemetry; never blocks acceptance.
2. Local integration runs flush Redis first (`make test-integration`)
   so reservation counters never leak between runs; CI uses fresh
   containers.

# Scope guard respected

No research, MatchContext, LLM, prediction, candidate ranking,
settlement, live in-play, Hetzner, Hermes.

---

# Suggested review order

1. `AGENTS.md`, this file, `docs/CURRENT_TASK.md`
2. Git diff `main..build/m4`
3. Key files:
   - `src/sports_intelligence/providers/odds/factory.py` (gating,
     request_markets, failure headers)
   - `src/sports_intelligence/collectors/refresh.py` (due generation)
   - `src/sports_intelligence/collectors/quota.py` (observation
     generations, inferred odds limit)
   - `src/sports_intelligence/collectors/sports_collectors.py`
     (fixture-level lineup refresh)
   - `src/sports_intelligence/workers/tasks/pre_match.py`
     (gating, counters, FAILED requeue)
   - `src/sports_intelligence/workers/tasks/scheduling.py` (FAILED
     requeue)
   - `tests/integration/test_m4_collectors.py`, `tests/unit/test_odds_gating.py`

# Next action after PASS

Merge `build/m4` into `main`, tag `v0.5-m4`. Only then start M5 with
explicit user approval.