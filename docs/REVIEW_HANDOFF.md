# Review Handoff

Use this file when handing the repository to ChatGPT, Kimi, another
engineer, or a fresh coding-agent session.

Update it before every milestone review.

---

# Review status

**Ready for review:** YES (Milestone M5.3 runtime correctness pass completed, fully tested)  
**Development phase:** LOCAL DEVELOPMENT ONLY  
**Milestone:** M5.3 — Web Research Runtime Correctness Pass  
**Review target branch:** `build/m5`  
**Previous reviewed remote HEAD:** `42f2277d8f7dde2f0b315c259f22c210da05cefb` (M5.2)  
**Previous accepted state:** `main` = `2e4683a` (`v0.5-m4` accepted M4 merge)  
**Previous review verdicts:**
- M5 → FAIL (`6c52b1f1df85163b0aeef1f3a16d223bd3296cff`)
- M5.1 → FAIL (`30dd97a4a948f906d6e690b9acbd14550c75dec8`)
- M5.2 → FAIL (`42f2277d8f7dde2f0b315c259f22c210da05cefb`)
- M5.3 → awaiting independent review  
**Review scope:** diff `main..build/m5` or diff `42f2277..build/m5`

---

# Milestone M5.3 Runtime Correctness Fixes

Following independent review verdict `M5.2 = FAIL`, M5.3 implemented five targeted runtime correctness fixes without redesigning the accepted search provider abstraction, per-attempt quota accounting, or database models:

### 1. PROVIDER_ERROR Retry Job Identity & Scanner Lifecycle
- **Defect fixed**: `ResearchCollector.latest_snapshot()` previously returned `(None, None)` for `PROVIDER_ERROR` runs. The Celery collector task finished with status `SUCCEEDED`. On subsequent scanner runs, the scanner generated `due:missing`, matched the existing `SUCCEEDED` job, and skipped enqueuing any retry — permanently stalling retries.
- **Implementation**:
  - Replaced the `(None, None)` hack in `ResearchCollector.latest_snapshot()` with true `(captured_at, run_id)`.
  - Added `latest_run_info(session, fixture_id, error_retry_ttl_seconds)` returning `ResearchRunInfo(captured_at, run_id, status, retry_due_at)`.
  - Added `refresh_due()` to `ResearchCollector` respecting `research_provider_error_retry_seconds` (default: 900s = 15m).
  - Updated `refresh_opportunity_suffix()` in `refresh.py` to generate deterministic `error_due:<epoch>` keys (`epoch = latest_captured_at + error_retry_ttl`) for `PROVIDER_ERROR` runs (and `quota_due:<epoch>` for `QUOTA_DENIED`).
  - Pre-match scanner in `pre_match.py` queries `collector_refresh_due()`: skips enqueuing before retry is due; creates a new deterministic opportunity job once retry is due; de-duplicates multiple scans within the same opportunity; opens a subsequent retry generation upon a second error; and resumes normal 6h TTL upon successful collection.
- **Verification**: `test_provider_error_scanner_retry_job_lifecycle` in `tests/integration/test_m5_research.py` verifies all six phases of this lifecycle end-to-end. Unit tests `test_provider_error_snapshot_and_run_info`, `test_collector_refresh_due_provider_error`, and `test_refresh_opportunity_suffix_error_and_quota` verify component behavior.

### 2. Explicit QUOTA_DENIED State
- **Defect fixed**: Quota denial previously threw a generic exception mapped to `PROVIDER_ERROR`, incorrectly recording provider failure telemetry when no external HTTP call was ever made.
- **Implementation**:
  - Added `ResearchState.QUOTA_DENIED` enum to `core/phases.py`.
  - Refactored `ResearchCollector.fetch()` to track `quota_denied` and `quota_denial_reason` explicitly without raising fake provider error exceptions.
  - When quota is denied before the first request: 0 provider calls, 0 ledger rows, status = `QUOTA_DENIED`, details record reason, planned queries, and `queries_succeeded = 0`.
  - When quota is denied mid-run: preserves all previously retrieved documents and claims with status = `QUOTA_DENIED` and `partial_failure = True`.
- **Verification**: `test_quota_denied_before_first_request_zero_provider_calls` and `test_quota_denied_after_first_query_retains_documents` in `tests/unit/collectors/test_research_collector.py`.

### 3. Failure Observation Timestamps & Anti-Leakage
- **Defect fixed**: `ResearchRun.captured_at` was initialized before external calls, potentially backdating failure timestamps and causing temporal leakage in historical replay queries.
- **Implementation**:
  - `ResearchCollector` tracks `latest_attempt_observed_at` using clock timestamps after every external HTTP attempt.
  - On failure or partial failure, `ResearchRun.captured_at` receives the exact post-failure observation timestamp (T2 / T3).
  - Retrieved documents retain their own specific `retrieved_at` timestamp (T1).
  - Historical queries (`as_of`) between document retrieval (T1) and run failure observation (T3) do not reveal the later failed run.
- **Verification**: `test_failure_observation_timestamp_reflects_actual_failure_time` (unit) and `test_partial_provider_failure_persists_provider_error` (integration) verify observation timestamp precision and historical `as_of` anti-leakage.

### 4. Respect Retry-After Header for 429 Rate Limits
- **Defect fixed**: Collector retry logic did not inspect or respect provider `Retry-After` headers, risking premature retry exhaustion or unbounded sleeps.
- **Implementation**:
  - Added `compute_retry_delay(exc, attempt, max_retry_after_seconds)` in `research_collector.py`.
  - When retrying `ProviderRateLimitError` (HTTP 429), parses `Retry-After` header value and caps it at `research_max_retry_after_seconds` (configurable in `Settings`, default 30s).
  - Falls back to deterministic exponential backoff (`0.1 * 2^attempt`) on invalid, negative, or missing headers.
  - Injected sleeper and clock support in `ResearchCollector` ensures test execution is 100% deterministic and never sleeps.
- **Verification**: Parameterized test `test_compute_retry_delay_429` covering small values, values capped at max, invalid headers, negative values, and non-429 exceptions.

### 5. Capability-Aware Fixture Freshness Status
- **Defect fixed**: `GET /v1/fixtures/{fixture_id}/status` reported research freshness as `"unknown"` when the research capability was globally disabled and no run existed.
- **Implementation**:
  - Extended `CategoryState` Literal in `schemas/status.py` to include `"disabled"`.
  - In `routes/status.py`, `_fixture_freshness` checks `settings.research_capability_enabled`. If False and no run exists, sets research status to `"disabled"`.
- **Verification**: `test_fixture_status_research_disabled_when_capability_disabled` in `tests/integration/test_m5_research.py`.

---

# Verification Evidence (All Passing Locally)

- **Unit tests**: `uv run pytest -q -m "not integration"` → **318 passed, 76 deselected in 5.30s**
- **Integration tests**: `TEST_DATABASE_URL="postgresql+asyncpg://sports:sports_dev_password@localhost:5433/sports_intel_test" TEST_REDIS_URL="redis://localhost:6380/15" uv run pytest -q -m integration` → **76 passed, 318 deselected in 17.16s**
- **Full test suite**: `uv run pytest -q` → **394 passed in 16.24s**
- **Linter**: `uv run ruff check .` → **clean (All checks passed!)**
- **Formatter**: `uv run ruff format --check .` → **clean (157 files already formatted)**
- **Type checker**: `uv run mypy src` → **clean (Success: no issues found in 104 source files)**
- **Alembic check**: `uv run alembic check` → **clean (No new upgrade operations detected)**
- **Docker Compose**: `docker compose config -q` and `docker compose --profile telegram config -q` (+dev) → **clean (OK)**
- **Secret scan**: clean (zero credentials in code, diff, or Git).
- **Offline safety**: Zero live external search API calls during test suite execution.

---

# Instructions for Independent Reviewer

1. Inspect git diff against previous reviewed HEAD: `git diff 42f2277d8f7dde2f0b315c259f22c210da05cefb..build/m5`.
2. Inspect `ResearchCollector.latest_snapshot()`, `latest_run_info()`, and `refresh_opportunity_suffix()`.
3. Verify `QUOTA_DENIED` status handling and diagnostics in `ResearchCollector.fetch()`.
4. Inspect `compute_retry_delay()` in `research_collector.py`.
5. Run full test suite: `uv run pytest -q`.
6. Run `uv run ruff check .` and `uv run mypy src`.
7. Run `uv run alembic check`.
8. Do NOT merge `build/m5` into `main`.
9. Do NOT start Milestone M6.