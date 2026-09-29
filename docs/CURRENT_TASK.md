# Current Task

**Task**: Implement focused M5.2 correctness fixes on branch `build/m5`
**Status**: COMPLETE

## Requirements

1. **Account for every real Tavily HTTP attempt**
   - Remove internal retry loop from `TavilySearchProvider.search()`.
   - Implement retry loop and logic at the collector level (`ResearchCollector.fetch()`), respecting quota.
2. **Make EXTRACTION_UNAVAILABLE a real configurable state**
   - Add `research_claim_extraction_enabled` to Settings.
   - Fix dead condition in `ResearchCollector`.
3. **Report disabled state in Read API**
   - API should return `status=DISABLED` when capability is disabled and no run exists.
4. **PROVIDER_ERROR must not be fresh for normal TTL**
   - `latest_snapshot()` should return `(None, None)` for `PROVIDER_ERROR` statuses.
5. **Partial provider failure visibility**
   - If one query succeeds and another fails, record `PROVIDER_ERROR` but persist gathered items.
   - Store diagnostic details in `details_jsonb`.
6. **Validate research mode strictly**
   - FastAPI endpoint typing `Literal["latest_run", "accumulated"]`.
7. **Documentation cleanup and Add Tests**
   - Updated worklogs and status.
   - Added `test_tavily_single_attempt_per_search`
   - Added `test_retry_per_attempt_quota_reservation`
   - Added `test_extraction_unavailable_via_settings`
   - Added `test_partial_failure_status_is_provider_error`
   - Added `test_provider_error_run_not_fresh`
   - Added integration test `test_research_api_mode_invalid_returns_422`
   - Added integration test `test_research_api_returns_disabled_when_capability_disabled`
   - Added integration test `test_partial_provider_failure_persists_provider_error`
