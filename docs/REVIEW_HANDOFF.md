# M9 implementation handoff — local gates, delivery in progress

**Branch:** build/m9. **Accepted M8 main/tag base:** `490227ac8e27ca4c8870891277fd8783d8a7f1af` / annotated `v0.9-m8`.
M8/M8.1 PASS/ACCEPTED; PR #10 merged; exact merged-main CI `36981326405` all three jobs SUCCESS.
At startup after fetch, build/m9 == origin/build/m9 == origin/main == v0.9-m8^{}. Post-M8 state-doc drift
corrected before implementation. Historical worklog receipts preserved; current M9 authority is this section.

Scope: [M9_SCOPE.md](M9_SCOPE.md). Architecture/method/CLI/API/limits: [EXPERIMENTS.md](EXPERIMENTS.md),
[ADR 0012](adr/0012-m9-frozen-replay-and-human-proposals.md).

Implemented: ten isolated experiment/analyst/proposal tables, Alembic 0014, immutable DB-protected identities;
exact frozen-context planning/replay; paired/full M8 comparisons; historical PRIMARY/CHALLENGER reuse;
bounded ModelRouter analyst and deterministic evidence; human authorization/rejection/audit-only promotion;
CLI, internal API, thin allowlisted Telegram; weekly scan disabled, zero notifications/live execution.

Verified locally: **873 unit + 200 integration PASS**. **Full pytest: 1073 PASS**, 64.93s. Ruff/format (245 files),
strict mypy (168 source files), fresh DB→head→down -1→head→check and populated accepted M8→M9 cycle
PASS with no drift; Compose default/dev/Telegram PASS; 325 working-file/history secret sanity PASS;
git diff --check PASS. Accepted migrations 0001–0013 and M7 prediction modules/production prompt remain byte-identical.
M8 closing-price formula is extracted into a shared pure function, preserving measurement definitions. Synthetic unit/integration fixtures
are infrastructure evidence only. Actual task wrappers and collectors→M6→M7→M8→M9 keyless E2E PASS.

Remaining: scoped commit/push, exact remote HEAD CI SUCCESS, clean-tree review STOP.
M9 NOT MERGED/TAGGED; M10 NOT STARTED. LOCAL DEVELOPMENT ONLY. Zero paid/live LLM calls;
zero deployment / Hetzner / SSH / Hermes interaction. No profitability/model-superiority/proposal-merit claim.
Operational limits: interrupted paid-call claims/lost broker delivery require inspection/explicit rerun;
no fitted statistics/ensembles, closing proxy only from explicit archived snapshots, monetary cost unknown; no new live Telegram smoke.

---

# Historical M8 handoff (superseded closeout wording retained as prior evidence)

# M8 finalization handoff — independently ACCEPTED

**Independent verdict (owner-supplied): M8 / M8.1 = PASS / ACCEPTED.**
**Accepted origin/build/m8 HEAD:** `f8863a8065df307ff47552750d900accad1ab666`.
**M8.1 implementation:** `248e6b190faf4d5b232b7f6eb60a67510c57ae86`.
**Final accepted exact-head CI:** [36977001070](https://github.com/hirchak/Sports-Intelligence-AI/actions/runs/36977001070), all 3 jobs SUCCESS.
**Accepted base/main:** `4eff88bcaaac387ec047d50575d25b8135baa567` / `v0.8-m7` until merge.
No remaining M8 blockers. Owner-authorized PR/merge/tag/build/m9 closeout in progress.
M8 is not merged/tagged yet. M9 is NOT STARTED. LOCAL DEVELOPMENT ONLY; zero deployment, Hetzner, SSH or Hermes interaction.

## M8.1 acceptance fix

Blocker: newer broad evaluation could shadow older scoped evaluation and return empty SUCCEEDED groups.
Summary selection now rejects unsupported restrictions/shapes before choosing; prefers more requested
scoped dimensions, then latest source_cutoff, with stable UUID tie-break. Base + one unscoped facet is
answerable; group_by consumes that facet. No compatible scope → not_available with explicit reason.
Read-only bounded pages, no formula/schema/provider/M7/settlement changes or synchronous recalculation.

Regressions in `tests/integration/test_m8_summary_selection.py`:
A older league+market scope vs newer automatic broad; B league scope+market group_by vs newer broad;
C broad base/single filter/group_by still works; D unsupported multi-dimensional/explicit broad ID safely
not_available. Fifth test checks most-specific scope, latest equal-scope cutoff and a valid partial scope.
Before fix: 4 FAIL / 1 PASS. After fix: all 5 PASS with persisted numerical metrics/sample sizes checked.

M8.1 local gates: **839 unit + 151 integration = 990 full pytest PASS**, 43.67s;
Ruff/format clean (228 Python files), strict mypy clean (155 source files). Alembic fresh→head→down -1→
head→check on isolated sports_intel_m81_test PASS; populated migration tests PASS; no schema drift or
migration edits. Compose default/dev/Telegram PASS; working-file/history secret sanity PASS (302 files).
M8.1 verification COMPLETE. Exact implementation HEAD `248e6b190faf4d5b232b7f6eb60a67510c57ae86`;
[CI 36976617246](https://github.com/hirchak/Sports-Intelligence-AI/actions/runs/36976617246) **all jobs SUCCESS**:
lint/type/unit, Postgres/Redis integration, Compose validation. Owner verdict M8 / M8.1 PASS / ACCEPTED
supersedes this historical review note.
The accepted owner verdict and exact accepted CI are recorded at the handoff header.

M8 scope/methodology: [M8_SCOPE.md](M8_SCOPE.md), [EVALUATION.md](EVALUATION.md),
[ADR 0011](adr/0011-m8-result-authority-and-measurement.md). Historical M8 contract/gates below are unchanged.

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
- Reviewed M8 delivery d56aa3620f728eae500a1d95bce167c986d3dfda: [36936656574](https://github.com/hirchak/Sports-Intelligence-AI/actions/runs/36936656574),
  all jobs SUCCESS. That M8 delivery verification is complete; it does not independently accept M8.1.

Next: open and merge build/m8 → main using a merge commit; verify merged-main CI; tag `v0.9-m8` on that
merge commit; create/push empty `build/m9` from the same SHA; STOP. Do not implement M9.

## Completed M8.1 receipt

Implementation: `248e6b190faf4d5b232b7f6eb60a67510c57ae86`. CI [36976617246](https://github.com/hirchak/Sports-Intelligence-AI/actions/runs/36976617246)
SUCCESS on that exact SHA; CI logs confirm 839 unit + 151 integration, mypy 155 source files and clean migrations.
Final local full pytest: 990 PASS. Documentation closeout is the only subsequent change.
STOP for review; M8/M8.1 not merged/tagged, M9 not started, LOCAL DEVELOPMENT ONLY.

## Owner-authorized finalization checklist

- Accepted branch/base/CI identifiers are at the top of this file.
- Open `build/m8` → `main`; wait for all PR checks; merge with a merge commit (repository precedent: PR #9).
- Verify final `main` equals the PR merge SHA and its Actions jobs succeed.
- Create annotated `v0.9-m8` pointing to that exact merged `main` SHA, then push the tag.
- Create and push `build/m9` from the same SHA; verify `origin/build/m9 == origin/main == v0.9-m8^{}`.
- Stop: M8 MERGED / TAGGED / ACCEPTED, M9 NOT STARTED, LOCAL DEVELOPMENT ONLY.
