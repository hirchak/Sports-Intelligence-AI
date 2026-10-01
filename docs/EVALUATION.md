# M8 — deterministic result truth, settlement and forecast measurement

Scope: [M8_SCOPE.md](M8_SCOPE.md). Methodology decision: [ADR 0011](adr/0011-m8-result-authority-and-measurement.md).
LOCAL DEVELOPMENT ONLY. No M9, fitting, model promotion, prompt changes, staking or deployment.

## Result authority and flow

The configured `SportsDataProvider.get_results_by_date()` makes one physical UTC date request.
API-Football uses `/fixtures?date=...&timezone=UTC`, without a status filter so postponed/cancelled/
abandoned/anomalous states remain observable. Provider score `fulltime` supplies regulation; `goals`,
extra time and shootout scores never substitute. Contract source:
[official API-Football guide](https://www.api-football.com/news/post/how-to-get-started-with-api-football-the-complete-beginners-guide).
No fixture-by-fixture calls or settlement vendor logic. Mock responses are explicitly synthetic.

Only tracked, mapped fixtures beyond expected finish + grace are processed. Date worker resolves provider
IDs in one query. P0 quota reservation precedes **each physical attempt**, including retries. Success/failure
ledger includes headers, timings and safe classes; raw bodies deduplicate via existing raw payloads and
provider observations. Malformed contracts are non-retryable, ledger/job audited, and never settled.
Timeout/transport/5xx/429 retry up to `RESULT_RETRY_LIMIT`, with bounded exponential delay (2/4 seconds
default). Retry-After up to 30 seconds is respected; longer or invalid waits defer to a later scan
without an early request. Auth/config/mapping/contract errors do not retry. Local settlement has no provider retry logic.

Redis date lock coalesces calls; winner caches pass for scan interval, loser never bypasses lock.
Confirmed FT, regulation-available AET/PEN, cancelled and abandoned fixtures need no normal refetch.
Postponed/live/unknown stay eligible for later passes. Explicit local correction uses
`enqueue_result_date(factory, settings, day, now=..., force=True)`; force passes are still job-deduplicated.
No automatic correction polling for confirmed matches. Conflicting provider authority fails explicitly.

Fixture row lock serializes append-only result versions. Same latest content reuses that version;
A→B→A creates three versions. Every version includes provider fixture ID, normalized status, provider status,
normalizer/source hash, observation time, raw payload FK, scores, predecessor FK and created_at.
Older correction observations are rejected. Results observed before kickoff are rejected.

Statuses: FINAL, AFTER_EXTRA_TIME, AFTER_PENALTIES, POSTPONED, CANCELLED, ABANDONED, UNFINISHED, UNKNOWN.
Malformed score/state combinations fail rather than guessing from live/partial scores.

## Settlement

`regulation_v1`: 90 minutes plus added time only. Extra-time/shootout goals are retained for provenance.
FINAL needs both integer regulation scores; AET/PEN without regulation remains UNSETTLED.
Postponed/live/unknown → UNSETTLED. Cancelled/abandoned → VOID (analytical refund convention).

For regulation h:a:

| Selection | Winning event |
|---|---|
| HOME / DRAW / AWAY | h>a / h=a / h<a |
| HOME_OR_DRAW / HOME_OR_AWAY / DRAW_OR_AWAY | h>=a / h!=a / h<=a |
| OVER_1_5 / UNDER_1_5 | h+a>=2 / h+a<2 |
| OVER_2_5 / UNDER_2_5 | h+a>=3 / h+a<3 |
| BTTS_YES / BTTS_NO | both score / either score is zero |

WIN/LOSS/PUSH/VOID/UNSETTLED are canonical outcomes. Half-goal totals never push under integer football
scores. Settlement identity = market_prediction_id + result_id/version + policy version; unique constraint
and row lock protect retries/concurrency. Corrections append new settlements; old rows remain intact.
Every SUCCEEDED M7 selection is settled, independent of display. ABSTAINED has no market forecasts.
Catch-up queries only latest results with missing settlements, including later explicit M7 reruns.

## Metric definitions and populations

`evaluation_v1` + `metrics_v1` freezes config, filters, cutoff, source run/result/settlement/baseline IDs.
Exact requested identity reuses the immutable run; another cutoff/config is a distinct run.
Rows/results/settlements observed/created/settled after cutoff are excluded. Period filters use forecast
`as_of`, [start,end); result-list periods use fixture kickoff. No M6/M7 evidence is updated.

- Binary Brier: mean((p-y)^2) across eligible WIN/LOSS selections; N counts probability rows.
- Multiclass 1X2 Brier **sum**: mean(sum of three squared errors), range 0..2. Only complete 1X2 vectors.
- Binary natural-log loss: mean(-y log(p')-(1-y)log(1-p')); separate 1X2 loss=-log(p'_realized).
  p'=clip(p,epsilon,1-epsilon) ONLY for computation. Default epsilon=1e-15, configurable with a float64-safe
  minimum 2.220446049250313e-16 and maximum <0.01. Stored probabilities are unchanged.
- Calibration deciles [0,.1), ... [.9,1], configurable increasing boundaries with explicit final 1 inclusion.
  Each bucket persists bounds, n, mean probability, event frequency, signed gap=mean_p-frequency.
- ECE = sum(n_bucket/N * abs(gap)). Empty buckets have null means, not fabricated frequencies.
- Sharpness = mean((p-.5)^2), range 0..0.25. It measures probability dispersion about .5, not correctness.
- Forecast coverage = SUCCEEDED/(SUCCEEDED+ABSTAINED); abstention = ABSTAINED/same denominator.
  FAILED and QUEUED/RUNNING are separately counted. Valid NO_BET contributes to SUCCEEDED.
- Display coverage = successful runs with persisted displayed candidates / successful runs.
  Coverage is available at run-dimensional scopes, not attributed to markets/prices for an abstaining run.
- Displayed hit rate = WIN/(WIN+LOSS) among displayed candidates. Forecast accuracy still includes all
  twelve supported selections. Related/complementary selections are correlated, not independent matches.
- Research fixed stake = **1 unit**, WIN=odds-1, LOSS=-1, PUSH/VOID=0, UNSETTLED unavailable.
  ROI=sum(net return)/count(WIN+LOSS+PUSH), VOID refunded/excluded. No staking strategy.
- Mean captured odds and prediction-time EV use stored ranked-candidate values and individual n.
- Optional `closing_snapshot_ids` explicitly identifies existing pre-kickoff snapshots for a **price proxy**:
  captured_odds/selected_closing_odds-1, same fixture/bookmaker/canonical selection, later than captured price,
  no later than historical kickoff/cutoff. No automatic identification as true closing, fetch or fabricated
  value. Missing comparator remains null/n=0. Snapshot IDs/config are included in evaluation identity.
- Mean latency/input/output tokens where M7 supplied them; absent usage/cost remains absent.
  M7 has no monetary price/cost records, so M8 makes no billing-cost estimate.

Every metric has its own sample_size. Empty measures are null/n=0. Invalid probabilities, odds, outcomes
and nonfinite numbers fail the evaluation with a safe operational error; no silent row dropping.

## Segmentation and baselines

PRIMARY/CHALLENGER, WITH_ODDS/WITHOUT_ODDS and LLM/market/statistical partition **every** aggregate.
No averaging, ensemble or winner selection. Persisted M7 baselines are read as-is; missing probabilities
reduce evaluated n and expose `missing_baseline_probabilities`. No retroactive baseline recomputation.
WITHOUT_ODDS also removes research free text, so it is not a pure causal odds-anchoring experiment.

Single-facet persisted summaries: league, market, selection, captured odds bucket ([1,1.5), [1.5,2),
[2,3), [3,5), [5,inf), missing), model config ID, provider/model, prompt semantic version, phase,
M6 quality band, confidence, baseline version. Multiple simultaneous filters are supported through a
scoped queued evaluation; summary reads that persisted scope. Each metric and calibration bucket retains n.
There is no warehouse/cross-product materialization or automatic statistical significance claim.

## Automatic local operation and API

Opt-in `RESULT_SCAN_ENABLED=true` enables Beat `evaluation.result_scan`, default hourly; minimum 15 minutes.
Default expected finish=120 minutes, grace=30, lookback=7 days, so yesterday and subsequent recovery passes
are supported. Disabled by default; M8 development does not activate existing local provider schedules.
Scan enqueues stable date/slot/config jobs → sports_io collector → result persistence → local settlements
→ queued 7d/30d/all-time evaluations on evaluation queue. No Telegram clicks, sports/LLM calls after results
are local, or LLM use anywhere in M8. Failures are visible in Job/JobAttempt and external ledger.

- GET `/v1/results`: latest version, date/league filters, limit<=100, offset.
- GET `/v1/results/{fixture_id}`: latest and last 20 immutable versions.
- GET `/v1/results/{fixture_id}/settlements`: latest-version settlements; optional run_id; limit<=200.
- POST `/v1/jobs/evaluate`: period=7d/30d/all, filters, optional config and cutoff → 202 UUID job/run.
- GET `/v1/evaluations/summary`: persisted summary/calibration, period or explicit range, optional evaluation_id,
  role/variant/baseline, league/market/selection/model/provider/config/prompt/phase/quality/confidence/odds filters,
  group_by facet; bounded group pagination (limit<=50). Never synchronous historical evaluation.

Telegram keeps existing Russian UI copy, uses allowlist middleware and backend only:
`/stats`, `/results`, `/evaluate`, period/segmentation buttons, recent results and settlement view.
Sample sizes accompany all measurements. No significance, profitability or best-model language.

## Verification and limitations

Tests run against Compose Postgres and isolated *_test DB / Redis db15. Full keyless E2E uses an explicitly
advanced synthetic clock after the forecast, so real elapsed hours and external keys are unnecessary.
Provider HTTP contracts use injected transports. Live result collection and new live Telegram interaction
are unverified; zero live result/LLM calls are part of this M8 implementation run.

M8 is research infrastructure, not evidence of forecasting skill. Independent review still required.
Existing crash/lost-broker recovery is operational/manual; M8 does not add an outbox platform.
A failed immutable evaluation needs a new cutoff/request rather than mutating its historical failure.
Confirmed results need explicit correction passes. A provider-normalization semantic change requires a new
normalizer version/review. Unrecognized awarded/walkover status is UNKNOWN/UNSETTLED.
