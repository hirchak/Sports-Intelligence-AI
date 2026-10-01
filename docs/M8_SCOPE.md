CONTINUATION OF THE ACTIVE M8 GOAL.

Everything below belongs to the same goal and is binding.

You are the lead implementation agent for Milestone M8.

M8 must turn the already accepted M7 prediction records into an objective,
reproducible measurement system.

The purpose is NOT to optimize predictions yet.

The purpose is to establish trustworthy truth data, deterministic settlement,
and statistically correct evaluation so future model/prompt/data decisions can
be made from evidence.

======================================================================
0. VERIFY REPOSITORY STATE FIRST
======================================================================

Before modifying anything read:

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
- docs/PREDICTIONS.md
- relevant M7 DB models/migrations/tests

Then inspect:

git status
git branch --show-current
git fetch origin
git rev-parse HEAD
git rev-parse origin/build/m8
git rev-parse origin/main
git describe --tags origin/main

Expected accepted starting point:

origin/main:
4eff88bcaaac387ec047d50575d25b8135baa567

tag:
v0.8-m7

origin/build/m8:
4eff88bcaaac387ec047d50575d25b8135baa567

Work only on build/m8.

If reality differs, inspect and reconcile safely before implementation.

Update docs/CURRENT_TASK.md before meaningful implementation.

======================================================================
1. M8 OBJECTIVE
======================================================================

Implement:

completed fixture discovery
→ final result collection
→ result validation
→ immutable fixture result persistence
→ deterministic settlement of every supported prediction
→ evaluation of all forecast probabilities
→ aggregate metrics and segmentation
→ API
→ thin Telegram stats/results UI
→ scheduled/local automatic flow

No LLM is required anywhere in this pipeline.

Never ask an LLM whether a prediction won.

M8 must evaluate what M7 actually predicted, without changing historical
PredictionRun, MatchContext, model probability, prompt identity, candidate
ranking or captured odds.

======================================================================
2. RESULT TRUTH
======================================================================

Create a clear authoritative fixture-result model.

At minimum preserve:

- fixture_id
- provider
- provider fixture identity / provenance where appropriate
- final fixture status
- regulation score / canonical score used for settlement
- extra-time score if provider supplies it
- penalty score if provider supplies it
- observed/confirmed timestamp
- raw provider payload reference where existing architecture supports it
- result version/source identity
- created_at

Do not overwrite historical prediction evidence.

If result information changes because a provider corrects a result,
preserve an auditable history or explicit version/update provenance rather than
silently pretending the original observation never existed.

Design the smallest clean solution consistent with current data lifecycle.

======================================================================
3. RESULT COLLECTOR
======================================================================

Implement result collection through the existing SportsDataProvider boundary.

Do not hard-code API-Football business logic into settlement/evaluation.

Prefer batch/date-level completed fixture retrieval where the provider supports it.

Avoid fixture-by-fixture N+1 external calls.

Typical intended flow:

fetch completed fixtures for relevant date/window
→ resolve provider fixture IDs
→ persist validated final results
→ enqueue settlement locally

Reuse:

- quota manager
- external request ledger
- provider IDs
- cache/batching patterns
- retries/error classification
- Celery conventions

No LLM/API calls are required after final results are locally available.

Mock result provider/data must support deterministic CI.

======================================================================
4. RESULT STATES
======================================================================

Explicitly distinguish statuses such as:

- final/completed
- after extra time if provider exposes it
- after penalties if provider exposes it
- postponed
- cancelled
- abandoned
- unfinished/live
- unknown/provider anomaly

Do not settle an unfinished match.

Postponed/cancelled/abandoned handling must be deterministic and auditable.

Do not guess a result from partial score data.

======================================================================
5. SETTLEMENT POLICY MUST BE EXPLICIT
======================================================================

Create a versioned deterministic settlement policy.

Do not leave time-basis semantics implicit.

The existing specs require explicit testing of extra-time cases but do not
authorize hidden assumptions.

Therefore:

- inspect current product/provider semantics;
- define the V1 settlement time basis explicitly;
- document it in code/docs/ADR if needed;
- ensure all markets use the same documented policy unless a market explicitly
  differs;
- never silently include extra time or penalties merely because the provider
  exposes those fields.

Persist settlement_version so future policy changes do not rewrite old history.

======================================================================
6. SUPPORTED SETTLEMENTS
======================================================================

Settle every M7 supported selection:

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
- BTTS_YES
- BTTS_NO

Canonical settlement outcomes:

- WIN
- LOSS
- PUSH
- VOID
- UNSETTLED

Do not use bookmaker text parsing.

Use the canonical M7 Selection enum / market identity whenever possible.

For 1.5 / 2.5 lines, PUSH should be structurally possible but impossible under
normal integer football scores; do not invent pushes.

======================================================================
7. PREDICTION SETTLEMENT
======================================================================

Each persisted MarketPrediction must be settled independently.

Settlement identity should bind at minimum:

- market_prediction_id
- authoritative fixture result/version
- settlement policy/version

Never overwrite the probability itself.

Repeated settlement with the same inputs must be idempotent.

If the authoritative result changes, handle re-settlement explicitly and
auditably.

Do not create duplicate settlement rows on task retry.

======================================================================
8. DISPLAYED CANDIDATE / ROI SETTLEMENT
======================================================================

Evaluation must distinguish:

A. ALL probability forecasts

from

B. DISPLAYED ranked candidates

Probability accuracy is evaluated for all eligible forecasts.

Candidate research metrics use only the appropriate ranked/displayed candidate
population.

For fixed-unit research ROI:

- use captured odds persisted at prediction time;
- never fetch a later price for historical ROI;
- do not use dynamic staking;
- use a fixed 1-unit analytical convention;
- WIN / LOSS / VOID / PUSH handling must be deterministic.

This is research/evaluation, not bankroll management.

Do not implement staking strategy.

======================================================================
9. CORE PROBABILITY EVALUATION
======================================================================

Implement statistically correct deterministic evaluation.

Required metrics where applicable:

- Brier score
- Log Loss
- calibration buckets / reliability
- calibration error
- probability sharpness
- coverage / abstention rate
- number of evaluated probabilities / predictions
- candidate hit rate
- number of displayed candidates
- average captured odds
- expected value at prediction time
- realized fixed-1-unit ROI research metric

If closing odds exist, support a clearly labeled closing-line comparison/proxy
without pretending it exists when no closing snapshot is available.

Do not evaluate solely by "percentage correct".

======================================================================
10. BRIER SCORE
======================================================================

Implement Brier from first principles with tested known examples.

For each binary selection:

(p - y)^2

where y ∈ {0,1}.

For mutually exclusive 1X2, define and document the exact multiclass Brier
convention used.

Do not mix incompatible Brier definitions under one metric name.

Metric version/config must make the convention reproducible.

======================================================================
11. LOG LOSS
======================================================================

Implement log loss correctly.

Do not allow log(0).

Use an explicit small configurable numeric epsilon ONLY for metric computation.

Persist/document that epsilon and metric version.

Do not alter stored model probabilities.

Test extreme confident-right and confident-wrong cases.

======================================================================
12. CALIBRATION
======================================================================

Implement calibration/reliability buckets.

Buckets must be deterministic and versioned.

For each bucket expose at minimum:

- probability range
- sample size
- mean predicted probability
- empirical event frequency
- calibration gap

Clearly define boundary behavior, e.g. where exactly 0.6 lands.

Never show a calibration claim without sample size.

Implement a calibration error metric with a documented definition
(e.g. weighted absolute bucket gap) rather than an ambiguous label.

======================================================================
13. SHARPNESS
======================================================================

Implement a clearly defined probability sharpness metric.

Document exact mathematical definition.

Do not invent a vague "confidence score".

The same implementation/version must be reproducible from historical
MarketPrediction rows.

======================================================================
14. COVERAGE / ABSTENTION
======================================================================

M7 distinguishes:

ABSTAIN
vs
valid forecast with NO_BET.

Preserve this distinction.

Calculate:

- forecast coverage
- abstention rate
- valid prediction runs
- failed prediction runs separately
- candidate/display coverage separately

Do not treat NO_BET as ABSTAIN.

Do not treat provider/system failure as a forecasting abstention.

======================================================================
15. SEGMENTATION
======================================================================

Evaluation must support filtering/aggregation by useful dimensions already
preserved by M6/M7.

At minimum:

- time period
- league
- market
- selection where useful
- odds bucket
- model config/provider/model
- prompt version
- prediction role (PRIMARY / CHALLENGER)
- variant (WITH_ODDS / WITHOUT_ODDS)
- forecast phase
- data-quality bucket
- confidence bucket
- baseline type where relevant

Keep sample_size with every aggregate.

Do not draw a "best model" conclusion in code.

Return measurements, not subjective winners.

======================================================================
16. PRIMARY VS CHALLENGER
======================================================================

Evaluate PRIMARY and CHALLENGER separately.

Do not average them.

Do not promote challenger automatically.

The system should make future comparison easy:

- Brier
- Log Loss
- calibration
- coverage
- latency
- token usage/cost where known
- segmented performance

M8 must provide measurements only.

Model promotion belongs to future experiment/improvement flow.

======================================================================
17. WITH_ODDS VS WITHOUT_ODDS
======================================================================

Evaluate variants separately.

Do not merge their samples.

Keep the M7 documented caveat that the current WITHOUT_ODDS projection also
removes research text; therefore results cannot automatically be interpreted as
a pure causal "odds anchoring" experiment.

Expose the data cleanly for future analysis.

======================================================================
18. BASELINE EVALUATION
======================================================================

Evaluate the persisted probability baselines from M7 independently:

- market baseline
- statistical Poisson baseline
- LLM predictor

Do not invent ensemble weights.

Do not retroactively recompute a historical baseline if its persisted M7
baseline is available.

Use the persisted baseline associated with the PredictionRun.

Missing baseline probabilities remain missing and must reduce sample size rather
than being filled with fabricated values.

======================================================================
19. DATA MODEL
======================================================================

Implement normalized SQLAlchemy models + Alembic migration(s).

Follow existing specs and repository conventions.

At minimum equivalents of:

fixture_results

prediction_settlements

evaluation_runs

evaluation_metrics

You may add narrowly justified supporting tables for:

- calibration buckets
- immutable result observations/versioning
- evaluation configuration
- candidate settlement / research-return details

if this produces a cleaner auditable design.

Do not build a warehouse.

Do not duplicate giant MatchContext or PredictionRun payloads.

Use foreign keys to existing canonical M7 records.

======================================================================
20. EVALUATION RUN IDENTITY
======================================================================

An EvaluationRun must be reproducible.

Bind it to:

- evaluation config/version
- settlement version
- metric version(s)
- period/filter definition
- relevant source cutoff / as_of of evaluation
- created_at

Running the exact same evaluation twice should either reuse an identical run or
create a clearly distinguishable immutable rerun according to an explicit policy.

Never silently mutate an old evaluation.

======================================================================
21. NO DATA LEAKAGE / HISTORICAL INTEGRITY
======================================================================

Post-match results are allowed for evaluation ONLY.

They must never flow back into:

- MatchContext
- FeatureSnapshot used by the prediction
- PredictionRun
- model probabilities
- original candidate ranking

Add regression tests proving:

prediction made at T0
→ later lineup/odds at T1
→ result at T2
→ settlement/evaluation at T3

does not alter hashes or historical prediction payloads from T0.

======================================================================
22. AUTOMATIC POST-MATCH FLOW
======================================================================

M8 must support automatic operation.

Conceptually:

scheduled result scan
→ batch fetch completed results
→ persist results
→ settle new eligible predictions
→ update/evaluate metrics

Do not require Telegram clicks.

Avoid aggressive polling.

Use a sensible configurable expected-finish/grace window based on existing
scheduler architecture.

A next-day batch result pass should be supported.

Do not re-fetch already confirmed results unnecessarily.

======================================================================
23. FAILURE / RETRY BEHAVIOR
======================================================================

Result-provider failures must not corrupt settlement state.

Classify:

retryable:
- timeout
- transient 5xx
- eligible 429/provider rate limit

non-retryable:
- invalid mapping
- malformed final-result contract
- impossible score/state combination
- invalid auth/config

Settlement itself is local deterministic code and should not have provider retry
logic inside it.

Invalid final result:
- persist/audit safe failure if appropriate;
- do not settle;
- surface operationally.

======================================================================
24. API
======================================================================

Implement/extend internal FastAPI control plane as appropriate.

Required capabilities should include equivalents of:

GET /v1/results
GET /v1/results/{fixture_id}

POST /v1/jobs/evaluate
or equivalent queued/manual evaluation trigger

GET /v1/evaluations/summary

Useful query filters:

- date range
- league
- market
- model
- role
- variant
- phase
- prompt
- data-quality bucket
- odds bucket

Keep response sizes bounded.

API reads persisted evaluation state.

Do not calculate huge historical evaluations synchronously in HTTP requests if
that conflicts with current job architecture.

======================================================================
25. TELEGRAM
======================================================================

Keep Telegram thin.

Implement enough M8 UI to support:

- /stats
- recent results
- settled prediction view
- evaluation summary
- period selector:
  - last 7d
  - last 30d
  - all time
- segmentation shortcuts:
  - by league
  - by market
  - by model
  - by odds bucket

Always show sample size.

Example information:

Last 30 days
Predictions evaluated: N
Coverage: ...
Brier: ...
Log Loss: ...
Calibration: ...
Displayed candidate hit rate: ...
Research ROI: ...

Do not claim statistical significance unless actually computed.

Do not declare a model "best" from a tiny sample.

Do not put settlement/evaluation business logic into Telegram handlers.

======================================================================
26. DAILY / WEEKLY REPORTING FOUNDATION
======================================================================

M8 may provide deterministic daily/weekly aggregate summaries.

Daily:
- newly completed fixtures
- newly settled predictions
- evaluation refreshed
- operational settlement failures

Weekly deterministic summary:
- calibration by market
- performance by league
- primary vs challenger measurements
- high-confidence misses as data rows
- data-quality failure patterns
- cost/latency aggregates where persisted

Do NOT create the M9 LLM Improvement Analyst yet.

No recommendations or automatic prompt changes.

======================================================================
27. EXACT SETTLEMENT UNIT TESTS
======================================================================

Build a strong settlement matrix.

At minimum verify scores/statuses:

0-0
1-0
0-1
1-1
2-0
0-2
2-1
1-2
2-2
3-0
0-3

And required special states:

postponed
cancelled
abandoned
unfinished
extra-time scenario
penalty scenario

Verify all supported M7 markets for each representative score.

Use a table-driven test design if clean.

Test settlement invariants:

- HOME/DRAW/AWAY exactly one wins on a normally settled match
- each Double Chance is mathematically consistent with 1X2
- O1.5 / U1.5 complementary
- O2.5 / U2.5 complementary
- BTTS YES/NO complementary
- cancelled/postponed policy consistent
- repeated settlement idempotent

======================================================================
28. METRIC UNIT TESTS
======================================================================

Use tiny synthetic datasets where expected values can be calculated manually.

Test:

- Brier exact values
- multiclass 1X2 Brier exact convention
- log loss exact values
- epsilon behavior
- calibration bucket boundaries
- calibration weighted error
- sharpness definition
- coverage
- abstention
- NO_BET vs ABSTAIN
- hit rate
- fixed 1-unit return
- ROI
- average odds
- sample sizes
- empty datasets
- one-item datasets
- segmentation
- missing baseline probabilities
- primary/challenger separation
- WITH/WITHOUT_ODDS separation

No random statistical tests.

======================================================================
29. INTEGRATION TESTS
======================================================================

Using dedicated *_test Postgres + Redis verify:

- M8 migration
- result persistence
- provider result provenance
- batch result processing
- duplicate result fetch/persist idempotency
- settlement persistence
- retry does not duplicate settlements
- all 12 M7 probabilities can be evaluated
- displayed candidates receive correct research-return result
- non-displayed probabilities are still evaluated for probabilistic accuracy
- ABSTAIN does not produce market settlements
- NO_BET remains valid forecast/evaluation data
- PRIMARY/CHALLENGER remain separate
- statistical/market/LLM baselines remain separate
- historical PredictionRun/MatchContext unchanged
- future result never leaks backwards
- evaluation run persists config/version/sample size
- API returns persisted values
- Telegram reads backend only
- scheduler/result worker deduplicates work

======================================================================
30. FULL KEYLESS E2E
======================================================================

Extend the deterministic local keyless flow:

fixture discovery
→ collectors
→ MatchContext
→ MockLLM prediction
→ ranking
→ persisted prediction
→ inject/mock final result
→ result persistence
→ deterministic settlement
→ evaluation
→ API
→ Telegram/test transport

No external API keys required.

No live LLM calls required.

This is an important acceptance gate.

======================================================================
31. REAL PROVIDER SMOKE
======================================================================

Do not require live provider calls for acceptance.

If valid sports-provider credentials are ALREADY available locally, you may run
one tightly bounded result normalization smoke test.

Do not ask the user to paste a key.

Do not consume meaningful quota.

Report clearly whether live result collection was or was not tested.

======================================================================
32. MIGRATIONS
======================================================================

All schema changes require Alembic.

Verify:

fresh empty DB → head

accepted M7 DB → M8

downgrade -1

upgrade head

alembic check

No destructive modification to accepted M0–M7 migrations.

No manual DB patching.

======================================================================
33. PERFORMANCE / NUMERICAL SAFETY
======================================================================

Evaluation may process many rows.

Avoid obvious N+1 DB patterns.

Use bounded queries / grouping appropriately.

All metric calculations must reject:

NaN
Inf
impossible probability
invalid odds
invalid settlement state

Use numerically stable log-loss calculations.

Do not silently drop bad rows without auditable reason.

======================================================================
34. CONFIGURATION
======================================================================

Version/configure at least:

- result scan timing/grace
- settlement version
- metric version
- log-loss epsilon
- calibration bucket boundaries
- fixed research stake convention
- evaluation period/default filters

Do not bury methodology constants in random source files.

Config changes must produce distinguishable evaluation identity.

======================================================================
35. DOCUMENTATION
======================================================================

Document:

- final result authority
- result status model
- settlement time basis
- settlement rules for all V1 markets
- void/unsettled semantics
- metric formulas
- Brier convention
- log-loss epsilon
- calibration definition
- sharpness definition
- coverage definition
- ROI research convention
- segment dimensions
- known limitations

Do not claim statistical significance or profitability merely from implementation.

======================================================================
36. QUALITY GATES
======================================================================

Before handoff run:

uv run ruff check .
uv run ruff format --check .
uv run mypy src

unit tests

integration tests using dedicated *_test Postgres + Redis

full pytest

Alembic:
- fresh upgrade head
- accepted M7 → M8
- downgrade -1
- upgrade head
- alembic check

Docker:
- docker compose config -q
- dev override if repository CI verifies it
- docker compose --profile telegram config -q

secret sanity scan

Verify clean working tree.

Push build/m8.

Wait for GitHub Actions on the exact final remote HEAD.

All CI jobs must be SUCCESS.

======================================================================
37. SCOPE BOUNDARIES
======================================================================

DO implement:

- result collector
- final-result validation
- result persistence
- deterministic settlement
- prediction settlement
- candidate research-return settlement
- Brier
- Log Loss
- calibration
- calibration error
- sharpness
- coverage/abstention
- hit rate
- fixed-unit ROI research metric
- segmentation
- persisted evaluation runs/metrics
- automatic post-match flow
- API
- thin Telegram results/stats UI
- comprehensive tests

DO NOT implement:

- M9 Improvement Analyst
- automatic prompt optimization
- automatic model promotion
- arbitrary ensembles
- learned/calibrated model fitting
- staking strategy
- live/in-play system
- deployment
- Hetzner
- Hermes integration

======================================================================
38. PERSISTENT PROJECT MEMORY
======================================================================

Maintain:

- docs/CURRENT_TASK.md
- docs/IMPLEMENTATION_STATUS.md
- docs/AI_WORKLOG.md
- docs/REVIEW_HANDOFF.md

Add a focused M8 documentation file if useful.

Add ADR(s) where methodology/settlement conventions require explicit decisions.

Do not erase historical milestone failures or review history.

======================================================================
39. FINAL STATE
======================================================================

At completion:

- branch remains build/m8
- branch pushed
- main remains accepted M7
- M8 is NOT merged
- M9 is NOT started
- working tree clean
- exact remote CI green

STOP for independent review.

Do not merge or tag M8 yourself.

======================================================================
40. FINAL HANDOFF
======================================================================

Return a concise but complete handoff containing:

1. final origin/build/m8 HEAD SHA
2. accepted M7 base SHA / v0.8-m7
3. Result Collector implementation
4. batching/quota behavior
5. final-result status model
6. settlement version and time-basis policy
7. settlement rules for all supported markets
8. postponed/cancelled/abandoned behavior
9. DB migrations/tables
10. settlement idempotency
11. evaluation run identity
12. Brier definition
13. Log Loss definition/epsilon
14. calibration definition/buckets
15. calibration-error definition
16. sharpness definition
17. coverage/abstention definition
18. displayed-candidate hit rate / fixed-unit ROI convention
19. baseline evaluation
20. PRIMARY/CHALLENGER separation
21. WITH_ODDS/WITHOUT_ODDS separation
22. segmentation capabilities
23. automatic post-match pipeline
24. API changes
25. Telegram changes
26. unit test result
27. integration test result
28. full pytest result
29. Ruff/format/mypy
30. migration verification
31. Docker verification
32. exact GitHub Actions run ID + HEAD + jobs
33. live provider result calls performed, if any
34. known limitations
35. M8 NOT merged
36. M9 NOT started
37. zero deployment / Hetzner / Hermes interaction

Then STOP.