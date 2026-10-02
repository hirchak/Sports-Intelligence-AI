CONTINUATION OF THE ACTIVE M9 GOAL.

Everything below is part of the same binding goal.

You are the lead implementation agent for Milestone M9.

M9 turns the existing forecasting/evaluation system into a controlled
experimentation laboratory.

Its purpose is NOT to automatically optimize production.

Its purpose is to make changes measurable, replayable, comparable and
human-controlled.

======================================================================
0. VERIFY EXACT STARTING STATE
======================================================================

First read:

- AGENTS.md
- docs/IMPLEMENTATION_STATUS.md
- docs/CURRENT_TASK.md
- docs/AI_WORKLOG.md
- docs/REVIEW_HANDOFF.md
- README_EXECUTION_ORDER.md
- 00_MASTER_TECHNICAL_SPEC.md
- 07_TELEGRAM_BOT_SPEC.md
- 09_AGENT_CATALOG_AND_ORCHESTRATION.md
- 10_DATABASE_AND_DATA_LIFECYCLE.md
- 12_LLM_ROUTER_AND_MODEL_POLICY.md
- 14_DATA_QUALITY_PROVENANCE_AND_LEAKAGE.md
- 15_FORECASTING_METHODOLOGY_V1.md
- 16_GITHUB_AI_DEVELOPMENT_CONTROL.md
- 17_OPEN_QUESTIONS_AND_CONFIG_DEFAULTS.md
- 18_LOCAL_ACCEPTANCE_TEST_PLAN.md
- docs/EVALUATION.md
- all M8 ADRs and M8 scope/methodology files

Then inspect:

git status
git branch --show-current
git fetch origin
git rev-parse HEAD
git rev-parse origin/build/m9
git rev-parse origin/main
git rev-parse v0.9-m8^{}

Expected:

main =
490227ac8e27ca4c8870891277fd8783d8a7f1af

build/m9 =
490227ac8e27ca4c8870891277fd8783d8a7f1af

v0.9-m8^{} =
490227ac8e27ca4c8870891277fd8783d8a7f1af

Merged-main CI:
36981326405
SUCCESS for all three jobs.

Work only on build/m9.

M8 is MERGED / TAGGED / ACCEPTED.
M9 is NOT STARTED at the accepted base.

Do not reconstruct implementation state from prior conversation memory.

======================================================================
1. FIX THE POST-M8 STATE-DOC DRIFT FIRST
======================================================================

The accepted Git state is ahead of the persistent state documents.

At the accepted M9 base, CURRENT_TASK / IMPLEMENTATION_STATUS /
REVIEW_HANDOFF still describe the M8 merge/tag/build-m9 closeout as pending.

Before substantive M9 implementation:

Update current state truthfully so it records:

- M8 / M8.1 = PASS / ACCEPTED
- PR #10 merged
- accepted main:
  490227ac8e27ca4c8870891277fd8783d8a7f1af
- main CI:
  36981326405, all jobs SUCCESS
- annotated tag:
  v0.9-m8
- build/m9 created from the exact accepted main
- build/m9 == main == v0.9-m8^{}
- M9 now active
- no deployment / Hetzner / Hermes interaction

Preserve historical AI_WORKLOG entries.
Append rather than rewriting history.

Then begin M9.

======================================================================
2. M9 OBJECTIVE
======================================================================

Build:

historical frozen evidence
        ↓
Experiment definition
        ↓
Leakage-safe replay planning
        ↓
selected prompt/model/variant/config
        ↓
prediction replay / challenger execution
        ↓
existing deterministic settlement + M8 evaluation
        ↓
fair comparison against control/baseline
        ↓
experiment result
        ↓
Improvement Analyst
        ↓
structured ImprovementProposal
        ↓
human approval/rejection

Core rule:

EXPERIMENTATION MUST NEVER SILENTLY MUTATE PRODUCTION.

======================================================================
3. MAIN M9 COMPONENTS
======================================================================

Implement the appropriate equivalents of:

- ExperimentDefinition
- ExperimentRun
- ReplayPlanner
- ReplayEngine / ExperimentRunner
- ExperimentComparisonService
- ImprovementAnalyst
- ImprovementProposal persistence
- deterministic proposal state machine
- API/control layer
- thin Telegram UI
- CLI replay entry point

Reuse existing M6/M7/M8 contracts wherever possible.

Do not duplicate prediction, settlement or evaluation logic unnecessarily.

======================================================================
4. HISTORICAL REPLAY — ABSOLUTE LEAKAGE RULE
======================================================================

Historical replay may use ONLY evidence that genuinely existed at the
historical prediction as_of boundary.

Never reconstruct an old forecast using today's mutable data.

Never:

- query current injuries to fill historical gaps;
- use current league metadata as historical evidence;
- use later odds in an earlier forecast;
- use later research documents;
- use confirmed lineups that appeared after as_of;
- use final match result as prediction input;
- use post-match evaluation information as model input;
- silently rebuild missing old snapshots from current provider data.

Use the frozen MatchContext and immutable referenced evidence where available.

If a requested historical case cannot be reproduced without leakage:

MARK IT UNAVAILABLE / NOT REPLAYABLE.

Do not fabricate a replay.

This condition must be visible in experiment coverage/sample counts.

======================================================================
5. REPLAY INPUT AUTHORITY
======================================================================

Prefer exact historical MatchContexts as experiment inputs.

Each replayed item must bind to at least:

- original fixture ID
- original MatchContext ID
- context_hash
- original as_of
- forecast phase
- feature version
- data-quality report
- relevant immutable evidence identities

The replay must not create a different historical truth under the same
MatchContext identity.

If an experiment intentionally changes a context projection such as
LLM_WITH_ODDS vs LLM_WITHOUT_ODDS, derive it deterministically from the same
frozen MatchContext.

Never mutate the original MatchContext.

======================================================================
6. EXPERIMENT DEFINITION
======================================================================

An experiment must explicitly record what is being tested.

Support dimensions such as:

- provider/model
- model config
- prompt version
- LLM_WITH_ODDS / LLM_WITHOUT_ODDS
- PRIMARY-like control vs CHALLENGER treatment
- forecasting phase
- allowed fixture/date/league/market scope
- statistical baseline comparison
- market baseline comparison

Do not support arbitrary hidden changes.

Every experiment needs:

- stable experiment ID
- name/title
- hypothesis
- control specification
- treatment specification
- population/scope
- created_at
- created_by / trigger identity where project conventions support it
- status
- config/version hash
- evaluation policy/version
- optional budget limits
- immutable definition after execution begins

If definition changes materially, create a new experiment identity/version.

======================================================================
7. CONTROL VS TREATMENT
======================================================================

Experiments must compare like with like.

For model/prompt experiments:

Control and treatment should operate on the same eligible frozen
MatchContexts whenever possible.

Persist:

- requested sample
- eligible sample
- paired sample
- non-replayable count
- failed-control count
- failed-treatment count
- abstention counts
- reason exclusions

Do not make a treatment look better by silently comparing it on an easier
subset.

Where paired comparison is required, use the intersection truthfully.

Also expose full arm metrics separately when useful.

======================================================================
8. EXPERIMENT OUTPUT IS SEPARATE FROM PRODUCTION
======================================================================

Experiment predictions must be distinguishable from normal production
predictions.

They must never:

- replace the primary production PredictionRun;
- become the Telegram primary pick automatically;
- alter historical production prediction rows;
- overwrite existing MatchContexts;
- overwrite evaluation results;
- change prompt activation;
- change ModelRouter production routes.

Reuse existing prediction machinery through an explicit experiment/replay mode
where safe.

Persist experiment lineage.

======================================================================
9. REPLAY CLI
======================================================================

Provide a practical local CLI following the project spec conceptually:

python -m sports_intelligence.replay \
  --from YYYY-MM-DD \
  --to YYYY-MM-DD \
  --experiment <id or definition> ...

Exact ergonomic design is yours to choose.

CLI must support safe bounded options such as:

- date range
- phase
- league filter
- model/prompt variant
- WITH_ODDS / WITHOUT_ODDS
- dry-run / plan mode
- max fixtures/calls where useful
- mock execution

Before expensive execution provide a plan/count when practical.

CLI must not require Telegram.

======================================================================
10. MOCK-FIRST / COST CONTROL
======================================================================

M9 acceptance must be possible entirely with:

- MockLLM
- frozen test MatchContexts
- Postgres
- Redis
- deterministic M8 evaluation

No paid/live LLM calls required.

Real replay across many fixtures can become expensive.

Add bounded controls appropriate to existing architecture:

- max experiment LLM calls
- max fixtures
- model-route budget
- concurrency bounds
- explicit live execution opt-in

Do not accidentally launch a large live replay.

Do not ask the user to paste API keys into chat.

======================================================================
11. REUSE M8 EVALUATION
======================================================================

Do not build a second competing metric implementation.

Experiment comparison should use the established M8 metric definitions and
versions wherever possible.

Relevant comparisons include:

- Brier
- multiclass 1X2 Brier
- log loss
- calibration / ECE
- sharpness
- coverage
- abstention
- displayed candidate coverage
- hit rate
- fixed-unit research ROI
- closing proxy where legitimately available
- latency
- tokens
- cost only when genuinely known

Never fabricate monetary cost.

Always include sample size.

======================================================================
12. BASELINES
======================================================================

Preserve conceptual separation between:

- market baseline
- statistical baseline
- LLM forecasts

Experiments may compare against them.

Do NOT invent arbitrary ensemble weights.

Do NOT promote an ensemble merely because it looks good on a small sample.

If a baseline is unavailable for part of the sample, reduce/report its n
truthfully.

======================================================================
13. MODEL / PROMPT EXPERIMENTS
======================================================================

Support honest comparisons such as:

- model A vs model B
- prompt v1 vs prompt v2
- LLM_WITH_ODDS vs LLM_WITHOUT_ODDS
- MORNING vs PREMATCH_FINAL where the comparison question is valid
- primary vs historical challenger
- statistical baseline vs LLM

Do not claim causal conclusions when inputs differ materially.

For example:
MORNING vs PREMATCH has different information availability and is not a clean
model-only A/B test.

Document comparison limitations.

======================================================================
14. SUFFICIENT SAMPLE / INTERPRETATION
======================================================================

Do not produce strong “model X is better” conclusions from tiny samples.

Every experiment result must expose sample counts prominently.

Implement configurable minimum sample requirements for any status/interpretation
that would otherwise imply a usable winner.

Below the threshold:

result should remain INSUFFICIENT_SAMPLE / equivalent,
not a confident superiority claim.

Do not invent statistical significance.

If significance/uncertainty analysis is implemented, it must be mathematically
explicit, tested and honestly named.

A simple measurement-first implementation is preferred over dubious statistics.

======================================================================
15. IMPROVEMENT ANALYST
======================================================================

Implement an LLM-assisted Improvement Analyst behind the existing ModelRouter /
LLM provider abstraction.

Inputs may include bounded structured evidence from:

- aggregate evaluation metrics
- experiment results
- worst calibrated segments
- high-confidence misses
- source/data-quality failures
- model disagreements
- missing-data patterns
- latency/token/cost data when available

Do not dump the entire database into an LLM prompt.

Build a bounded structured analysis packet.

The Improvement Analyst produces PROPOSALS ONLY.

It cannot:

- change production prompt files;
- activate a prompt;
- edit routing configuration;
- change ranking thresholds;
- alter features;
- modify source priorities;
- edit application code;
- merge Git branches;
- deploy;
- auto-promote a treatment.

======================================================================
16. IMPROVEMENT PROPOSAL SCHEMA
======================================================================

Implement a strict structured ImprovementProposal contract.

At minimum:

- id
- title
- problem
- evidence summary
- evidence references / experiment IDs / evaluation IDs
- sample_size
- hypothesis
- proposed_change
- expected effect
- test_plan
- risks
- risk level
- affected component
- created_at
- analyst provider/model/prompt/config identity if LLM-generated
- status
- human action metadata where applicable

Allowed lifecycle from specification:

PROPOSED
APPROVED_FOR_EXPERIMENT
EXPERIMENT_RUNNING
REJECTED
PROMOTED
ROLLED_BACK

Model the state transitions explicitly.

Invalid transitions must fail.

======================================================================
17. HUMAN CONTROL
======================================================================

No automatic production promotion.

An ImprovementProposal may be:

- proposed automatically;
- reviewed by the user;
- rejected;
- approved for an experiment.

Approval may create/queue an EXPERIMENT only.

It must NOT change production.

If the system supports PROMOTED status in M9, it represents a human-recorded
decision/audit state only unless a later explicitly authorized production
change workflow exists.

Do not silently write production config.

A production promotion must require explicit user action outside the autonomous
analyst.

======================================================================
18. EXPERIMENT STATE MACHINE
======================================================================

Create deterministic experiment states appropriate to the implementation,
for example:

DRAFT
READY
QUEUED
RUNNING
SUCCEEDED
FAILED
CANCELLED
INSUFFICIENT_DATA

Use repository conventions if existing enums provide better names.

State transitions must be deterministic and auditable.

Retries must not create duplicate experiment identity/results.

======================================================================
19. FAILURE / PARTIAL EXECUTION
======================================================================

An experiment may encounter:

- missing frozen context
- non-replayable fixture
- model timeout
- malformed structured output
- abstention
- missing result
- unsupported settlement
- evaluation unavailable
- budget exhausted

Do not convert these into successful predictions.

Persist reason counts.

A partially completed experiment must truthfully distinguish:

requested
eligible
executed
predicted
settled
evaluated
paired

samples.

======================================================================
20. IMMUTABILITY / REPRODUCIBILITY
======================================================================

An experiment result must be reproducible from stored identities.

Record at least:

- experiment definition hash
- control/treatment identities
- prompt hashes
- model configs
- provider/models actually used
- context IDs/hashes
- evaluation version
- run timestamps
- sample manifest or equivalent immutable references

Do not rely on whatever model is currently configured later.

======================================================================
21. DATABASE
======================================================================

Design normalized SQLAlchemy models and Alembic migration(s) following existing
project conventions.

Likely logical entities include equivalents of:

- experiments
- experiment_arms / experiment_variants
- experiment_runs
- experiment_cases / replay cases or immutable manifest
- experiment_comparisons / summaries
- improvement_proposals
- improvement_proposal_events or equivalent audit history

Choose the simplest schema that preserves:

- immutable definition
- sample lineage
- execution state
- comparison output
- proposal lifecycle
- reproducibility

Do not duplicate giant MatchContext blobs.

Reference existing immutable rows.

======================================================================
22. EXPERIMENT IDEMPOTENCY
======================================================================

Equivalent execution of the same immutable experiment definition over the same
sample must not accidentally create duplicate external calls/results.

Use stable semantic identities.

Explicit rerun, when supported, must be distinguishable and auditable.

Concurrent duplicate queue execution must be safe.

======================================================================
23. CELERY / ORCHESTRATION
======================================================================

Experiment orchestration must remain deterministic.

Use appropriate existing queues.

LLM prediction work remains on the LLM path/queue.
Evaluation remains deterministic evaluation work.

Tasks should carry identifiers rather than giant payloads.

Do not put long replay work in FastAPI or Telegram handlers.

Support bounded batch processing so a large replay does not become one giant
fragile transaction.

======================================================================
24. API
======================================================================

Add a private/internal control plane appropriate for M9.

Capabilities should include equivalents of:

GET  /v1/experiments
GET  /v1/experiments/{id}
POST /v1/experiments
POST /v1/experiments/{id}/run

GET  /v1/improvements
GET  /v1/improvements/{id}
POST /v1/improvements/{id}/approve-experiment
POST /v1/improvements/{id}/reject

Exact route design should follow existing repository conventions.

Expensive work returns queued job/status rather than running synchronously.

No arbitrary provider API keys/config blobs in requests.

======================================================================
25. TELEGRAM
======================================================================

Keep Telegram thin.

Implement the useful M9 view/control portions from the Telegram spec.

`/improvements` should list proposals concisely.

Example:

#17 PROPOSED
Reduce reliance on H2H context
Evidence sample: 138
Risk: Low

Possible actions:

[ Details ]
[ Approve experiment ]
[ Reject ]

Experiment views may expose:

- hypothesis
- status
- control
- treatment
- sample size
- key metric deltas
- limitations

Do not dump huge JSON.

Do not let a single Telegram tap silently promote production.

Do not put LLM/business logic in handlers.

======================================================================
26. IMPROVEMENT GENERATION SCHEDULE
======================================================================

Specification allows periodic improvement analysis.

Implement automatic scheduling only if consistent with existing architecture.

Default should be conservative and configurable.

For example:
weekly improvement analysis may be opt-in/configurable.

Do not generate proposals repeatedly from identical evaluation evidence.

Use evidence/config identity for deduplication.

No notification spam.

======================================================================
27. EVIDENCE-BOUND ANALYST OUTPUT
======================================================================

Improvement proposals must reference actual measured evidence.

Validator must reject structurally invalid analyst outputs.

The analyst must not invent:

- sample size
- Brier values
- log loss
- calibration figures
- model cost
- experiment results

Measured fields should preferably be inserted deterministically from DB evidence
rather than trusted from free-form model prose.

The LLM proposes interpretation/hypothesis/test plan.

Python owns factual metric values and identities.

======================================================================
28. REPLAY WITHOUT HISTORICAL DATA
======================================================================

This is an explicit acceptance case.

If the requested period does not contain adequate frozen historical evidence:

Return a clear structured result such as:

NOT_REPLAYABLE
INSUFFICIENT_HISTORICAL_EVIDENCE

with counts/reasons.

Do not fetch today's provider data to fill the period.

Do not claim the experiment was performed.

======================================================================
29. TESTS — LEAKAGE / REPLAY
======================================================================

Add strong deterministic tests covering at minimum:

- exact frozen MatchContext reused
- later lineup excluded
- later odds excluded
- later research excluded
- final result never enters prediction input
- current mutable team/league data cannot change historical replay
- missing historical context → NOT_REPLAYABLE
- context projection does not mutate original
- WITH_ODDS / WITHOUT_ODDS deterministic projection
- exact prompt/model/config identity preserved
- feature version identity preserved
- original production PredictionRun unchanged

Historical leakage tests are release blockers.

======================================================================
30. TESTS — EXPERIMENT FAIRNESS
======================================================================

Cover:

- same eligible contexts for paired control/treatment
- excluded sample counts visible
- treatment failure does not silently remove the control from full-arm metrics
- paired metric population is explicit
- abstention preserved
- missing result preserved
- sample size boundaries
- insufficient sample state
- deterministic comparison ordering
- missing baseline reduces baseline n rather than inventing values

======================================================================
31. TESTS — IMPROVEMENT PROPOSALS
======================================================================

Cover:

- strict structured output
- malformed analyst output safely rejected
- measured evidence cannot be overwritten by LLM hallucinated values
- proposal dedup where evidence identity is same
- valid state transitions
- invalid state transitions rejected
- approve → experiment authorization only
- reject works
- no production prompt/config mutation
- no automatic promotion
- actual analyst provider/model/prompt metadata persisted

======================================================================
32. TESTS — IDEMPOTENCY / CONCURRENCY
======================================================================

Cover:

- duplicate experiment queue request
- duplicate experiment worker execution
- explicit rerun identity
- concurrent proposal generation
- experiment partial failure
- retry after transient LLM failure
- no duplicate external calls for already completed case
- stable sample manifest

======================================================================
33. MOCK END-TO-END M9
======================================================================

Create a completely keyless deterministic path:

historical frozen MatchContexts
→ experiment definition
→ control MockLLM
→ treatment MockLLM
→ M7 validation/probabilities
→ existing M8 settlement/evaluation
→ experiment comparison
→ Improvement Analyst mock
→ ImprovementProposal
→ approve-for-experiment/reject workflow
→ API
→ Telegram/test transport

CI must require zero external API calls.

======================================================================
34. DO NOT OVERCLAIM
======================================================================

M9 acceptance does NOT prove:

- the football predictor is profitable;
- one real model is superior;
- the prompt is calibrated;
- an improvement proposal is correct;
- a challenger should replace primary;
- live providers behave perfectly.

Separate infrastructure correctness from empirical forecasting performance.

======================================================================
35. SCOPE BOUNDARIES
======================================================================

DO implement:

- replay planning
- leakage-safe historical replay
- experiment definitions
- control/treatment execution
- immutable experiment persistence
- model/prompt/variant comparisons
- experiment metrics using M8
- improvement analyst
- structured proposals
- human-controlled proposal lifecycle
- CLI
- private API
- thin Telegram integration
- deterministic tests

DO NOT implement:

- automatic production prompt mutation
- automatic model promotion
- automatic feature changes
- arbitrary ensemble weighting
- dynamic staking
- live betting execution
- M10 deployment work
- Hetzner
- Hermes
- production infrastructure

======================================================================
36. ACCEPTANCE GATES
======================================================================

Run complete repository gates:

uv run ruff check .
uv run ruff format --check .
uv run mypy src

unit suite
integration suite
full pytest

Alembic:
fresh DB → upgrade head
downgrade -1
upgrade head
alembic check

Verify populated accepted M8 → M9 migration path.

docker compose config -q
docker compose --profile telegram config -q

secret sanity
git diff --check

Push build/m9.

Wait for GitHub Actions on the exact remote HEAD.

All jobs must be SUCCESS.

======================================================================
37. PROJECT MEMORY
======================================================================

Maintain continuously:

docs/CURRENT_TASK.md
docs/IMPLEMENTATION_STATUS.md
docs/AI_WORKLOG.md
docs/REVIEW_HANDOFF.md

AI_WORKLOG remains append-only.

Record any ADR required by experiment/replay semantics.

======================================================================
38. FINAL STATE
======================================================================

At completion:

- remain on build/m9
- push build/m9
- main remains accepted M8:
  490227ac8e27ca4c8870891277fd8783d8a7f1af
- v0.9-m8 remains unchanged
- M9 NOT merged
- M10 NOT started
- working tree clean
- exact remote build/m9 CI green

STOP for independent review.

Do not merge/tag M9 yourself.

======================================================================
39. FINAL HANDOFF
======================================================================

Return:

1. exact origin/build/m9 HEAD SHA
2. accepted M8 base confirmation
3. state-doc drift correction confirmation
4. Experiment/Replay architecture
5. database/migration changes
6. historical evidence authority
7. anti-leakage guarantees
8. experiment identity/idempotency
9. control/treatment pairing semantics
10. non-replayable behavior
11. CLI usage
12. model/prompt/variant comparison support
13. baseline comparison support
14. Improvement Analyst architecture
15. ImprovementProposal schema
16. lifecycle/state transitions
17. proof that analyst cannot mutate production
18. API endpoints
19. Telegram changes
20. automatic schedule behavior if any
21. unit test count/result
22. integration test count/result
23. full pytest result
24. Ruff/format/mypy
25. Alembic verification
26. Compose verification
27. exact GitHub Actions run ID and exact HEAD SHA
28. any real external LLM calls performed
29. known limitations
30. confirmation M9 not merged
31. confirmation M10 not started
32. confirmation zero deployment / Hetzner / Hermes interaction

Then STOP.