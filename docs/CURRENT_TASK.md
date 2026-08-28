# Current Task

**Status:** COMPLETE (M4.3) — awaiting independent review
**Milestone:** M4.3 — focused correctness pass after M4.2 review **FAIL**
**Owner/agent:** ox-alpha (OpenCode)
**Started at:** 2026-08-24
**Last updated:** 2026-08-24

---

# Task

Independent review of M4.2 returned **FAIL** (focused correctness
blockers). M4.3 on `build/m4` implements the fixes WITHOUT redesigning
working M4 components:

1. **No silent MOCK odds in non-mock environments**: `build_odds_provider`
   returns MockOddsProvider ONLY in APP_ENV=mock (or with the explicit
   `ODDS_ALLOW_MOCK_OVERRIDE` flag); in sandbox/live_local with an empty
   ODDS_PROVIDER the odds capability is DISABLED (provider is None);
   ODDS_PROVIDER=mock in a non-mock env without the override is REJECTED
   (ProviderConfigError). The pre-match planner skips odds when the
   capability is disabled; `sports.collect` refuses odds jobs when
   disabled (fail closed). Regression test: live_local +
   sports_provider=api_football + odds_provider="" → zero odds jobs and
   zero OddsSnapshotSet rows.
2. **Provider market translation**: the provider owns the translation
   from internal market requirements to actual HTTP market keys.
   `OddsProvider.request_markets()` guarantees the outgoing `markets=`
   parameter contains `h2h, double_chance, totals, alternate_totals,
   btts` (alternate_totals needed for exact O/U 1.5/2.5 lines). Cost
   estimation uses the ACTUAL provider market set (5 markets × 1 region
   → 5 credits). Contract test asserts alternate_totals is in the
   outgoing query.
3. **Fixture-level lineup refresh**: CONFIRMED stops polling only when
   BOTH actual fixture teams have confirmed latest lineups. Scenario
   test: home CONFIRMED + away NOT_YET_PUBLISHED → next window still
   refreshes; both CONFIRMED → zero provider calls.
4. **TTL refresh-opportunity identity**: opportunity = actual due
   generation — `latest_captured_at + effective TTL` while fresh, `now`
   once stale (never an unrelated global bucket); no snapshot yet →
   stable `due:missing` opportunity. Counterexample regression: job
   created while fresh, time advances past TTL inside the old bucket →
   new opportunity created.
5. **Quota observation generations**: reservation counters are keyed to
   the observation GENERATION (observed_at of the authoritative bucket).
   A newer observation starts a fresh counter — reservations are
   "since this observation", never re-subtracted against a moving
   baseline. Regression: observed 100 → reserve 4 → new observation 96 →
   reserve 4 behaves as 96→92 (not 96−4−4). Concurrency-safe.
6. **The Odds API quota limit**: limit inferred from
   `x-requests-used + x-requests-remaining` (used=8, remaining=492 →
   limit 500); degradation percentages operate on the actual 500-credit
   allowance; `x-requests-last` remains the actual last-call cost.
7. **FAILED job requeue**: collector jobs reuse the SAME job UUID within
   the same refresh opportunity but are re-enqueued after FAILED via CAS
   (FAILED → PENDING); RUNNING/SUCCEEDED are never downgraded. Applied
   to scheduled discovery too (stranded-FAILED re-enqueue).
8. **Failure telemetry**: API-Football 401/403/429/5xx and The Odds API
   429/5xx carry `status_code` AND safe quota headers
   (`ProviderError.quota_headers` — never auth headers/API keys); the
   framework passes them to `record_failure`; ledger test for 429.
9. **Scanner observability**: counters distinguish `planned /
   jobs_created / jobs_reused / jobs_enqueued` (reused jobs are never
   reported as newly enqueued); Redis cleanup is finally-safe on
   enqueue errors.

# Acceptance tests (M4.3) — run

- live_local + no odds credentials → zero odds jobs + zero mock
  persistence (integration);
- outgoing The Odds API query contains alternate_totals (contract test);
- 5 provider markets × 1 region estimated-cost test (unit);
- partial home-confirmed / away-unpublished → later window still
  refreshes; both confirmed → stops (integration);
- TTL stale-inside-old-bucket regression (unit);
- quota observation-generation regression (integration);
- Odds headers used=8, remaining=492 → limit 500 (unit);
- concurrent reservations after a new observation (integration);
- FAILED collector same-opportunity retry (same uuid) (integration);
- broker retry does not downgrade RUNNING/SUCCEEDED (integration);
- API-Football 429 ledger has status 429 and safe rate headers
  (integration);
- full unit + integration suite; migrations + alembic check;
  Ruff/format; strict mypy (87 files); Compose; secret scan.

# Verification (actually run)

- `uv run pytest -q -m "not integration"` → **262 passed**
- integration suite (`sports_intel_test` + Redis db15) → **56 passed**
- `uv run ruff check .` / `ruff format --check .` → clean
- `uv run mypy src` → **no issues in 87 source files** (strict)
- `docker compose config -q` (+telegram profile) → OK
- Secret scan → clean

# Known limitations

- Live The Odds API / API-Football smokes require local credentials
  (not run; contract tests cover normalization and failure telemetry).
- Local integration runs need a one-time Redis flush (added to
  `make test-integration`) because quota reservation counters live in
  Redis; CI uses fresh containers.

---

# Completion

- Status: COMPLETE on `build/m4`. No merge to main; M5 not started.
- Review verdict to record: M4 → FAIL; M4.1 → FAIL; M4.2 → FAIL; M4.3
  awaiting independent review.