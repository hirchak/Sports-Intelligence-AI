# ADR 0011 — M8 result authority and reproducible measurement

Status: accepted for local M8 implementation. No M9 or deployment authority.

Results belong to the configured SportsDataProvider, fetched once per UTC kickoff date.
They never update prediction/context/feature evidence. Append immutable numbered fixture
result versions under a fixture lock; repeat of the latest normalized observation reuses it.
Corrections (including A→B→A) append versions; old settlements/evaluations remain intact.
Conflicting providers require an explicit authority change, not implicit last-writer wins.

`regulation_v1` uses 90 minutes plus added time, never extra time or shootout goals.
FT/AET/PEN require an explicitly supplied regulation score. Missing regulation is UNSETTLED;
malformed/impossible contracts fail safely with request/raw evidence and job failure auditing.
Postponed, live, unfinished and unknown are UNSETTLED; cancelled and abandoned are VOID.
These are analytical rules, not bookmaker-specific payment promises. Unsupported policy fails.

`metrics_v1`: binary Brier=(p-y)^2 per selection. Multiclass 1X2 Brier is the SUM
of three squared errors (range 0..2), separately named. Binary natural-log loss clips
only metric inputs to [epsilon,1-epsilon], epsilon=1e-15 by default. 1X2 natural-log
loss=-log(clipped probability of the realized class), separately named.
Calibration uses [lower,upper), with 1 included in the final bucket. Default deciles;
ECE=sum(n_bucket/N * abs(mean_p-event_frequency)). Sharpness=mean((p-0.5)^2), range 0..0.25.

Coverage=successful terminal runs/(successful+abstained); abstention has the same denominator.
FAILED and in-flight runs are separate counts. NO_BET is successful. Candidate coverage=successful
runs having displayed candidates/successful runs. Probability/candidate filters cannot invent
market attribution for ABSTAIN: run-level coverage is reported only at run-dimensional facets.

Candidate hit rate uses WIN/(WIN+LOSS). Fixed research stake is exactly one unit:
WIN=odds-1, LOSS=-1, PUSH=0, VOID=0, UNSETTLED unavailable. ROI=sum(net return)/
count(WIN+LOSS+PUSH); VOID is refunded and excluded. Average odds and captured EV are
reported with their own sample sizes. No dynamic staking.

Evaluation freezes config, filters, source cutoff and referenced run/result/settlement IDs.
Exact completed identity reuses an immutable run. Cutoff is observation availability, not kickoff;
period is forecast as_of. Never use a result/version observed after cutoff. No implicit baseline
fill/recompute. Role, variant and baseline always partition aggregates. Missing baseline stays missing.
Cost absent from M7 stays absent; tokens and latency are measurements, not invented billing.
WITHOUT_ODDS also removes research text; comparisons are not pure causal odds experiments.
