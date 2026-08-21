# Review Handoff

Use this file when handing the repository to ChatGPT, Kimi, another engineer, or a fresh coding-agent session.

Update it before every milestone review.

---

# Review status

**Ready for review:** YES  
**Development phase:** LOCAL DEVELOPMENT ONLY  
**Milestone:** M2 + M2.1 + M2.2 + M2.3 + M2.4 fixes — final M2.3 review
(PASS WITH ONE SMALL SAFETY FIX) addressed in M2.4; final state awaiting
review  
**Review target branch:** `build/m2`  
**Review target commits:** `bdb5ef3`, `3f62348`, `6625d7c`, `7e71ed0`,
`ac4188a` (M2); `ea9b4a8`, `1de60af`, `1dcd7cd` (M2.1);
`118aaab`, `dc5d2e0`, `e236f96` (M2.2);
`a157158` (M2.3: spec-compliant discovery idempotency identity);
`e4c38b6` (M2.4: bind discovery job identity to worker execution config) —
see Git section  
**CI status:** green on `build/m2` (unit, integration with isolated
Postgres/Redis, compose validation)  
**Previous review:** M2.3 → PASS WITH ONE SMALL SAFETY FIX; fix implemented in M2.4  
**Previous accepted state:** `main` = `25dda83` (M1 accepted, tag `v0.2-m1`)

---

# What changed since the last review

M2.4 (the one required safety fix from the final M2.3 review):

- **Discovery job identity now binds execution semantics.** The Celery
  task receives `job_id`, `fixture_date`, `expected_league_config_version`,
  `discovery_timezone` — the same values encoded in the idempotency
  identity at enqueue time. The worker loads the LeagueConfig and refuses
  to run when the loaded `version` differs from the expected one:
  deterministic `LeagueConfigVersionMismatchError`, zero provider
  requests, job marked FAILED. A full persisted job-input
  snapshot/outbox remains deferred to the orchestration milestone, but
  the worker can never execute a different semantic configuration than
  the one encoded in the job identity.
- **Timezone comes from the job**: `FixtureDiscoveryService` receives
  `discovery_timezone` from the task payload; mutable
  `settings.app_timezone` is no longer re-read at execution.
- Regression tests: enqueued v1 + worker sees v1 → executes and
  SUCCEEDS; config drifts to v2 before execution → 0 provider calls +
  FAILED; a job with `Europe/Warsaw` uses Warsaw even when current
  settings say `Europe/London`; existing MOCK discovery/idempotency
  tests stay green. No migration; no live smoke (quota preserved).

M2.3 (the one required fix from the final M2.2 review):

- **Discovery idempotency identity now matches spec `09`**:
  `discover:{provider}:{date}:v{league_config_version}:{timezone}`.
  The LeagueConfig `version` loaded from the configured YAML is the
  canonical identity mechanism (the enabled-league list never appears in
  the key); timezone is included because the provider request depends on
  it. Rule documented: semantic changes to `config/leagues.yaml` must
  bump `version`.
- Tests: duplicate POST with the same identity → no new job/enqueue;
  config-version change → new job + enqueue; timezone change → distinct
  identity (Warsaw vs London); FAILED-job retry keeps the same job UUID.
- Stale IMPLEMENTATION_STATUS strings synced (in-progress block, provider
  selected/verified, reviewer diff `main..build/m2`, raw-evidence
  description post-ADR-0009).

Earlier M2.2 fixes (PASS WITH FIXES verdict):

1. **Canonical request fingerprint** — deterministic
   `provider:endpoint_family:sorted(params)` including date AND timezone;
   stored in `provider_observations`; tests cover stability (same
   date+tz), tz-sensitivity (different tz → different fingerprint),
   parameter-order independence and provider distinction.
2. **FAILED-job requeue race** — CAS transition
   `transition_job_status_if(FAILED → PENDING)`; the HTTP layer re-reads
   the status after enqueue and can never downgrade RUNNING/SUCCEEDED;
   regression test simulates a worker status transition between
   `apply_async()` and the HTTP-side update (job remains RUNNING).
   Full outbox still M4.
3. **ORM metadata synchronized with migration 0003** — composite
   `ix_fixtures_league_kickoff` / `ix_fixtures_status_kickoff` declared in
   the ORM; stale single-column `index=True` removed (single kickoff
   index kept deliberately for date-only queries); schema drift verified
   with `alembic check` at head in integration tests/CI — no new upgrade
   operations.
4. **Hardened atomic identity race** — arbiter resolution no longer uses
   `scalar_one()` without fallback: bounded safe resolution (winner row →
   use; empty → fresh mapping SELECT; bounded retries); no orphan
   Team/Fixture; targeted synchronized-start test (6 participants on one
   team identity) proves exactly 1 mapping, exactly 1 Team, identical
   UUID for all callers.
5. **Worker initialization exception-safe** — engine/provider cleanup in
   `finally` with independent try/excepts; provider/config init failure
   marks the job FAILED when the DB is available and re-raises the
   original exception (integration + unit tests).

---

# What should the reviewer verify?

- provider JSON never leaks into domain/API schemas (DTO boundary);
- adapter retry classification and key handling (no key in logs/errors);
- discovery is fully idempotent (rows, mappings, raw payload dedup);
- N+1 guard test is meaningful (single request for N fixtures);
- migration 0002 applies/downgrades/reapplies on a fresh DB;
- no scope creep (no odds/research/MatchContext/prediction/Telegram);
- test-DB isolation guard still intact (dev DB protected);
- compose isolation unchanged (loopback ports, named volumes);
- M2.4: worker refuses to run on LeagueConfig version drift (0 provider
  calls, FAILED, deterministic exception) and uses the job's timezone,
  not the current settings.

---

# Commands claimed as passing

```bash
uv sync --frozen --dev
uv run pytest -q -m "not integration"        # 79 passed
make test-integration                        # 26 passed, isolated sports_intel_test
uv run ruff check .
uv run ruff format --check .
uv run mypy src                              # 51 source files, strict
docker compose config -q
docker compose up -d --build                 # api/postgres/redis/worker/beat
curl http://127.0.0.1:8000/health            # 200
curl http://127.0.0.1:8000/ready             # 200
curl -X POST http://127.0.0.1:8000/v1/jobs/discover -d '{"date":"2026-08-21"}'
curl "http://127.0.0.1:8000/v1/fixtures?date=2026-08-21"
```

CI runs unit + integration (isolated service containers) + compose
validation on every push; all three jobs green on `build/m2`.

Live evidence: bounded API-Football smokes passed in M2/M2.1 (383
fixtures in ONE request, 1 eligible league, idempotent re-runs, no key
in logs). M2.2 changed no HTTP contract, so the live smoke was NOT
repeated (quota preserved); MOCK-mode discovery through the full stack
was re-verified (idempotent, canonical fingerprint stored in
observations). M2.3/M2.4 changed only the job identity/payload, not the
provider HTTP contract — live smoke again NOT repeated (quota
preserved).

Reviewer must not assume tests passed based on status text alone.

---

# Known limitations

- Live verification is a single-date, single-league bounded smoke — not
  multi-day production usage.
- `job_attempts` rows are not written yet (M4 debt); only `jobs.status`
  is updated.
- QuotaManager/request ledger deferred to M4 (adapter captures
  rate-limit headers already).
- Odds/search/LLM protocols still typed as `dict[str, Any]` placeholders
  until their milestones.
- Docker Desktop multi-service bake bug (per-service build workaround
  documented).

---

# Files of highest relevance

- `src/sports_intelligence/providers/dto.py`
- `src/sports_intelligence/providers/sports/api_football.py`
- `src/sports_intelligence/providers/sports/mock.py`
- `src/sports_intelligence/pipelines/discover_fixtures.py`
- `src/sports_intelligence/db/repositories/discovery.py`
- `src/sports_intelligence/db/migrations/versions/0002_*.py`
- `src/sports_intelligence/api/routes/{fixtures,jobs}.py`
- `src/sports_intelligence/workers/tasks/sports.py`
- `src/sports_intelligence/core/league_config.py`
- `docs/adr/0007-api-football-first-provider.md`
- `docs/adr/0008-m2-schema-scope-and-upserts.md`
- `config/leagues.yaml`, `config/leagues.mock.yaml`
- `tests/unit/test_api_football_adapter.py`
- `tests/integration/test_fixture_discovery.py`
- Git diff `main..build/m2`

---

# Questions for reviewer

1. Are the DTO boundary and adapter design sufficient to swap providers
   later (Sportmonks)?
2. Is discovery idempotency watertight under concurrent jobs (upsert
   races)?
3. Does raw evidence persistence satisfy provenance requirements
   (spec 14) for future MatchContext references?
4. Are there quota pitfalls in the batch-first flow?
5. Is the next milestone safe to start?

---

# Reviewer output expected

```text
VERDICT: PASS / PASS WITH FIXES / FAIL

P0 critical
P1 high
P2 medium
P3 low

Tests independently run:
...

Required fixes before next milestone:
...

Safe to begin next milestone:
YES / NO
```
