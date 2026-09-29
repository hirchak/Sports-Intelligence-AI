import re

# Fix research.py
with open("src/sports_intelligence/api/routes/research.py", "r") as f:
    content = f.read()
content = content.replace(
    "view = await get_research_for_fixture(session, fixture_id, as_of=as_of, mode=mode, capability_enabled=capability_enabled)",
    "view = await get_research_for_fixture(\n            session, fixture_id, as_of=as_of, mode=mode, capability_enabled=capability_enabled\n        )"
)
with open("src/sports_intelligence/api/routes/research.py", "w") as f:
    f.write(content)

# Fix service.py
with open("src/sports_intelligence/research/service.py", "r") as f:
    content = f.read()
content = content.replace(
    "status=ResearchState.NO_USEFUL_RESULTS.value if capability_enabled else ResearchState.DISABLED.value,",
    "status=(ResearchState.NO_USEFUL_RESULTS.value if capability_enabled else ResearchState.DISABLED.value),"
)
with open("src/sports_intelligence/research/service.py", "w") as f:
    f.write(content)

