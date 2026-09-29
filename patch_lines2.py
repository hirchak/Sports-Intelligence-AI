import re

with open("src/sports_intelligence/research/service.py", "r") as f:
    content = f.read()

content = content.replace(
    "status=(ResearchState.NO_USEFUL_RESULTS.value if capability_enabled else ResearchState.DISABLED.value),",
    "status=(\n                ResearchState.NO_USEFUL_RESULTS.value\n                if capability_enabled\n                else ResearchState.DISABLED.value\n            ),"
)
with open("src/sports_intelligence/research/service.py", "w") as f:
    f.write(content)
