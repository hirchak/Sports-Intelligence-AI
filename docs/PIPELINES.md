# Pipelines

M0–M10 independently accepted. LOCAL DEVELOPMENT ONLY; schedules are opt-in.

## Automatic-first path

Beat morning/refresh discovery → one date-level provider batch → normalized fixture evidence.
Pre-match scan plans fresh/due league/team/fixture collectors and optional research. Each collector
rechecks freshness under a coalescing lock before quota-budgeted fetch; shared team/league snapshots
avoid repeated requests. Missing/failed optional work stays explicit, not fabricated.
Required collectors ready → quality/features/MatchContext build → opt-in automatic prediction job.
Prediction loads frozen context/prompt/model/policy → bounded provider calls → strict validation → all
probabilities and candidates/filter reasons → persisted API → Telegram/test transport.

No provider or LLM calls occur inside scheduler planning or ordinary read screens. MORNING/PREMATCH
are separate historical contexts; reruns never overwrite old evidence. Phase/config/source-generation
semantic identities deduplicate repeated scans/completions and queued work.

## Post-match and improvement

Opt-in result scan selects due dates → P0 date-level result collection → append-only result versions →
regulation_v1 settlements against original probabilities/captured prices → 7d/30d/all frozen evaluations.
Confirmed completed results are not refetched automatically; explicit correction appends a new version.
Weekly opt-in improvement scan considers bounded existing comparisons; analysis cannot opt into live
calls by itself. Replay uses frozen historical contexts and result versions for evaluation only.
Human approval authorizes a compatible experiment; running it requires a separate explicit request.

## Control switches and assurance

SCHEDULER_ENABLED, discovery hours/minutes, SCHEDULER_PRE_MATCH_SCAN_ENABLED/cron,
PREDICTION_AUTO_ENABLED/variant, RESULT_SCAN_ENABLED/interval/lookback, IMPROVEMENT_SCHEDULE_ENABLED;
live experiment and analyst switches are separate. Disabled optional search/odds degrade visibly.
Physical retry/repair budgets, quota reserves and no-malformed-publication policies apply in workers.

The acceptance suite simulates three days of discovery slots and duplicate scans at frozen time;
existing collector/context/prediction/result/improvement regressions verify the downstream boundaries.
Actual restart/outage tests use a bounded local queued workload. They do not empirically prove multiple
unattended days. Lost dispatch or interrupted unknown paid calls require operator inspection/rerun.

Full keyless command: `make acceptance-mock` (isolated *_test DB/Redis). See LOCAL_DEVELOPMENT,
PREDICTIONS, EVALUATION and EXPERIMENTS for precise formulas, identities, gates and known limitations.
