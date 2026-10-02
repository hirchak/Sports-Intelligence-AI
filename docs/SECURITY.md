# M10 private-runtime security pass

LOCAL DEVELOPMENT ONLY. This is the implementation agent's repository/runtime review, **not independent
M10 acceptance**. Exact gates and residual limits are in M10_ACCEPTANCE_REPORT.

## Findings addressed

| ID | Initial finding / impact | Fix and evidence |
|---|---|---|
| S1 High operational | Compose omitted many runtime provider/schedule/quota settings; configured safety gates could diverge | All application services load selected ignored env; internal DB/broker URLs remain explicit; bootstrap/topology checks |
| S2 Medium | JSON formatter rendered full exceptions without a final redaction layer | Credential keys/URLs and registered secrets redacted in messages/context/tracebacks; tests cover auth/query/exception, token counts retained |
| S3 Medium | Non-mock sports configuration could explicitly return mocks without a gate | Factory refuses mock outside MOCK; two-mode regressions; existing LLM/search/odds gates retained |
| S4 Low | Bot started with empty allowlist (access middleware did deny everyone) | Startup now refuses before any transport request; positive ID validation; middleware still denies unknown/missing users/callbacks |
| S5 Low operational | Unbounded/default worker parallelism and plain query access logs | concurrency2/prefetch1, bounded broker connect/publish policy; safe request correlation logs, no query/body/header logging; production API no access log/proxy headers |
| S6 Low operational | Alembic fileConfig disabled existing application loggers inside test/CLI process | disable_existing_loggers=False, full-suite lifecycle-log regression |

API-Football API-error exceptions now use a static message rather than echoing arbitrary provider error bodies.
Application images run uid10001; production-like API command has no debug/reload, OpenAPI disabled,
no published ports in private Compose override. Standard upstream Postgres/Redis entrypoints retain their
own initialization/privilege-dropping behavior. No public CORS/control plane has been added.

## Audited retained boundaries

- Central Telegram allowlist covers messages/callbacks on all routers; test transport proves unauthorized
  users never call backend handlers. Backend errors are typed/safe and escaped. No arbitrary shell endpoint.
- API writes use bounded strict models/UUIDs and queued identifiers; credentials/arbitrary model config,
  endpoint URLs or filesystem paths are not public request parameters. Pydantic rejects unsafe extras.
- ORM/parameterized SQL; operational CLI uses argument lists and validated identifiers, never shell=True.
  Backup/restart scripts are operator-only local tools, not exposed through Telegram/API.
- Frozen model metadata contains no key fields; provider adapters retain safe usage/request IDs/hashes,
  not auth headers. External provider-error bodies are not operational messages. No keys in prompt/config.
- .env and dumps ignored; locked uv dependencies, pinned uv build tool, production target, no automatic deploy.
- Separate project/network/volumes/env/database; loopback development ports, zero production-like host ports.
- M9 analyst/proposals cannot edit code, activate prompts/routes, change weights or apply production decisions.
  Human actions on the API assume a trusted private operator; Telegram enforces allowlist before them.

## Limits and future gate

The internal API is intentionally not a public identity/auth platform. Before any explicitly approved external
exposure, add authentication and reassess host/proxy/body limits; current topology prohibits publishing it.
Security sanity scans known local credential fingerprints, private-key/GitHub-token patterns, working files
and reachable Git blobs; it is heuristic, not proof of absence of every secret or dependency vulnerability.
No penetration test, complete vulnerability-database audit, real server security/resources or independent
M10 audit is asserted. Live integrations and deployment gates remain separate.

Commands: `make security-check`, `make compose-safety`, full security/access/provider regressions, runtime
outage acceptance. Do not print `docker compose config` with real env values; use config -q or the keyless
captured topology script. If a secret ever appears in Git, stop that area and rotate under owner authorization.

Guidance used: local security-best-practices Python/FastAPI skill; primary
[Docker Compose merge/reset documentation](https://docs.docker.com/reference/compose-file/merge/).
