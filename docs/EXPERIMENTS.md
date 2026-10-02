# M9 — controlled experiments, frozen replay and proposal-only improvement

Scope: [M9_SCOPE.md](M9_SCOPE.md); design: [ADR 0012](adr/0012-m9-frozen-replay-and-human-proposals.md).
LOCAL DEVELOPMENT ONLY. M9 delivery requires independent review; no M10, deployment or production promotion.

## Architecture and persistence

Frozen MatchContext → immutable ExperimentDefinition/FrozenArm → ReplayPlanner → ordered run manifest →
bounded sequential PredictionEngine replay on `llm` → deterministic M8 settlement/aggregation on
`evaluation` → immutable comparison → bounded ModelRouter analyst → ImprovementProposal → human action.

Alembic **0014**, ten normalized tables:
`experiments`, `experiment_arms`, `experiment_runs`, `experiment_cases`, `experiment_predictions`,
`experiment_calls`, `experiment_comparisons`, `improvement_analyses`, `improvement_proposals`,
`improvement_proposal_events`. Existing M0–M8 models/migrations and prediction/evaluation rows are preserved.
No giant context duplication. Cases reference context/feature/quality/source identities and result versions.
Database triggers protect definitions, arms, manifests, comparisons, factual proposal evidence and analyst
requests against update; status/telemetry are separate mutable lifecycle fields. UUID FKs and unique hashes
protect semantic identity. M9 downgrade removes only M9 tables/function; no accepted data backfill.

## Historical authority and planning

Prediction input is the exact stored, hash-verified MatchContext, through existing deterministic M7
WITH_ODDS/WITHOUT_ODDS projection. Verify feature/quality references, feature schema/content, as_of,
phase, metadata/odds/research timing and persisted source identities. Reference tables must be historical
snapshot tables; cross-fixture and future references fail closed. No current collectors/provider calls,
team/league metadata reconstruction, final result or evaluation in model input. Original context is never
updated. WITHOUT_ODDS also masks research; this is not a clean causal odds-only experiment.

Scope is frozen prediction **as_of [start,end)**, configured phase, leagues and markets. Exact `context_ids`
or `fixture_ids` can bound the population. More than one explicitly selected context per fixture/phase is
refused; each fixture contributes at most one pair. Automatic selection uses latest frozen as_of, then
stable UUID. Mutable fixture kickoff is used only to inventory discovered matches lacking contexts; that
inventory never supplies forecast evidence. Maximum requested population is 1000; maximum context rows
read is 10000. Oversized plans require narrowing scope. Scope/manifest excludes rather than fabricates.

Missing context/features/quality/reference, mismatched hash/version/time, unavailable historical forecast,
future evidence or missing explicit context → `NOT_REPLAYABLE`, counted reason. Entirely empty/unavailable
historical period → `INSUFFICIENT_HISTORICAL_EVIDENCE` plan and `INSUFFICIENT_DATA` completed run.
No current sports/research API backfill. Fixture cap exclusions are counted separately.

Results are selected by M8 observation/creation cutoff and frozen as result IDs in the manifest, for
**evaluation only**. Missing results remain missing; corrections require a new explicit run/manifest.
Later result rows cannot change an existing comparison.

## Frozen model/prompt comparison and identity

Arms select configured prediction routes; APIs accept route names and `default`/`candidate` prompt labels,
not provider credentials, arbitrary URLs/model-config blobs or filesystem paths. Explicit configured
manual routes can provide additional model/config comparisons. Freeze route/model configs, prompt
content/version/hash, prediction/ranking policy and evaluation policy at definition creation.
Candidate default is `prompts/experiments/1.1.0.txt`, separate from production prompt.

`source=replay` executes that frozen route. `historical_primary` / `historical_challenger` reuse an original
terminal M7 forecast on the selected exact context and variant. Plan records original prediction ID and
complete detail hash; worker verifies it, copies only experiment output/metadata, and makes no new LLM
call for that arm. Actual historical provider/model/prompt/config/telemetry identities are preserved.
Missing recorded forecast is unavailable. Baselines remain market/statistical/LLM separately named.

Definition hash covers scope, hypothesis, controls and all frozen arm identities. Material changes create
new experiment identity. Run identity covers definition + ordered sample/result manifest + optional
explicit rerun UUID. Repeated ordinary request returns the initial run/manifest, including failure; an
explicit rerun UUID is distinct and auditable. Duplicate definition/run requests and workers do not repeat
completed arm calls. Run lock is held on one explicit DB connection; per-output CAS protects redelivery.

Sequential batches (default five fixtures, max twenty) commit per arm. Effective experiment concurrency
one. Every physical retry/repair reserves DB budget and records request metadata. Experiment total and
per-arm route call caps apply to retries/repairs too; M7 policy daily cap is additionally checked.
A known transient failure may retry inside M7's bounded retry policy. Interrupted RUNNING output →
`NEEDS_INSPECTION`, FAILED run; never automatically reclaim a possibly paid call. Broker/worker crash or
lost dispatch requires inspection and explicit rerun; no new outbox/recovery platform is introduced.

Live replay requires all three: `APP_ENV=live_local`, `EXPERIMENT_LIVE_ENABLED=true`, and request
`live_opt_in=true`; worker checks again. Defaults and CI use MockLLM only. No live LLM calls were needed.

## Pairing, measurements and interpretation

Full-arm groups keep successful, failed and abstained outcomes independently. A treatment failure cannot
remove the control's full metrics. Paired metrics use the explicit intersection of successful, settled
selections on both fixture arms. Market scope is identical. Phase differences remain observational.

Counts prominently expose requested/eligible/non-replayable/excluded fixture cases, executed/predicted/
settled/evaluated **arm outputs**, paired **fixtures**, failed/abstained counts per arm, missing result and
sorted reasons. Each metric has its own n; twelve correlated markets do not count as twelve fixtures.

Reuse M8 `regulation_v1`, `Aggregate`, `aggregate_values`, calibration and metric formulas, including
binary Brier/log loss, separately named multiclass 1X2 scores, ECE, sharpness, coverage/abstention,
display coverage, hit rate, fixed-one-unit research ROI, captured odds/EV, latency/tokens when known.
Market/statistical baselines use the successful control population; unavailable probabilities reduce n
and increase missing-baseline counts. No ensembles, fitted weights, new metric conventions or invented
monetary cost. Closing-price proxy is explicitly null/n=0 in M9 comparisons; production M8 can measure it
from explicitly supplied snapshots. Result/selection settlement manifest is retained with comparison.

Default `min_paired_fixtures=100`. Below threshold: `INSUFFICIENT_SAMPLE`; above: `MEASURED_ONLY`, never
usable-winner/significance/automatic promotion. Paired deltas mean treatment minus control and retain n.
Infrastructure tests do not establish profitability, calibration, real-model superiority or proposal merit.

## Improvement Analyst and human control

`improvement_analysis` route defaults to `mock-analyst-v1`. Freeze bounded packet, prompt/config/route at
queue time. Packet contains persisted comparison metrics/counts/IDs, at most six groups and twenty
calibration buckets per group; byte cap 50000. No whole database dump or tool/filesystem access.
Python inserts evidence summary/references, sample_size and actual analyst metadata. Strict LLM output
contains title, problem, hypothesis, proposed_change, expected_effect, test_plan, risks, risk_level and
an affected component only. Numeric prose/percent claims and extra measured/status/config fields are
rejected. This conservative qualitative validator avoids hallucinated measurements; it does not prove
that a qualitative proposal is correct. Malformed output fails job and creates no proposal.

Deduplicate by exact evidence + frozen analyst config/prompt hash. Job CAS prevents concurrent generation.
Daily analyst call cap defaults to ten, configurable 0–100; failure/usage metadata is retained separately.
Live analyst additionally requires LIVE_LOCAL + IMPROVEMENT_LIVE_ENABLED + explicit live opt-in.

Lifecycle:
`PROPOSED → APPROVED_FOR_EXPERIMENT → EXPERIMENT_RUNNING → PROMOTED → ROLLED_BACK`;
`PROPOSED`, `APPROVED_FOR_EXPERIMENT`, `EXPERIMENT_RUNNING` may be rejected. Invalid transitions fail;
duplicate same action is idempotent. Actor/reason/from/to/time are append-only proposal events.
Approval **creates an experiment authorization only**, not a worker call. Explicit run request moves the
linked approved proposal to EXPERIMENT_RUNNING. Default approval prepares the registered candidate
prompt against the prior scope; custom approval may supply a reviewed definition. It does not implement
arbitrary feature/source/ranking changes described in prose.

PROMOTED/ROLLED_BACK endpoint is **human-recorded audit only**, returns `production_applied=false`.
No production prompt activation, config writing, routing change, threshold/feature mutation, code edit,
Git merge or deployment operation exists in the analyst. Telegram has no promote action.

Optional Monday 09:00 (configured app timezone) weekly scan is **disabled by default**. When enabled it
considers up to ten recent comparisons, deduplicates identical evidence, and cannot opt into live calls.
No proposal notifications are sent; manual UI reads only. Schedule is infrastructure, not an activated run.

## CLI

Create a strict JSON definition, e.g. [experiment.example.json](../config/experiment.example.json).
Run locally against Compose Postgres/Redis:

```bash
uv run python -m sports_intelligence.replay \
  --experiment config/experiment.example.json \
  --from 2026-08-01 --to 2026-08-31 --mock --dry-run
```

CLI `--to` is inclusive UTC date, converted to exclusive following midnight. Plan is default. Definition
files permit phase/league/context/model-route/prompt/variant/max-fixtures/max-calls overrides and create a
new immutable identity; existing UUID definitions reject overrides.

```bash
uv run python -m sports_intelligence.replay --experiment <uuid> --mock --execute
uv run python -m sports_intelligence.replay --experiment <uuid> --mock --execute --rerun-key <uuid>
```

Execution prints counts and queues identifier-only worker work; no Telegram needed. `--dry-run` wins over
`--execute`; `--mock` refuses any non-mock replay route. A plan does not claim a forecast was executed.

## Internal API and Telegram

- GET/POST `/v1/experiments`; GET `/v1/experiments/{id}` (last twenty runs).
- POST `/v1/experiments/{id}/plan`; POST `/v1/experiments/{id}/run` → 202 job/run IDs.
- POST `/v1/experiments/runs/{id}/analyze` → 202 analyst job ID.
- GET `/v1/improvements`, GET `/v1/improvements/{id}` (evidence + human actions).
- POST `/v1/improvements/{id}/approve-experiment`, `/reject`, `/record-decision`.

Private loopback/Docker control plane follows existing API conventions; no public exposure/auth relaxation.
Lists support bounded limit/offset. Requests validate IDs/configs; no arbitrary execution/config inputs.
Telegram `/experiments`, `/improvements`, menu entries, paging, details, approve/reject call typed backend
methods only. Existing allowlist retained. Sizes and limitations appear with metrics; no giant JSON or
one-tap production promotion. Backend failures remain safe, text escaped.

## Verification evidence

See [REVIEW_HANDOFF.md](REVIEW_HANDOFF.md) for exact delivery SHA/CI receipt and complete gate counts.
Tests include frozen inputs and planted later rows; current team/league mutation; result exclusion;
paired/full fairness, abstentions/failures/budgets; historical identities; concurrent workers/proposals;
strict analyst facts; approval/rejection/audit-only promotion; CLI; actual task wrappers; API/Telegram;
full keyless real collectors→M6→M7→M8→M9 flow; fresh and populated accepted M8 migration cycles.
Real provider integrations/new live Telegram operation remain unverified; all model results here are synthetic.
