CONTINUATION OF THE ACTIVE M7 GOAL.

Everything below is part of the same goal and is binding.

You are the lead implementation agent for Milestone M7.

Do not treat the GPT-6.1 Sol model running inside Codex as the application's runtime forecasting model. Development model and runtime LLM providers are separate concerns.

The runtime architecture must remain provider-agnostic.

======================================================================
0. VERIFY REPOSITORY STATE FIRST
======================================================================

Before modifying anything, read:

- AGENTS.md
- docs/IMPLEMENTATION_STATUS.md
- docs/CURRENT_TASK.md
- docs/AI_WORKLOG.md
- docs/REVIEW_HANDOFF.md
- README_EXECUTION_ORDER.md
- 00_MASTER_TECHNICAL_SPEC.md
- 07_TELEGRAM_BOT_SPEC.md
- 08_FOOTBALL_ANALYTICS_PIPELINE.md
- 09_AGENT_CATALOG_AND_ORCHESTRATION.md
- 10_DATABASE_AND_DATA_LIFECYCLE.md
- 11_API_QUOTA_CACHING_STRATEGY.md
- 12_LLM_ROUTER_AND_MODEL_POLICY.md
- 14_DATA_QUALITY_PROVENANCE_AND_LEAKAGE.md
- 15_FORECASTING_METHODOLOGY_V1.md
- 17_OPEN_QUESTIONS_AND_CONFIG_DEFAULTS.md
- 18_LOCAL_ACCEPTANCE_TEST_PLAN.md

Then inspect:

git status
git branch --show-current
git fetch origin
git rev-parse HEAD
git rev-parse origin/build/m7
git rev-parse origin/main
git describe --tags origin/main

Expected accepted starting point:

origin/main:
11b6e782ab7256607992b70cc0d0dee4ebe92a3a

tag:
v0.7-m6

origin/build/m7:
11b6e782ab7256607992b70cc0d0dee4ebe92a3a

Work only on build/m7.

If repository reality differs, reconcile safely before implementation.

Do not reconstruct current state from prior chat memory.

Update docs/CURRENT_TASK.md before meaningful implementation.

======================================================================
1. M7 OBJECTIVE
======================================================================

Build the first complete measurable forecasting layer:

immutable MatchContext
→ prediction eligibility
→ probability baselines
→ deterministic Model Router
→ runtime LLM Prediction Engine
→ strict Prediction Validator
→ normalized complete probability table
→ deterministic bookmaker comparison
→ Candidate Ranking
→ immutable prediction persistence
→ read-only API / thin Telegram integration

The system must clearly separate:

A. What is the probability of an event?

from

B. Is the current bookmaker price interesting relative to that probability?

Do not collapse forecasting and candidate selection into one LLM answer.

The LLM is an analytical layer only.

It MUST NOT:

- schedule itself;
- decide which model/provider should be used;
- make hidden web/search requests;
- fetch sports data;
- alter MatchContext;
- calculate basic bookmaker/no-vig math;
- choose edge thresholds;
- choose staking;
- settle match outcomes;
- invent missing evidence;
- silently rewrite probabilities after validation.

======================================================================
2. INITIAL MARKET SET
======================================================================

Support exactly the V1 market family:

1X2:
- HOME
- DRAW
- AWAY

Double Chance:
- HOME_OR_DRAW
- HOME_OR_AWAY
- DRAW_OR_AWAY

Totals:
- OVER_1_5
- UNDER_1_5
- OVER_2_5
- UNDER_2_5

BTTS:
- YES
- NO

Store every supported probability for each successful prediction run.

Do not only store displayed candidates.

======================================================================
3. MATHEMATICAL COHERENCE
======================================================================

Do not ask the LLM to independently estimate probabilities that can be
deterministically derived from other probabilities.

Preferred V1 core output:

LLM estimates directly:

P(Home)
P(Draw)
P(Away)

P(Over 1.5)
P(Over 2.5)

P(BTTS Yes)

Then deterministic Python derives:

P(Home or Draw) = P(Home) + P(Draw)
P(Home or Away) = P(Home) + P(Away)
P(Draw or Away) = P(Draw) + P(Away)

P(Under 1.5) = 1 - P(Over 1.5)
P(Under 2.5) = 1 - P(Over 2.5)

P(BTTS No) = 1 - P(BTTS Yes)

1X2 probabilities must sum to 1 within an explicit tight tolerance.

All probabilities must be finite numbers inside [0, 1].

Do not silently renormalize grossly invalid LLM output.

Small floating-point tolerance normalization may be deterministic and explicit,
but genuinely invalid output must go through validation/repair/failure semantics.

======================================================================
4. STRICT LLM OUTPUT CONTRACT
======================================================================

Create strict Pydantic structured-output schemas.

The LLM output should contain at minimum:

- fixture_id
- forecast phase
- direct probabilities
- abstain
- abstain_reason
- confidence diagnostics
- evidence_for
- evidence_against
- risk_flags
- concise analysis/summary

Confidence is diagnostic metadata only.

Confidence is NOT probability.

Do not use free-form prose as the machine source of probabilities.

Prefer native provider structured output / JSON schema.

Fallback:
- JSON-only structured prompt if provider lacks native schema.

Never parse probabilities from a long natural-language response using regex.

======================================================================
5. EVIDENCE GROUNDING
======================================================================

The model must reason only from the exact supplied MatchContext.

No hidden retrieval.

Evidence references should be auditable.

Where practical use structured evidence references such as:

- deterministic feature name/path
- availability field
- lineup field
- research claim ID
- research document/source reference
- data-quality warning
- source manifest category

The validator must reject or flag references that obviously point outside the
provided context.

Do not require the LLM to copy large evidence blobs.

Keep explanations compact.

======================================================================
6. ABSTENTION / NO PREDICTION
======================================================================

Abstention is a first-class valid outcome.

Possible reasons include:

- data quality below configured prediction threshold;
- critical evidence missing;
- excessive source conflict;
- invalid context;
- provider/model failure;
- unrecoverable invalid structured output.

If MatchContext DataQuality says can_predict=false, do not make a normal
forecast merely because an LLM is available.

Persist auditable abstention state where appropriate.

Do not force a forecast for every fixture.

======================================================================
7. PROMPT VERSIONING
======================================================================

Production/runtime prompts must live as versioned files in Git.

Create an explicit prompt identity mechanism.

Persist at minimum:

- prompt name
- semantic version
- Git/source identity where useful
- SHA-256 content hash
- created_at / active semantics according to repo conventions

Never mutate the identity of an old prediction by editing an old prompt in place.

A prompt content change must generate a different prompt identity/hash.

======================================================================
8. LLM PROVIDER ABSTRACTION
======================================================================

Implement a clean provider-independent LLM boundary.

Conceptually support:

- MockLLMProvider
- OpenAI-compatible provider(s)
- MiniMax provider
- OpenCode Go provider
- future providers

Do not couple prediction domain logic to vendor SDKs.

Internal result should normalize fields such as:

- parsed structured output
- provider
- actual model
- request ID
- latency
- usage/input tokens/output tokens if available
- finish reason
- raw response reference/metadata where safe
- provider error classification

Never store secret API keys in DB.

Do not log secrets.

Mock provider must be deterministic and CI-compatible.

======================================================================
9. CONFIGURATION AND REAL PROVIDER GATING
======================================================================

Runtime provider/model must be configuration-driven.

No provider/model ID may be treated as permanently hard-coded truth.

Mock mode must work with zero credentials.

Non-mock provider configuration must fail clearly if required credentials are
missing.

Never silently fall back to Mock in sandbox/live_local.

Do not require real OpenAI/MiniMax/OpenCode credentials for CI acceptance.

If an appropriate real API key already exists locally, a bounded optional smoke
test may be performed.

Do not ask the user to paste API keys into chat.

Do not consume meaningful paid quota for acceptance.

======================================================================
10. MODEL ROUTER
======================================================================

Implement deterministic ModelRouter.

The model never chooses itself.

Routing inputs should support concepts such as:

- task_type
- required capabilities
- quality tier
- budget class
- route configuration
- provider health
- explicit manual override if authorized

At minimum support task types:

prediction_primary
prediction_challenger

Architecture should remain extensible for:

research_extract
improvement_analysis

without pulling those milestones into M7.

Routing output must explicitly identify:

- selected provider
- selected model
- fallback route(s)
- route identity/config fingerprint if useful

Actual provider/model used must be persisted on PredictionRun.

======================================================================
11. FALLBACK AND REPAIR POLICY
======================================================================

Classify provider failures.

Retryable examples:

- timeout
- transient 5xx
- eligible 429/rate limit
- temporary provider outage

Non-retryable examples:

- invalid auth
- invalid route config
- unsupported structured-output capability
- schema incompatible with implementation

Structured output validation policy:

1. initial prediction call
2. if invalid but repairable → at most ONE explicit structured repair attempt
3. if still invalid → fail safely

Do not run unlimited repair loops.

Fallback to another provider/model may occur only according to configured policy.

Fallback must be auditable.

Never pretend the fallback model was the originally selected model.

======================================================================
12. MODEL HEALTH / USAGE
======================================================================

Create only the amount of health infrastructure necessary for M7.

Support normalized health concepts:

HEALTHY
DEGRADED
RATE_LIMITED
UNAVAILABLE

Record enough telemetry to enable deterministic routing decisions and future
cost/latency comparison.

Capture usage when provider returns it.

Track by at least:

- task type
- provider
- model
- prediction run

Do not overengineer a full billing platform.

======================================================================
13. PREDICTION IDENTITY / IDEMPOTENCY
======================================================================

A prediction identity must bind the exact forecasting semantics.

At minimum include:

- MatchContext/context_hash
- prompt hash/version
- provider
- model
- decoding/model config identity
- prediction variant
- forecast phase

Same exact semantic request should be reusable/idempotent according to policy.

Changing any semantic component creates a distinct prediction identity.

A manual explicit rerun must never overwrite an old PredictionRun.

Do not use mutable "latest prediction" rows as the historical record.

======================================================================
14. MODEL CONFIG VERSIONING
======================================================================

Persist runtime configuration identity.

At minimum:

- provider
- model ID
- supported/used sampling parameters
- structured-output mode
- max output tokens if applicable
- config JSON
- deterministic config hash if appropriate

Do not fake unsupported parameters.

If one provider does not expose temperature, do not invent a fake temperature.

Forecasting defaults should be low/non-creative where supported.

======================================================================
15. PREDICTION PERSISTENCE
======================================================================

Implement normalized SQLAlchemy models + Alembic migration(s).

Follow the logical design already specified by repository docs.

At minimum include equivalents of:

prompt_versions

model_configs

prediction_runs

market_predictions

ranked_candidates

PredictionRun should reference:

- fixture
- exact MatchContext
- forecast phase
- prompt version
- model config
- requested route
- actual provider/model
- status
- start/completion timestamps
- latency
- token usage if known
- provider request ID if known
- error code/class if failed
- variant
- abstention state where applicable

MarketPrediction should persist every supported model probability.

RankedCandidate should persist deterministic market comparison and filter result.

Do not store only the top pick.

Do not overwrite old runs.

======================================================================
16. MARKET BASELINE
======================================================================

Preserve market baseline separately from LLM probability.

Use already normalized/no-vig probabilities from MatchContext/odds evidence.

Do NOT treat bookmaker market probability as ground truth.

The ranking engine may compare model probability against market probability.

The prediction prompt must clearly label bookmaker information as market
information rather than fact.

======================================================================
17. SIMPLE STATISTICAL BASELINE
======================================================================

Forecasting methodology requires a measurable non-LLM baseline.

Implement a deliberately simple, transparent statistical baseline if the current
M6 feature set supports it truthfully.

Preferred direction:

- scoring/conceding rates
- home/away information where available
- simple Poisson-style goal model
- deterministic derivation of supported market probabilities

Do not build a large ML model.

Do not fabricate inputs that the current data model does not contain.

If a full statistically defensible Poisson baseline cannot be implemented with
the existing available inputs, implement the cleanest truthful baseline that is
possible and explicitly document limitations.

Persist/identify baseline outputs separately from the LLM prediction.

The purpose is future comparison, not arbitrary ensembling.

Do NOT combine LLM + market + statistical baseline using invented weights.

======================================================================
18. ANTI-ANCHORING VARIANTS
======================================================================

Architecture must support two prediction variants:

LLM_WITH_ODDS
LLM_WITHOUT_ODDS

For WITHOUT_ODDS:

Create a deterministic context projection/masking step that removes bookmaker
odds/market probability information from the LLM payload while preserving the
original immutable MatchContext unchanged.

Do not mutate the stored MatchContext.

Both variants must be distinguishable in PredictionRun identity.

Do not automatically run both for every production prediction unless configured.

They are required for later empirical comparison.

======================================================================
19. PRIMARY / CHALLENGER
======================================================================

Support:

PRIMARY
CHALLENGER / SHADOW

A challenger must:

- receive the same underlying MatchContext and selected variant;
- create its own PredictionRun;
- never overwrite primary;
- not become primary merely because one example looks better;
- not be automatically averaged with primary.

Store disagreement information if useful and deterministic.

Do not implement M8 evaluation yet.

M8 will later compare:
- Brier
- log loss
- calibration
- coverage
- segments
- latency
- cost

======================================================================
20. PREDICTION VALIDATOR
======================================================================

Prediction Validator must be ordinary deterministic Python.

Validate at minimum:

- schema
- fixture/context identity
- finite numbers
- probability range [0,1]
- 1X2 sum tolerance
- all required direct probability fields
- derived market consistency
- abstention consistency
- duplicate/contradictory outputs
- unsupported markets
- data quality restrictions
- evidence reference sanity
- bounded text/list sizes where appropriate

Invalid output must never be published as a valid prediction.

One repair attempt maximum according to policy.

======================================================================
21. COMPLETE NORMALIZED PROBABILITY TABLE
======================================================================

After validation produce a normalized deterministic probability table for all
supported selections.

Every successful prediction must expose/store:

HOME
DRAW
AWAY
HOME_OR_DRAW
HOME_OR_AWAY
DRAW_OR_AWAY
OVER_1_5
UNDER_1_5
OVER_2_5
UNDER_2_5
BTTS_YES
BTTS_NO

Use stable canonical market/selection identifiers.

Avoid ambiguous strings that later make settlement/evaluation difficult.

======================================================================
22. CANDIDATE RANKING ENGINE
======================================================================

Candidate Ranking must be deterministic Python.

For each supported selection where market odds are available:

market_probability = no-vig implied probability

edge =
model_probability - market_probability

expected_value =
model_probability * captured_decimal_odds - 1

Use exact odds snapshot associated with the prediction context where possible.

Never fetch fresh odds inside ranking behind the prediction's as_of boundary.

Ranking/filter configuration must include at minimum:

- allowed markets
- minimum data quality
- minimum decimal odds
- optional maximum decimal odds
- minimum model probability
- minimum edge
- maximum candidates per fixture
- stale odds exclusion
- league allow/deny semantics if existing project config supports it

Default minimum displayed decimal odds may follow spec default 1.30,
but all thresholds must be configurable and versioned/auditable.

Persist why each considered candidate passed or failed.

It is valid to return:

NO BET
NO HIGH-CONFIDENCE OPPORTUNITY

Zero displayed candidates is a normal successful result.

======================================================================
23. NO-BET VS ABSTAIN
======================================================================

Keep these concepts separate.

ABSTAIN:
the system does not produce a normal forecast due to inadequate context,
quality, or prediction failure.

NO BET / NO HIGH-CONFIDENCE OPPORTUNITY:
the system produced valid probabilities but no market passes deterministic
candidate thresholds.

These must not be represented as the same state.

======================================================================
24. API / APPLICATION CONTROL PLANE
======================================================================

Implement or extend internal FastAPI/application services as appropriate.

Required capabilities should include equivalents of:

POST /v1/fixtures/{fixture_id}/analyze
GET /v1/predictions
GET /v1/predictions/{run_id}

Manual analyze must enqueue work.
Do not perform a long LLM call synchronously inside the request handler.

Request should support safe explicit options such as:

- phase/context selection according to existing architecture
- PRIMARY vs CHALLENGER
- LLM_WITH_ODDS / LLM_WITHOUT_ODDS
- optional configured model route override if permitted

Do not accept arbitrary API keys or raw dangerous provider configs through API.

Duplicate clicks must respect idempotency.

======================================================================
25. CELERY / ORCHESTRATION
======================================================================

Prediction work belongs on the `llm` queue.

Tasks receive minimal identifiers, not giant MatchContext JSON blobs.

Worker loads canonical MatchContext from DB.

Task execution must be auditable through existing Job / JobAttempt conventions.

Preserve automatic pipeline architecture.

When a final suitable MatchContext is produced and prediction policy says it is
eligible, the system should be capable of enqueuing prediction automatically.

Do not create uncontrolled repeated LLM calls on every scanner tick.

Use stable prediction semantic identity for deduplication.

Morning and pre-match predictions are distinct because MatchContext/as_of/phase
differ.

======================================================================
26. TELEGRAM
======================================================================

Keep Telegram thin.

Do not put prediction/ranking business logic into handlers.

Extend UI only as needed for M7 acceptance.

Expected user capabilities:

- see latest prediction for fixture
- see top candidates
- see full probability table
- see why/evidence
- see risks
- see model metadata
- manually request re-run
- later allow different configured model/challenger route

A manual rerun creates a new PredictionRun when explicitly requested.
Never overwrite previous prediction.

Use Russian UI consistent with existing bot.

Never use phrases such as:

- guaranteed
- safe bet
- certain

Allow:

NO HIGH-CONFIDENCE OPPORTUNITY

Do not dump giant MatchContext JSON into Telegram.

======================================================================
27. AUTOMATIC FORECASTING
======================================================================

Maintain the system's automatic-first design.

M7 must integrate with existing scheduled pipeline rather than making prediction
dependent on Telegram clicks.

Expected behavior conceptually:

MORNING MatchContext ready
→ eligible prediction job

PREMATCH_FINAL / final pre-match MatchContext ready
→ eligible updated prediction job

Exact existing phase names and schedule semantics must follow repository reality.

Do not invent incompatible new phase names if current enums already define them.

Do not create blind high-frequency LLM polling.

======================================================================
28. SECURITY / COST CONTROL
======================================================================

No secrets in:
- Git
- DB model configs
- prompts
- logs
- Telegram
- test fixtures

LLM calls must have:

- explicit timeout
- bounded retries
- bounded repair
- token/output bounds where provider supports them
- configurable daily/challenger budgets where practical

Mock tests consume zero external quota.

A missing live API credential must not block M7 code acceptance.

======================================================================
29. PROMPT CONTENT PRINCIPLES
======================================================================

The forecasting prompt should explicitly tell the runtime model:

- estimate calibrated probabilities, not "pick a winner";
- do not copy bookmaker probabilities blindly;
- market odds are one evidence class, not ground truth;
- do not invent facts;
- distinguish observed evidence from uncertainty;
- old H2H is secondary;
- verified availability/lineups/recent form matter more;
- confidence does not replace probability;
- abstain when context is insufficient;
- use only supplied context;
- output schema exactly.

Keep prompt concise enough for controlled runtime cost.

Version it from day one.

======================================================================
30. TESTING — UNIT
======================================================================

Add comprehensive deterministic tests.

At minimum cover:

- output schema validation
- exact required markets
- probability bounds
- NaN/Inf rejection
- 1X2 sum validation
- deterministic complementary markets
- deterministic double-chance derivation
- validator rejects malformed output
- one repair attempt only
- second invalid response safely fails
- abstain behavior
- can_predict=false behavior
- NO BET distinct from abstain
- prompt hash stability
- prompt change → new hash
- model config hash stability
- prediction semantic cache/idempotency key
- model change → new identity
- prompt change → new identity
- config change → new identity
- WITH_ODDS vs WITHOUT_ODDS → different identity
- WITHOUT_ODDS projection actually removes market data
- original MatchContext remains unchanged
- deterministic ModelRouter
- route fallback auditability
- actual provider/model persistence
- MockLLM deterministic behavior
- no silent Mock fallback
- candidate edge math
- EV math
- threshold boundaries
- stale odds filtering
- missing odds
- zero-candidate result
- candidate ranking stable ordering
- maximum candidates per fixture
- statistical baseline deterministic behavior
- no arbitrary ensemble averaging

======================================================================
31. TESTING — PROVIDER CONTRACTS
======================================================================

Use injected/mock HTTP transports where appropriate.

Test:

- successful structured output
- timeout
- retryable 5xx
- 429
- bad JSON
- invalid structured output
- auth failure
- usage parsing
- request ID parsing
- finish reason
- bounded retry
- bounded repair
- secret redaction

Do not require internet in CI.

======================================================================
32. TESTING — INTEGRATION
======================================================================

Using dedicated *_test Postgres + Redis, verify:

- migration creates M7 tables
- prediction persists exact MatchContext reference
- context_hash identity is preserved
- prompt/model config identities persisted
- all market probabilities persisted
- ranked candidates reference correct PredictionRun
- exact odds snapshot/as_of boundaries preserved
- duplicate semantic request does not create accidental duplicate production run
- explicit manual rerun preserves old run and creates correct new run semantics
- PRIMARY and CHALLENGER coexist
- WITH_ODDS and WITHOUT_ODDS coexist
- fallback actual provider/model recorded
- failed prediction remains auditable
- invalid output never produces displayed candidate
- can_predict=false never results in normal prediction
- later lineup/odds/result cannot leak into historical prediction replay
- automatic eligible context → one prediction job
- duplicate scheduler scan → no duplicate LLM call/job
- Telegram/API read from persisted prediction state only
- handlers never invoke provider directly

======================================================================
33. MOCK END-TO-END M7 FLOW
======================================================================

Create a deterministic keyless integration path:

fixture
→ snapshots
→ MatchContext
→ MockLLM
→ validation
→ derived probabilities
→ ranking
→ persistence
→ API
→ Telegram/test transport

This must work without external credentials.

Do NOT implement M8 settlement/evaluation.

======================================================================
34. LIVE SMOKE
======================================================================

Only if a valid runtime LLM credential is ALREADY configured locally.

Perform at most one tightly bounded prediction smoke test on one existing safe
MatchContext.

Do not expose key.

Do not include secret request headers in logs.

Report:

- provider
- model
- success/failure
- latency
- approximate usage if returned

Do not treat lack of live credentials as M7 failure.

Never ask the user to paste credentials into chat.

======================================================================
35. MIGRATIONS
======================================================================

All schema changes require Alembic.

Verify:

- fresh empty DB → upgrade head
- downgrade -1
- upgrade head
- alembic check
- existing M6 DB → M7 migration
- no manual DB patching
- no schema drift

Avoid destructive changes to accepted M0-M6 history.

======================================================================
36. QUALITY GATES
======================================================================

Before handoff run the repository's complete gate:

uv run ruff check .
uv run ruff format --check .
uv run mypy src

unit tests

integration tests with dedicated *_test Postgres + Redis

full pytest

Alembic:
upgrade head
downgrade -1
upgrade head
alembic check

docker compose config -q
docker compose --profile telegram config -q

secret sanity scan

Verify working tree status.

Push build/m7.

Wait for GitHub Actions on the exact remote HEAD.

All CI jobs must be SUCCESS.

======================================================================
37. SCOPE BOUNDARIES
======================================================================

DO implement:

- runtime LLM abstraction
- Mock provider
- real provider adapter architecture
- deterministic router
- prompt/model versioning
- prediction output schema
- prediction validator
- repair/fallback
- all V1 probabilities
- market baseline linkage
- simple measurable statistical baseline
- WITH_ODDS/WITHOUT_ODDS capability
- PRIMARY/CHALLENGER capability
- ranking
- persistence
- prediction jobs
- minimal API
- minimal Telegram M7 integration
- tests

DO NOT implement:

- result settlement
- post-match evaluation engine
- Brier/log-loss aggregation engine
- calibration reports
- automated prompt optimization
- improvement analyst
- experiment promotion
- arbitrary ensembles
- staking strategy
- live/in-play betting
- production deployment

Those belong to later milestones.

======================================================================
38. PERSISTENT PROJECT MEMORY
======================================================================

Continuously maintain:

- docs/CURRENT_TASK.md
- docs/IMPLEMENTATION_STATUS.md
- docs/AI_WORKLOG.md
- docs/REVIEW_HANDOFF.md

Do not erase historical milestone failures/reviews.

Document architecture decisions if an ADR is required.

Git is the authoritative development history.

======================================================================
39. FINAL STATE
======================================================================

At completion:

- branch must remain build/m7
- build/m7 must be pushed
- main must remain accepted M6
- M7 must NOT be merged
- M8 must NOT be started
- working tree clean
- exact remote CI HEAD green

STOP for independent review.

Do not merge or tag M7 yourself.

======================================================================
40. FINAL HANDOFF FORMAT
======================================================================

Return a concise but complete handoff containing:

1. final origin/build/m7 HEAD SHA
2. base main SHA / v0.7-m6 confirmation
3. major M7 architecture implemented
4. LLM provider adapters implemented
5. ModelRouter behavior
6. prompt/model version identity
7. PredictionRun identity/idempotency
8. supported probability markets
9. validator and one-repair behavior
10. abstain vs NO BET behavior
11. statistical baseline implementation and limitations
12. market baseline linkage
13. WITH_ODDS / WITHOUT_ODDS support
14. PRIMARY / CHALLENGER support
15. candidate ranking policy
16. automatic scheduling integration
17. API endpoints
18. Telegram changes
19. migrations
20. unit test count/result
21. integration test count/result
22. full test result
23. Ruff/format/mypy
24. Alembic verification
25. Docker Compose verification
26. exact GitHub Actions run ID + HEAD SHA + all job results
27. real runtime LLM calls performed, if any
28. known limitations
29. confirmation M7 NOT merged
30. confirmation M8 NOT started
31. confirmation zero deployment / Hetzner / Hermes interaction

Then STOP.