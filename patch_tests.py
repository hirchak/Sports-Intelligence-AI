with open("tests/unit/test_search_provider.py") as f:
    content = f.read()

# Replace test_tavily_search_provider_500_retries_and_raises_transient
old_500 = """@pytest.mark.asyncio
async def test_tavily_search_provider_500_retries_and_raises_transient() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(500, json={"error": "Internal server error"})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    provider = TavilySearchProvider(api_key="secret-key-123", client=client, max_retries=2)

    try:
        with pytest.raises(ProviderServerError):
            await provider.search("any query")
        assert call_count == 3
    finally:
        await provider.aclose()"""

new_500 = """@pytest.mark.asyncio
async def test_tavily_single_attempt_per_search() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(500, json={"error": "Internal server error"})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    provider = TavilySearchProvider(api_key="secret-key-123", client=client)

    try:
        with pytest.raises(ProviderServerError):
            await provider.search("any query")
        # Ensure only 1 attempt is made inside Tavily provider
        assert call_count == 1
    finally:
        await provider.aclose()"""

content = content.replace(old_500, new_500)
with open("tests/unit/test_search_provider.py", "w") as f:
    f.write(content)

