# M8 independent review handoff

Branch `build/m8`; accepted base/main `4eff88bcaaac387ec047d50575d25b8135baa567`, tag `v0.8-m7`.
Implementation/local gates complete; branch pushed. Final delivery requires all jobs SUCCESS on
exact final origin/build/m8 HEAD (receipt in completion message). M8 NOT merged or tagged.
M9 NOT started. LOCAL DEVELOPMENT ONLY; zero deployment, Hetzner, SSH or Hermes interaction.

Binding complete scope: [M8_SCOPE.md](M8_SCOPE.md). Methodology and limits:
[EVALUATION.md](EVALUATION.md), [ADR 0011](adr/0011-m8-result-authority-and-measurement.md).
Historical verdicts remain in IMPLEMENTATION_STATUS and append-only AI_WORKLOG.

## Implementation / evaluation contract

1. Result collector: SportsDataProvider.get_results_by_date, Mock/API-Football adapters; one UTC date batch,
   tracked provider ID resolution, finish/grace filtering; no fixture-by-fixture calls.
2. Quota: P0 reserve per physical attempt, safe success/error ledger, headers, raw content hash dedup and
   provider observations, Redis date coalescing/freshness; no hidden adapter retries in M8 path.
3. Truth: append-only fixture result versions with provider fixture identity, normalized/provider status,
   regulation/extra-time/shootout scores, observed_at, raw FK, source hash, predecessor and created_at.
   Supplied home/away provider IDs are checked against canonical mappings. A→B→A creates three versions.
4. States: FINAL/AET/PEN (normalized names), POSTPONED, CANCELLED, ABANDONED, UNFINISHED, UNKNOWN.
   `regulation_v1`: 90 minutes + added time only. No ET/shootout goals in market truth.
   Postponed/live/unknown/missing AET regulation remain UNSETTLED; cancelled/abandoned VOID.
5. All 12 canonical M7 selections: HOME/DRAW/AWAY; three double chance; O/U1.5, O/U2.5; BTTS yes/no.
   Integer scores make half-goal PUSH impossible; enum/return logic still represents PUSH.
6. Settlement idempotency: unique probability + result/version + policy; row locks; retry/concurrency
   cannot duplicate rows. Corrections append settlements. UNSETTLED audit rows do not count as settled.
   Displayed-only candidate settlements retain fixed-one-unit net return from original captured odds.
7. Evaluation identity: frozen config/version + filters/period + source cutoff, UUID manifest;
   exact identity reuses immutable run; changed config/cutoff creates distinct run. Worker writes atomic
   metrics/calibration/run success, never M6/M7. Bad rows fail operationally rather than silently dropping.
8. Binary Brier=(p-y)^2 mean. Separately named multiclass 1X2 Brier=sum of 3 squared errors, range 0..2.
   Binary log loss uses natural log and explicit computation-only epsilon (default 1e-15); separate 1X2 loss.
9. Calibration default deciles [lower,upper), final bucket includes 1; n/mean_p/frequency/signed gap.
   ECE=weighted absolute bucket gap. Sharpness=mean((p-.5)^2). Empty measures null/n=0.
10. Coverage=SUCCEEDED/(SUCCEEDED+ABSTAINED); abstention same denominator. Failures/in-flight separate.
    NO_BET valid. Display coverage includes candidates without results; hit/ROI use eligible settlements.
    Hit=WIN/(WIN+LOSS); WIN odds-1, LOSS -1, PUSH/VOID 0; ROI denominator WIN/LOSS/PUSH, VOID refunded.
    Average captured odds/EV retain their own n. Optional explicit persisted closing snapshot price proxy;
    missing comparator null/n=0; no historical later-price fetch, dynamic staking or profitability claim.
11. Persisted market/statistical/LLM baselines independent; missing baseline probabilities reduce n;
    no recomputation/fill/ensembles. PRIMARY/CHALLENGER and WITH/WITHOUT_ODDS always partition metrics.
    WITHOUT_ODDS removes research text too, so no pure causal odds-experiment claim.
12. Dimensions: time, league, market, selection, odds buckets, provider/model/config, prompt semantic
    version, role, variant, phase, quality band, confidence, baseline/version. Single-facet aggregates;
    multi-filter scoped queued evaluations supported. Latency/tokens where known; no invented money cost.
13. Automatic opt-in Beat date scan → sports_io worker → result persistence → local settlement →
    queued 7d/30d/all evaluations; finish=120m/grace=30m/hourly/lookback=7d defaults. No Telegram trigger
    dependency or LLM use. Already-confirmed results need no refetch; explicit force correction supported.
14. API: GET /v1/results, /v1/results/{fixture_id}, /v1/results/{fixture_id}/settlements;
    POST /v1/jobs/evaluate (202 queued); GET /v1/evaluations/summary reads persisted state, bounded filters/
    pagination. Telegram /stats, /results, /evaluate, periods and four segmentation shortcuts, settlement
    screen; allowlist retained, typed safe backend validation, samples always shown.
15. Schema: Alembic 0013, six normalized M8 tables listed in implementation status; existing M7 foreign
    keys, no giant context duplication, old migrations byte-identical to accepted base.

## Verification actually run (2026-10-02)

- Unit: **839 passed** (535 accepted M7 + 304 M8); integration **146 passed** (128 + 18 M8).
- Full `pytest -q`: **985 passed**, 33.32 seconds; isolated Compose sports_intel_m8_test + Redis db15.
- Ruff check / format check clean (227 files); mypy strict clean (155 source files).
- Migration: fresh sports_intel_m8_fresh_test→head→downgrade -1→head→alembic check PASS;
  populated 0012 M7→0013→0012→0013 integrity regression PASS, zero drift.
- Compose default/dev override/Telegram profile configs PASS. Secret sanity: 301 working files and
  Git history PASS (heuristic scan; no values printed). `git diff --check` PASS.
- Keyless E2E discovery→collectors→M6→MockLLM→ranking→M8 worker→settlement→evaluation→API→Telegram
  test transport PASS. Synthetic clock advances post-match; original FeatureSnapshot/MatchContext and
  M7 probability/ranking/odds/context hash regressions PASS. All settlement matrix/statuses and numeric
  examples, correction/concurrent retry, baselines/roles/variants, cutoff and combined filters tested.
- Existing M4 scan test used a UTC date with Warsaw-day planner and failed around midnight; changed
  test date to configured local_today only. CI exposed another existing discovery unit test comparing
  Warsaw day against UTC runner date.today; it now freezes a UTC→next-Warsaw-day boundary. Runtime
  schedulers unchanged. Legacy test stub/menu assertions updated for M8 interface/UI.
- Actual result scanner regression: repeated frozen scan queues date/evaluation work once, never calls
  a provider; worker uses the supplied scan time as reproducible evaluation cutoff.

## Live status / remaining limitations

**Live result provider calls: 0. Live runtime LLM calls: 0.** Real provider uses offline HTTP contract tests;
no new live Telegram smoke. No statistical significance, forecasting accuracy or profitability proven.
No fitted calibration/model promotion/weekly LLM analyst. M7 monetary cost data absent. Closing proxy
requires explicit existing snapshot IDs; confirmed corrections are manual/explicit. Existing crash/lost
broker delivery recovery remains operational/manual; no new outbox platform. Invalid result contracts
retain safe ledger/job failure, no unsafe partial settlement. See EVALUATION.md for exact definitions.

## GitHub Actions receipts

- Initial implementation HEAD a0c9332d2fca5fb8807d16015a7a331928dccbc4: run 36935276839;
  integration/Compose SUCCESS, unit FAIL due to the existing UTC/Warsaw date.today test.
- Corrected source HEAD 9de803022600ed761ec3af81c63b9091c47e3230: [36935653021](https://github.com/hirchak/Sports-Intelligence-AI/actions/runs/36935653021),
  **SUCCESS** for lint/type/unit, Postgres/Redis integration, and Compose validation.
- Final runtime-code/scanner HEAD 7cbf1a1148e162130a25828138f09e99f6963654: [36936292769](https://github.com/hirchak/Sports-Intelligence-AI/actions/runs/36936292769),
  **all three jobs SUCCESS** (lint/type/unit, integration, Compose). All code/local gates complete.
- Documentation-only closeout follows; its exact final origin/build/m8 HEAD and CI ID are returned in
  completion and can be resolved through `gh run list --branch build/m8`. Final delivery still requires
  all-job SUCCESS on that HEAD. Independent acceptance is not claimed.

Next: exact final HEAD Actions SUCCESS and clean tree, then STOP for independent review only.
