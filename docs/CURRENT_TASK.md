# Current Task

**Status:** COMPLETE (M4.1) — awaiting independent review
**Milestone:** M4.1 — corrective implementation after M4 review **FAIL**
**Owner/agent:** ox-alpha (OpenCode), continuing DeepSeek V4 Pro work
**Started at:** 2026-08-24
**Last updated:** 2026-08-24

---

# Task

Independent review of M4 returned **FAIL — not mergeable**. Core
automatic/live-data paths had correctness and data-integrity failures.
M4.1 on `build/m4` implements the 14 required fixes:

1. Scheduled discovery execution via `sports.schedule_discovery(slot)`
   wrapper (distinct morning/refresh jobs, full immutable tuple, M2
   config-version safety preserved).
2. Real provider data in real-provider paths (extended
   `SportsDataProvider` boundary; ApiFootballProvider NEVER returns
   MOCK payloads; external-ID resolution via `provider_entity_ids`).
3. Team-specific availability/lineup persistence (one request per
   fixture, one snapshot PER team, never merged).
4. Bounded, state-aware lineup windows (NOT_YET_PUBLISHED / CONFIRMED /
   UNSUPPORTED / PROVIDER_ERROR; no started-fixture polling; T-120
   unconfirmed does not block T-60; confirmed stops polling; Warsaw
   calendar-day → UTC boundaries; PREMATCH freshness applied).
5. Coalescing correctness (lock is a budget boundary — no fetch-anyway;
   waiters reuse the winner's REAL persisted snapshot UUID; no second
   snapshot/ledger row; freshness hit returns real id).
6. QuotaManager pct-vs-actual-limit semantics (100/500/7500 tested),
   CONSERVE pauses P3, CRITICAL pauses P2/P3, RESERVE_ONLY protects P0,
   CRITICAL reachable, concurrency-safe Redis reservation, estimated
   cost support.
7. Provider-specific quota headers (API-Football daily+minute; Odds
   remaining/used/last-as-cost).
8. Request-ledger telemetry (started_at before request, duration incl.
   HTTP, status code, error class, headers, cost; failures visible).
9. The Odds API event/sport-key mapping (strict team+kickoff
   resolution, ambiguity = error, persisted mapping, provider event id
   in URL — never internal UUID).
10. Raw evidence linkage (content-deduped raw payloads + observation
    rows; snapshots carry payload_id).
11. job_attempts sequential numbering (1, 2, 3…) + real worker PID.
12. Pre-match scanner dispatches collector jobs through the queue with
    job/attempt recording and exception-safe resource cleanup.
13. Form inputs from normalized completed-fixture results (deterministic
    W/D/L, no LLM, no settlement logic).
14. Status API correctness (real degradation mode, both-team freshness,
    publication-aware lineup availability, Priority.P0 enum, zero
    external calls on reads).

# Acceptance tests (M4.1) — run

- actual scheduled 09:00 wrapper execution (eager, creates Job +
  enqueues full tuple);
- distinct 13:00 refresh job (not suppressed by morning);
- Warsaw/DST-local-midnight planner boundaries; already-started fixture
  → zero pre-match calls;
- API-Football sentinel contract tests for EVERY M4 sports category
  (standings/team stats/availability/lineups/completed fixtures) with
  MockTransport; no MOCK payload under api_football;
- 10 concurrent equivalent collector calls → exactly 1 provider call /
  1 snapshot / 1 ledger row / same persisted UUID;
- coalescing waiter receives the winner's real UUID; freshness hit
  returns the real existing snapshot id;
- quota thresholds for limits 100 / 500 / 7500 (percent-of-limit);
- concurrent quota reservation (10 workers → exactly 4 of 10 succeed
  atomically against usable budget);
- correct API-Football and The Odds API header semantics
  (x-requests-last = cost, not minute remaining);
- The Odds API event/sport-key mapping + no-match + ambiguity errors +
  exact URL path assertion;
- Odds API estimated credit-cost protection;
- two team-specific availability snapshots from one fixture response;
- T-120 unconfirmed → T-60 refresh allowed → confirmed stops T-20;
- raw evidence/observation linkage (payload_id on snapshots);
- job attempt #1 then #2 on rerun (sequential numbering);
- DB-first GET/Telegram reads → zero external calls;
- migration fresh apply/downgrade/reapply + alembic check (head 0005);
- full Ruff / format / strict mypy (86 files) / Compose / secret scan.

# Verification (actually run)

- `uv run pytest -q -m "not integration"` → **242 passed**
- integration suite (isolated `sports_intel_test` + Redis db15) →
  **41 passed** (incl. new M4.1 file + migration/alembic check)
- `uv run ruff check .` / `ruff format --check .` → clean
- `uv run mypy src` → **no issues in 86 source files** (strict)
- `docker compose config -q` (+telegram profile) → OK
- Secret scan → clean

# Known limitations

- Form inputs persist deterministic completed-result history; upstream
  prediction/form features remain out of scope (M7+).
- The Odds API live path is contract-tested; live verification only if
  credentials configured (never blocks acceptance).
- Pre-match scanner enqueues collector jobs; per-collector queue
  fan-out and cross-factory batch odds remain future optimizations.

---

# Completion

- Status: COMPLETE on `build/m4`. No merge to main; M5 not started.
- Review verdict to record: M4 → **FAIL**; M4.1 awaiting re-review.
