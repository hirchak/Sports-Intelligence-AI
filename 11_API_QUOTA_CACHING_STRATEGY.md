# API Quota, Caching and Request Optimization Strategy

The project must treat external API calls as a budgeted resource.

This is especially important on low-cost/free plans.

---

# 1. Important distinction

**100 API requests/day does not mean 100 matches/day.**

A naive implementation can spend several requests per fixture:

```text
fixture
standings
team stats x2
injuries
odds
H2H
lineups
...
```

The architecture must optimize at league/team/date/batch level before fixture level.

---

# 2. Current provider notes

Provider capabilities and quotas change. Verify before production.

At the time this spec was authored:

## API-Football / API-Sports

Official public pricing/docs show:

- Free: 100 requests/day;
- Free per-minute: 10 requests/minute;
- response headers expose daily and minute limits/remaining.

Useful optimization:

- `fixtures?ids=` can retrieve multiple fixture IDs in one request;
- current API-Football guidance documents up to 20 IDs for that usage;
- fixture bulk responses can include detailed blocks such as events, lineups, statistics and player statistics;
- injuries also support multi-ID querying in current API versions.

Docs:
- https://www.api-football.com/
- https://www.api-football.com/news/post/how-to-optimize-api-sports-calls-and-quota-usage
- https://www.api-football.com/news/post/how-to-get-all-fixtures-data-from-one-league

## Sportmonks

Current Football API v3 supports:

- rich `include=` expansion;
- fixture-by-date;
- multi-fixture request with up to 50 fixture IDs in the documented multi endpoint;
- one fixture call can include related entities.

Docs:
- https://postman.sportmonks.com/
- https://www.sportmonks.com/football-api/

Provider adapters must own provider-specific batching rules.

---

# 3. Quota Manager

Create a first-class service:

```text
QuotaManager
```

Responsibilities:

- record each external request;
- read provider rate-limit headers;
- estimate remaining daily budget;
- reserve calls for critical tasks;
- throttle per-minute requests;
- prevent duplicate calls within freshness window;
- downgrade optional work when quota is low.

Persist:

```text
provider
window
limit
remaining
observed_at
request_category
```

---

# 4. Request priority

Priority classes:

## P0 Critical

- fixture result settlement;
- authentication/health validation;
- final fixture status;
- essential pre-kickoff refresh for a selected fixture.

## P1 High

- daily fixture discovery;
- initial odds;
- essential team context;
- injuries/availability.

## P2 Normal

- standings refresh;
- richer statistics;
- H2H.

## P3 Optional

- secondary bookmaker snapshots;
- repeated research;
- optional metadata;
- experimental/challenger data enrichment.

When quota is low, pause P3 first.

---

# 5. Freshness registry

Every data category has a TTL/freshness policy.

Example initial policy:

```text
league metadata:          days/weeks
team metadata:            days
standings:                6–24 h
historical completed form: until new match completes
season team stats:        6–24 h
H2H:                      until either team plays relevant new H2H
morning injuries:         2–6 h
pre-match injuries:       30–90 min
lineups before release:   do not poll aggressively
confirmed lineups:        immutable after capture except corrections
morning odds:             1–3 h
pre-kickoff odds:         15–60 min
completed result:         immutable after confirmation
```

Exact values are configuration, not hard-coded domain rules.

---

# 6. Cache hierarchy

Use:

## L1 application/process cache

Only for tiny very-short-lived objects if useful.

## L2 Redis

For:

- request coalescing;
- rate-limit counters;
- locks;
- short-lived provider response cache;
- job deduplication.

## L3 PostgreSQL snapshots

For durable cache/history.

Before an external request:

```text
1. is valid snapshot in Postgres?
2. is refresh actually required for this forecast phase?
3. is equivalent request in progress?
4. quota available?
5. then call provider.
```

---

# 7. Request coalescing

If 10 fixture jobs all request the same standings table:

Do not send 10 requests.

Use a lock/future:

```text
standings:{provider}:{league}:{season}
```

One worker fetches.

Others wait/use the fresh snapshot.

Same principle for team season stats.

---

# 8. Batch-first strategy

Provider adapter exposes capabilities:

```python
ProviderCapabilities(
    supports_fixture_ids_batch=True,
    max_fixture_ids_per_request=20,
    supports_injury_ids_batch=True,
    supports_embedded_fixture_details=True,
)
```

Domain orchestration never assumes a universal max.

The adapter chunks IDs according to capability.

---

# 9. Daily optimized call plan example

For illustration only.

Suppose 12 target fixtures / 24 teams.

A naive collector could exceed 100 calls.

An optimized plan may look conceptually like:

```text
1 call     discover today's fixtures
1 call     bulk fixture detail (if <= provider batch limit)
4 calls    standings, once per active league
~24 calls  team season stats only if not fresh
1–few      batched injuries
1–few      odds by date/league/fixture depending provider
0–few      H2H only if not cached
```

If team stats are already fresh, the daily cost drops sharply.

Do not promise a fixed call count because provider endpoints/coverage vary.

---

# 10. Historical form optimization

Do not refetch a team's entire history for every fixture.

Maintain local fixture/result history.

After each completed match:

1. persist result;
2. update team rolling-form materialization/cache.

Then the next forecast can calculate form locally.

External provider is used to fill gaps and validate new results.

This is one of the largest long-term request savings.

---

# 11. Standings optimization

Standings are league-wide.

Fetch once per:

```text
provider + league + season + freshness window
```

All fixtures in the league reference the same snapshot.

---

# 12. Results optimization

Do not fetch result fixture-by-fixture if provider can query completed fixtures by date.

Typical next-day flow:

```text
fetch yesterday's fixtures once/batched
→ match by external ID
→ update all target results
→ settle locally
```

No LLM/API calls are needed to determine bet outcomes.

---

# 13. Lineup optimization

Confirmed lineups are valuable but often unavailable early.

Do not poll from morning every few minutes.

Pre-match scanner:

```text
T-120: check whether provider usually has lineup
T-90/T-60: one bounded refresh
after confirmed: cache and stop polling
```

Exact timing depends on provider coverage and competition.

---

# 14. Odds optimization

Define only markets used by the product.

Do not store/fetch every exotic market.

Initial whitelist:

```text
1X2
Double chance
O/U 1.5
O/U 2.5
BTTS
```

Use provider filtering where available.

Keep a small number of meaningful snapshots:

```text
MORNING
PREMATCH
optional CLOSING
```

Do not poll continuously in v1.

---

# 15. Search API optimization

Research is expensive and noisy.

Use:

- maximum queries per fixture;
- search result cap;
- domain/source deduplication;
- content hash;
- cached sources across same team/day;
- only rerun if research freshness expired.

A press conference article about Team A may be relevant to multiple later queries; do not repeatedly fetch it.

---

# 16. LLM call optimization

LLM requests also need caching/budgeting.

If identical:

```text
MatchContext hash
+ prompt hash
+ model config
```

already has a successful prediction, reuse it unless user explicitly asks for a new run.

Manual rerun should create a new run only if explicitly requested.

Research claim extraction can also cache by document content hash + extractor version.

---

# 17. Dynamic degradation

When quota remaining crosses thresholds:

Example:

```text
>50% remaining: NORMAL
25–50%: CONSERVE
10–25%: CRITICAL
<10%: RESERVE_ONLY
```

Behavior:

NORMAL:
- all enabled work.

CONSERVE:
- skip optional H2H refresh;
- fewer odds sources;
- reuse slightly older non-critical cache.

CRITICAL:
- only target fixtures/essential availability/odds.

RESERVE_ONLY:
- reserve for result/critical pre-match/admin action.

Thresholds configurable.

---

# 18. Rate limit behavior

Parse provider headers where supported.

For API-Football-style headers:

```text
x-ratelimit-requests-limit
x-ratelimit-requests-remaining
X-RateLimit-Limit
X-RateLimit-Remaining
```

On 429:

- do not immediately retry in a tight loop;
- respect reset/retry information if available;
- exponential backoff;
- record quota event.

---

# 19. Request ledger

Create operational telemetry:

```text
external_api_requests
- provider
- endpoint_category
- fixture_id nullable
- league_id nullable
- started_at
- duration_ms
- status_code
- cache_hit
- daily_remaining nullable
- minute_remaining nullable
```

This makes API optimization measurable.

---

# 20. API budget acceptance criteria

- [ ] No standings request per fixture.
- [ ] Historical form is primarily calculated from local stored results.
- [ ] Provider batching is implemented where supported.
- [ ] Response rate-limit headers are recorded.
- [ ] Same request is coalesced during concurrency.
- [ ] Cache freshness is category-specific.
- [ ] Quota reserve exists.
- [ ] Optional work degrades before critical work.
- [ ] Results can be collected in bulk.
- [ ] LLM calls are keyed by context/prompt/model hashes.
