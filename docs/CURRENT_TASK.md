# Current Task

**Task**: Implement focused M5.3 runtime correctness pass on branch `build/m5`  
**Status**: COMPLETE (awaiting independent review)

## Review Verdicts
- M5 → FAIL
- M5.1 → FAIL
- M5.2 → FAIL (reviewed remote HEAD: `42f2277d8f7dde2f0b315c259f22c210da05cefb`)
- M5.3 → awaiting independent review

## Requirements Implemented

1. **Fix PROVIDER_ERROR retry job identity**
   - Removed `(None, None)` hack from `ResearchCollector.latest_snapshot()`.
   - Exposed state-aware refresh info via `latest_run_info()` and `refresh_due()`.
   - Updated `refresh_opportunity_suffix()` to produce stable `error_due:<epoch>` where epoch = `latest_captured_at + research_provider_error_retry_seconds` (configurable, default 900s).
   - Ensured scanner creates no job before error retry due, creates new job after retry due, de-duplicates scans inside same opportunity, opens later retry generation on second error, and resumes normal 6h TTL on success.
2. **Distinguish quota denial from provider failure**
   - Added `ResearchState.QUOTA_DENIED` enum.
   - Refactored `ResearchCollector.fetch()` to track `quota_denied` explicitly without fake provider error exceptions.
   - Quota denial before first request yields 0 provider calls, 0 ledger rows, status `QUOTA_DENIED`, and reason in details.
   - Partial quota denial preserves retrieved documents and claims with status `QUOTA_DENIED`.
3. **Fix research failure observation timestamp**
   - Clock-based observation timestamp tracks every attempt.
   - Failure and partial failure capture the exact observation timestamp of the failed attempt on `ResearchRun.captured_at`.
   - Documents keep their own `retrieved_at`.
   - Historical `as_of` prior to failed attempt observation timestamp does not reveal the later run.
4. **Respect Retry-After for 429**
   - Implemented `compute_retry_delay()` respecting `Retry-After` header on `ProviderRateLimitError`, bounded by `research_max_retry_after_seconds` (default 30s).
   - Invalid, missing, or negative values fallback to deterministic exponential backoff.
   - `ResearchCollector` supports injectable `sleeper` and `clock` for deterministic offline testing.
5. **Fix current fixture status when research is disabled**
   - Updated `GET /v1/fixtures/{fixture_id}/status` to report research state as `"disabled"` when `research_capability_enabled` is False and no run exists.
   - Extended `CategoryState` Literal to include `"disabled"`.
6. **Acceptance and regression tests**
   - Unit tests for all M5.3 behaviors in `tests/unit/collectors/test_research_collector.py`.
   - Integration tests in `tests/integration/test_m5_research.py`.
   - Full suite passes: 394 passed (318 unit, 76 integration).
   - Zero live external calls in tests.
