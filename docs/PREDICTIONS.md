# M7 forecasting and deterministic market comparison

LOCAL DEVELOPMENT ONLY. Development coding models are separate from runtime LLM providers.
M7 does not implement settlement, evaluation, fitted ensembles, staking or deployment.
Complete binding scope: [M7_SCOPE.md](M7_SCOPE.md). Review packet: [REVIEW_HANDOFF.md](REVIEW_HANDOFF.md).

## Flow and identity

Persisted immutable M6 MatchContext → quality gate → separate statistical/market baselines →
configured ModelRouter → runtime adapter → strict output validation → twelve normalized probabilities
→ deterministic candidate filters/ranks → PostgreSQL → read-only API / thin Telegram.

The worker verifies canonical context SHA-256 and fixture/phase/as_of before calls. No fresh sports,
odds, research or results are fetched. M6 `MORNING` and `PREMATCH` names are retained; `POSTMATCH`
is refused. DataQuality.can_predict=false or score below prediction policy means ABSTAINED with
zero provider calls. As_of at/after kickoff and cancelled/finished context statuses also abstain.

Prompt `prompts/predictor/1.0.0.txt` is versioned in Git and copied into Docker/package assets.
At enqueue, DB stores prompt name, semantic version, source path, SHA-256 and exact content.
`active=true` means a prompt was selected by permitted runtime configuration; it is not a mutable
single-active pointer. Worker uses the persisted content, even if a file later changes. Create a
new semantic-version file for prompt revisions; changed content always generates another hash/row.

ModelSpec stores provider/model, endpoint style, structured mode, supported/used sampling values,
output limit, capabilities and SHA-256. `None` sampling parameters are omitted from HTTP requests.
Credentials are read only from environment and never copied into config, prompt, DB or responses.

Requested identity binds context hash, prompt hash/version, selected provider/model/config hash,
role, variant, phase, engine version, policy and routing/fallback fingerprint. Request key additionally
binds explicit rerun UUID. Actual semantic identity uses the actual fallback/returned model config.
A repeated semantic request reuses its run, including terminal failure; explicit rerun creates a new
row and never overwrites old probabilities/candidates. Rerun attempts use the same underlying context.
QUEUED → RUNNING CAS allows one worker; duplicate delivery performs no LLM call. A process crash
leaving RUNNING, or lost broker delivery, needs operational investigation and explicit rerun; M7 does
not automatically reset it and risk duplicate paid calls. No general outbox/recovery platform added.

## Provider/router configuration

`config/llm.yaml` is the versioned authority for routes, ranking and cost controls. Default routes are
MOCK/keyless. Optional `LLM_PROVIDER` + `PREDICTOR_MODEL` + `LLM_BASE_URL` explicitly override only
the primary route; otherwise configure YAML. An env provider/model override clears inherited sampling
parameters; configure model-supported low sampling explicitly in YAML. API style/schema support are model-specific.
Legacy `DEFAULT_MIN_*` env fields do not override M7 YAML ranking thresholds.

Adapters: MockLLMProvider; OpenAIProvider/OpenAICompatibleProvider; MiniMaxProvider; OpenCodeGoProvider.
Non-streaming httpx, no vendor SDK in domain code, no tools, no hidden retrieval. Native strict JSON
schema for capable chat/responses APIs; JSON-only schema prompt otherwise. MiniMax uses JSON-only
mode and reasoning_split; unsupported native schema is not claimed. Go supports configured chat,
messages (JSON-only) or responses protocol styles; model IDs must match the configured endpoint.

Official contracts checked on 2026-10-01:
- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [MiniMax OpenAI-compatible API](https://platform.minimax.io/docs/api-reference/text-openai-api)
- [OpenCode Go API](https://opencode.ai/docs/go/)

Go documentation describes coding-agent traffic, so availability of endpoints does not prove
permission for a forecasting workload. Runtime Go stays disabled by default via
`LLM_OPENCODE_GO_RUNTIME_ALLOWED=false`; configure permitted runtime use separately before enabling.
The adapter identifies itself as sports-intelligence; it never impersonates a coding agent.

Provider-specific keys: `LLM_OPENAI_API_KEY`, `LLM_MINIMAX_API_KEY`, `LLM_OPENCODE_GO_API_KEY`.
`LLM_API_KEY` is used only for the explicitly selected legacy LLM_PROVIDER. No silent Mock fallback
in sandbox/live_local. Missing credentials produce an auditable failed run, no HTTP call and no
claimed actual provider/model. No runtime credentials were configured locally during M7 acceptance;
live smoke was skipped, zero real runtime LLM calls.

Router deterministically uses task type, capabilities, route quality/budget labels, explicit permitted
override list and recent model health. Degraded is usable; rate-limited/unavailable are skipped for
configured alternatives. States expire after configured TTL. Actual provider/model and skip/fallback
reasons persist. Primary/challenger routes can coexist; default UI lists PRIMARY only.

## Validation and failure bounds

Strict Pydantic output requires fixture_id/context_hash/phase, six direct probabilities (or null on
abstain), reason, diagnostic confidence, compact structured evidence paths, risks and summary.
Unknown fields/markets, duplicate/contradictory evidence, outside-context paths, NaN/Inf, booleans as
probabilities, out-of-range numbers, incompatible abstention and invalid 1X2 sums are rejected.
1X2 tolerance is 1e-6; only tiny accepted floating drift is normalized and recorded in run audit.
Over2.5 <= Over1.5 and BTTS Yes <= Over1.5. Complements/DC are derived in Python.

One explicit structured repair maximum **across the whole run**, including fallbacks. A repair is not
retried. Initial transient calls have configured 0–2 retries with bounded delay; retryable timeout,
transport, 5xx and 429 classifications. Auth/config/schema compatibility failures never retry or
fallback. Fallback is limited to configured routes/errors. Invalid JSON is parsed as JSON only,
with duplicate keys rejected; no regex probability parsing. Truncated/refused output cannot publish.

Per-physical-call telemetry includes run/task/provider/model, purpose, health, latency, usage if
available, request ID, finish reason, response hash and safe error code. Invalid structured output
updates health to DEGRADED. Real HTTP attempts also link the existing external request ledger.
No response body/auth headers/reasoning traces retained. Global/challenger daily attempt budgets use
an atomic PostgreSQL advisory lock and count retries/repair. Limits are call counts, not monetary billing.

## Probabilities, baselines and ranking

Exactly: HOME, DRAW, AWAY; HOME_OR_DRAW, HOME_OR_AWAY, DRAW_OR_AWAY;
OVER_1_5, UNDER_1_5, OVER_2_5, UNDER_2_5; BTTS_YES, BTTS_NO.
All twelve are stored on every successful run, even when zero candidates are displayed.

Statistical `poisson_v1`: home lambda = (observed home last10 GF + away last10 GA)/2;
away lambda = (away last10 GF + home last10 GA)/2. Independent Poisson score grid 0–80;
refuse missing/invalid rates or tail >1e-10. No fabricated prior, home advantage, opponent adjustment,
xG or arbitrary ensemble. Preserve inputs and limitations; this baseline is not calibrated or proven
accurate. Known zero rates remain zero; unavailable baseline stays explicitly unavailable.

Market `captured_no_vig_v1`: separate median captured bookmaker benchmarks. Only complete,
finite normalized markets are usable. Double Chance outcomes overlap: ignore M4's generic sum-1
DC margin normalization and derive DC from the same-bookmaker captured 1X2. No new odds fetch or
changes to M4 historical data. Bookmaker probabilities are benchmarks, not truth.

Ranking takes each selection's highest captured valid price with a compatible same-bookmaker no-vig
benchmark, then deterministic bookmaker tie-break. Edge = model P − market P; EV = model P * odds − 1.
Filters: supported/allowed market, context eligibility, minimum quality, min/max odds, minimum model P,
minimum edge, odds age and M6 stale flag, league allow/deny (deny wins), maximum displayed candidates.
Probability/edge threshold comparison uses auditable 1e-12 float tolerance (configurable up to 1e-6),
so derived arithmetic drift does not reject equality. No model probability is changed by ranking.
Policy/hash, original odds set/time/bookmaker and every considered selection's pass/failure reasons
persist. Stable ordering: edge DESC, EV DESC, model P DESC, canonical selection ASC.
ABSTAIN is no forecast; NO_BET is valid probabilities with no passing price. They are distinct outcomes.

WITHOUT_ODDS is a deterministic copy of the original context, masking market snapshot, market/odds
features, odds/research provenance, quality free text/details and arbitrary research claims. Nested
provider market keys are also removed. Original context remains unchanged. Conservative removal of
all research text can confound later pure odds-effect comparisons; retain this limitation for M8+.
No automatic running of both variants, challenger promotion or averaging.

## Control plane and automatic flow

- `POST /v1/fixtures/{fixture_id}/analyze` → 202, persisted Job/PredictionRun, llm queue.
- `GET /v1/predictions` → role/fixture/variant filters, bounded pagination, PRIMARY by default.
- `GET /v1/predictions/{run_id}` → probabilities, candidates, evidence, models, versions, baselines, audit.

POST options: phase, context_id, optional as_of cutoff, role, variant, allowlisted route_override.
Explicit rerun requires `rerun=true` and stable `rerun_key` UUID. No keys/raw provider config accepted.
Not-ready context → 409, invalid config/options → 422, enqueue error → auditable FAILED + 502.

`PREDICTION_AUTO_ENABLED=true` permits eligible context completion to enqueue primary prediction.
Existing scheduler flags remain separate and disabled by default. No scanner-frequency LLM polling.
Morning/prematch context/as_of differ and remain separate runs. Local acceptance did not activate the
running scheduler, automatic external calls or Telegram pushes. Telegram only reads persisted API
state and enqueues actions; tests use fake transport, not a new live Telegram smoke.

## Local verification

Use repo root and the existing Docker Compose Postgres/Redis. Unit/provider tests need no credentials.
All integration URLs must name a dedicated `*_test` DB; Redis db15 only. M7 acceptance used a fresh
`sports_intel_m7_test` database. No manual schema patches, production DB migrations or server access.

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q -m 'not integration'
TEST_DATABASE_URL=postgresql+asyncpg://sports:sports_dev_password@localhost:5433/sports_intel_m7_test \
TEST_REDIS_URL=redis://localhost:6380/15 uv run pytest -q -m integration
```

Fresh DB upgrade, M6→M7, downgrade -1, re-upgrade and alembic check are verified independently.
The integration suite includes discovery→collectors→context→MockLLM→validation→ranking→persistence
→API→Telegram test transport and real isolated Redis Celery message serialization. Mock output is
explicitly synthetic and is not evidence of model accuracy or a live provider integration.

## M7.1 M4 canonical odds compatibility

M4 stores normalized 1X2 prices as `market="h2h_1x2"`, `selection=home|draw|away`.
M7 accepts this canonical identifier (while retaining legacy `h2h`/`1x2` aliases), groups only complete
no-vig sets from one identified bookmaker, and derives each Double Chance benchmark from that same
bookmaker's 1X2 probabilities. Incomplete 1X2 rows, missing bookmaker identity, or pieces split across
bookmakers cannot create a 1X2/DC baseline. The Odds API request key `h2h` remains provider-specific;
M4 maps it to `h2h_1x2` before persistence. M7.1 does not change M4's live normalizer or schema.
