import datetime

# Update REVIEW_HANDOFF.md
with open("docs/REVIEW_HANDOFF.md") as f:
    handoff = f.read()

handoff = handoff.replace("M5.1 HEAD", "M5.2 HEAD")
handoff = handoff.replace("Milestone M5.1: Web Research Correctness Subsystem", "Milestone M5.2: Web Research Correctness Subsystem")
handoff = handoff.replace("The scope was purely correctly capturing", "The scope was to address M5.2 fixes for HTTP retries, extraction configuration, API disabled states, and partial provider failures")

with open("docs/REVIEW_HANDOFF.md", "w") as f:
    f.write(handoff)

# Update AI_WORKLOG.md
worklog_entry = f"""
---
timestamp: {datetime.datetime.now().isoformat()}
agent/model: Antigravity (Gemini)
milestone: M5.2
task: Implement focused M5.2 correctness fixes
files changed:
- src/sports_intelligence/providers/search/tavily.py
- src/sports_intelligence/collectors/research_collector.py
- src/sports_intelligence/core/config.py
- src/sports_intelligence/api/routes/research.py
- src/sports_intelligence/research/service.py
- tests/unit/test_search_provider.py
- tests/unit/collectors/test_research_collector.py
- tests/integration/test_m5_research.py
- .env.example
- docs/CURRENT_TASK.md
- docs/IMPLEMENTATION_STATUS.md
- docs/REVIEW_HANDOFF.md
behavior implemented:
- Removed internal retry loop from TavilySearchProvider.
- Moved retry loop to ResearchCollector with quota checks on each attempt.
- Added research_claim_extraction_enabled to Settings and used it properly.
- Handled disabled research capability in the Read API.
- latest_snapshot() ignores runs with PROVIDER_ERROR status so they aren't considered fresh.
- Recorded partial provider failures as PROVIDER_ERROR with detail_jsonb diagnostics.
- Validate mode strictly as Literal["latest_run", "accumulated"] in API and service.
commands/tests run: uv run pytest -q, uv run ruff check, uv run mypy src
results: All tests pass.
known problems: None.
spec/ADR deviations: None.
next recommended action: Review M5.2 changes.
"""

with open("docs/AI_WORKLOG.md", "a") as f:
    f.write(worklog_entry)

