# ADR-0007: API-Football as first sports data provider

**Date:** 2026-08-20  
**Status:** Accepted  
**Milestone:** M2

## Context

`17_OPEN_QUESTIONS_AND_CONFIG_DEFAULTS.md` leaves the sports provider open
(API-Football vs Sportmonks). M2 must implement the first real
`SportsDataProvider`. This is a reversible architecture decision: the
adapter boundary exists precisely so providers can be swapped.

## Decision

Implement **API-Football (API-Sports)** as the first provider.

- Adapter: `providers/sports/api_football.py`, async httpx.
- Auth: `x-apisports-key` header, key read only from
  `SPORTS_API_KEY` environment — never logged, never persisted.
- Base URL configurable via `API_FOOTBALL_BASE_URL`
  (default `https://v3.football.api-sports.io`).
- Discovery endpoint: `GET /fixtures?date=YYYY-MM-DD` (one bounded
  date-level request; enabled leagues filtered locally).
- Bounded retry (3 attempts, exponential backoff + jitter) for timeouts,
  transport errors, 429 and 5xx; auth errors (401/403) are non-retryable.
- Normalized exceptions (`ProviderError` hierarchy); response metadata
  includes rate-limit headers when present.
- Domain code only ever sees typed DTOs (`providers/dto.py`), never
  API-Football JSON.

## Provider boundaries

- All provider-specific parsing, batching, auth and retry logic lives in
  the adapter.
- `ProviderCapabilities` declares what the adapter supports; the discovery
  service is written batch-first but must not assume hard-coded limits.
- Raw payloads are persisted (hash-deduplicated) before normalization for
  auditability.

## Alternatives

- Sportmonks Football API v3 — equally valid; richer includes, different
  quota model. Rejected as *first* provider only because API-Football has
  a simple date-level fixtures endpoint and well-known rate-limit headers.
- Building a multi-provider abstraction layer now — rejected: YAGNI; the
  adapter interface is the abstraction.

## Consequences

- MOCK mode uses a `MockSportsDataProvider` backed by recorded, sanitized
  API-Football-shaped responses; no key required anywhere in CI.

## Rollback/Migration

To migrate to Sportmonks or another provider: add a new adapter with the
same `SportsDataProvider` interface, switch `SPORTS_PROVIDER` configuration,
and re-point `provider_entity_ids.provider` mapping. Schema and domain code
do not change.
