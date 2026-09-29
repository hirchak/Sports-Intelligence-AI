with open("src/sports_intelligence/research/service.py") as f:
    content = f.read()

content = content.replace("from typing import Any", "from typing import Any, Literal")

old_def = """async def get_research_for_fixture(
    session: AsyncSession,
    fixture_id: uuid.UUID,
    *,
    as_of: datetime | None = None,
    mode: str = "latest_run",
) -> FixtureResearchView:"""

new_def = """async def get_research_for_fixture(
    session: AsyncSession,
    fixture_id: uuid.UUID,
    *,
    as_of: datetime | None = None,
    mode: Literal["latest_run", "accumulated"] = "latest_run",
    capability_enabled: bool = True,
) -> FixtureResearchView:"""
content = content.replace(old_def, new_def)

old_run_null = """    if run_row is None:
        return FixtureResearchView(
            fixture_id=fixture_id,
            status=ResearchState.NO_USEFUL_RESULTS.value,"""
new_run_null = """    if run_row is None:
        return FixtureResearchView(
            fixture_id=fixture_id,
            status=ResearchState.NO_USEFUL_RESULTS.value if capability_enabled else ResearchState.DISABLED.value,"""
content = content.replace(old_run_null, new_run_null)

with open("src/sports_intelligence/research/service.py", "w") as f:
    f.write(content)
