# Review Handoff

Use this file when handing the repository to ChatGPT, Kimi, another
engineer, or a fresh coding-agent session.

Update it before every milestone review.

---

# Review status

**Ready for review:** YES  
**Development phase:** LOCAL DEVELOPMENT ONLY  
**Milestone:** M4.3 — focused correctness pass after M4.2 review **FAIL**  
**Review target branch:** `build/m4` (NOT merged to main)  
**Previous accepted state:** `main` = `7d23c9d` (M3 accepted via PR #5)  
**Review scope:** diff `main..build/m4` (M4 + M4.1 + M4.2 + M4.3)

---

# Independent review history

- M4 → **FAIL**; M4.1 → **FAIL**; M4.2 → **FAIL** (focused correctness
  blockers); M4.3 implemented on `build/m4`, awaiting independent review.

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