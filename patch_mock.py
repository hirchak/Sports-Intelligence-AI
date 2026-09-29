with open("tests/unit/collectors/test_research_collector.py") as f:
    content = f.read()

content = content.replace("class MockSearchPartial:", "from sports_intelligence.providers.search.base import SearchProvider\n    class MockSearchPartial(SearchProvider):")
with open("tests/unit/collectors/test_research_collector.py", "w") as f:
    f.write(content)
