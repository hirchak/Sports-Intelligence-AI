# M10 local acceptance and deployment gate

Date: **2026-10-03, Europe/Warsaw**. LOCAL DEVELOPMENT ONLY.
**Independent verdict:** M10 implementation / local acceptance = **PASS / ACCEPTED**, supplied by the owner.
**Accepted review HEAD:** `76a221afbf06aeba464bbddbcfca315cf9b276d8`.
**Exact accepted CI:** [37083328438](https://github.com/hirchak/Sports-Intelligence-AI/actions/runs/37083328438), all three jobs SUCCESS.
**Verified implementation source:** `e137f4b5bfd19f1074644682cea49ee5932a0094`.
Exact source CI: [37082136185](https://github.com/hirchak/Sports-Intelligence-AI/actions/runs/37082136185),
all three jobs SUCCESS. Final subsequent delivery is documentation/evidence only; canonical delivery is
`origin/build/m10`. Exact delivery CI is verified after push before handoff, available in GitHub Actions
by that SHA (see REVIEW_HANDOFF). No source changes after this verified implementation.

**A. IMPLEMENTATION READY. B. LOCAL ACCEPTANCE VERIFIED. C. LIVE INTEGRATIONS PARTIAL.
D. DEPLOYMENT GATE: NOT READY.** Independent M10 verdict = PASS / ACCEPTED.
M10 PR #12 merged as `f289a82f2ae04ce455dc943f7d113470d4299e46`; PR CI `37107458873` and merged-main CI `37107597306` all SUCCESS.
Annotated `v0.11-m10` object `359c529b8424fd27d7dd82aad0a39c263e1a9bed` peels to exact merge SHA `f289a82f2ae04ce455dc943f7d113470d4299e46`. Acceptance receipt CI `37107325599` all SUCCESS.
A final docs-only record on main does not alter the tag target or implementation.

Every row below uses this date and the verified source above unless its evidence states a different
historical source. Final docs-only delivery does not change the verified implementation.

| Gate | Status | Exact command/test and evidence | Limitation |
|---|---|---|---|
| Clean bootstrap | PASS | fresh checkout of e137f4b; isolated sports-m10-review; `make bootstrap`; final-command-receipts JSON | local Docker Desktop, no clean physical-machine/server proof |
| Full keyless v1 E2E | PASS | `pytest tests/integration/test_m10_acceptance.py::test_complete_v1_no_network_reproducible_redis_loss_and_restore`; m10-final-e2e-backup.json | explicit MOCK providers/LLM/analyst; HTTP network transport refused |
| Live sports | NOT_VERIFIED | `python scripts/live_smoke.py`, m10-live-smoke.json | one bounded API-Football request, ProviderResponseError/API error; no accepted raw/normalized response |
| Live odds | NOT_VERIFIED | local credential presence check | no ODDS_API_KEY; no external odds request |
| Live search | PASS | `python scripts/live_search_smoke.py`, m10-live-search.json | one real Tavily query on explicit recorded MOCK fixture, one normalized document, zero claims; no forecasting merit |
| Real runtime LLM | NOT_VERIFIED | local route/key availability check | no configured real runtime LLM key/route; zero real LLM calls |
| Batch/no-N+1 | PASS | M4 integration shared standings/team/season/coalesce tests; discovery batch tests, full suite | provider-supported scopes only; existing per-event odds endpoint remains, no cross-event odds batch redesign |
| Prediction reconstruction | PASS | M10 context/prompt/model/probability references + native full-row fingerprints | application immutable persistence contract, not deeply frozen Python collections |
| No historical leakage | PASS | M6/M7/M9 planted future-row, mutable-metadata and frozen population regressions, full suite | absent historical evidence stays NOT_REPLAYABLE |
| Telegram test transport | PASS | bot access/callback/backend/menu, prediction/evaluation/experiment tests plus full M10 E2E | no Telegram network in keyless tests |
| Live Telegram smoke | PASS | m10-live-smoke.json: getMe + one allowlisted test message acknowledged | transport acknowledgement only; human receipt/complete live command flow not asserted |
| Provider failures | PASS | API-Football/odds/search HTTP contracts and collector ledger tests: timeout/429/5xx/malformed/auth | simulated error paths; real sports smoke separately unavailable |
| LLM failures | PASS | prediction engine/HTTP contracts + persistence tests: timeout/unavailable/malformed/probability/repair failure | injected providers, no real LLM acceptance |
| Settlement | PASS | M8 regulation_v1 matrix and corrections/idempotency, full suite | deterministic research policy, not bookmaker payment promises |
| Evaluation | PASS | M8 metrics/scope/cutoff/baseline regressions and M9 comparison, full suite | no profitability/calibration/superiority claim |
| Quota/degradation/cost | PASS | quota counters/headers/reserve/coalesce, runtime single HTTP attempts, cold odds ledger/cache/concurrent observers, LLM physical budgets, full suite | unknown monetary costs stay unknown; conservative aborted-lookup reservations and Redis loss require inspection |
| Scheduler simulation | PASS | M10 three-day frozen discovery slots ×duplicate; M4/M7 context/auto prediction; M8 repeated result scan; M9 weekly toggle/dedup | accelerated planning, no actual multi-day observation |
| Multi-day unattended empirical run | NOT_VERIFIED | no wall-clock multi-day run performed | explicit user acceptance allowed simulation; do not infer empirical proof |
| Restart/recovery | PASS | `python scripts/runtime_acceptance.py --project sports-m10-review --env-file /tmp/sports-m10-final/.env --base-url http://127.0.0.1:18003`, m10-final-runtime-resources.json | queued local mock work; lost broker dispatch/unknown paid RUNNING calls require manual inspection/rerun |
| Redis/Postgres outages | PASS | same runtime test, actual stop/start of isolated services;503 readiness/generic500/recovered unchanged forecast | does not prove automatic recovery of lost paid-call delivery |
| Telegram process restart | NOT_APPLICABLE | test transport/application startup validation; existing token already has a polling instance | no second concurrent polling process started; core remains stateless relative to bot |
| Backup/restore | PASS | `scripts/backup_restore.py` during complete E2E; m10-final-e2e-backup.json | native local temp restore, writers quiescent; no remote backup automation |
| Resource measurement | PASS | bounded12-job runtime batch; m10-final-runtime-resources.json | one synthetic fixture, snapshot not peak/target sizing |
| Private Compose/network | PASS | `scripts/compose_safety.py`; default/dev/Telegram/production-example config -q | future example only, zero deployment |
| Security pass | PASS | SECURITY findings/fixes, full security/access/failure gates, `scripts/security_check.py` | implementation-agent audit, not independent security acceptance |
| Secret/history sanity | PASS | known-local fingerprints + reachable Git blobs/private key/GitHub patterns; all reachable objects/working paths at final checkpoint | heuristic, not exhaustive entropy/dependency-vulnerability audit; no values printed |
| Unit | PASS | `uv run pytest -q -m 'not integration'`:909 PASS | keyless |
| Integration | PASS | isolated Docker *_test/Redis15, `pytest -q -m integration`:237 PASS | keyless, no skips |
| Full pytest | PASS | `pytest -q`:1146 PASS,73.44s | keyless, no skips |
| Ruff/format/mypy | PASS | `ruff check .`, `ruff format --check .`, `mypy src`:258 Python files/171 source files | final docs-only change does not affect code |
| Alembic fresh | PASS | fresh sports_intel_m10_fresh_test →head→down -1→head→check; command receipt | destructive cycle only on generated empty *_test DB |
| Populated migration | PASS | accepted M8→M9 regression + final-populated-migration.json; all 50 table fingerprints/identities unchanged; 0001–0014 byte-identical to v0.10-m9 | exact e137f4b populated head/check PASS, no drift |
| Exact source GitHub CI | PASS | e137f4b / 37082136185, all 3 jobs SUCCESS | source basis for M10 implementation |
| Acceptance receipt CI | PASS | commit b44d859b0bff2f6671cadc3563e2129d6a978fc6 / 37107325599, all 3 jobs SUCCESS | docs-only acceptance receipt |
| M10 PR checks / CI | PASS | PR #12, HEAD b44d859b0bff2f6671cadc3563e2129d6a978fc6 / 37107458873, all 3 jobs SUCCESS | merge used exact-head guard |
| Merged-main CI | PASS | merge `f289a82f2ae04ce455dc943f7d113470d4299e46` / run 37107597306, all 3 jobs SUCCESS | exact SHA |
| Annotated tag | PASS | `v0.11-m10` object `359c529b8424fd27d7dd82aad0a39c263e1a9bed`, peeled `f289a82f2ae04ce455dc943f7d113470d4299e46` | next tag in verified sequence |
| Independent M10 review | PASS / ACCEPTED | owner-supplied verdict on HEAD `76a221afbf06aeba464bbddbcfca315cf9b276d8`; CI 37083328438 | live/deployment gates remain separate |
| M10 PR / merge | PASS | PR #12; merge `f289a82f2ae04ce455dc943f7d113470d4299e46`; PR CI `37107458873`; merged-main CI `37107597306`, all jobs SUCCESS | docs-only receipt commits do not alter implementation |
| Annotated M10 tag | PASS | `v0.11-m10`; object `359c529b8424fd27d7dd82aad0a39c263e1a9bed`; peeled `f289a82f2ae04ce455dc943f7d113470d4299e46` | exact PR merge SHA |

## Exact M9 closeout

Accepted review HEAD 354c8f5ff27fe5427313a459937c17054073f36a / accepted CI 37061920047.
Acceptance receipt b0112a0dfb5328d8679526c17606805bd4bb9105 / CI 37070235725, all jobs SUCCESS.
PR #11, PR CI 37070527662 all SUCCESS; merged main 03789b7b7b4af2179271a7797faa754d48ad0d0d.
Merged-main CI 37070774858 all SUCCESS. Annotated v0.10-m9 object 952356ed97ef8f47e7cdbd8a58a58cdbfc229c76,
peeled 03789b7b7b4af2179271a7797faa754d48ad0d0d. Initial build/m10 remote/main/tag equality verified.

## Measured local capacity

Mac arm64, 8 CPUs, 8GiB host RAM; Docker Desktop VM limit 3.826GiB. Synthetic one-fixture batch:
12 new jobs/144 probabilities, concurrency 2,0.85s. Post-batch snapshots:

| Service | RAM | CPU snapshot |
|---|---:|---:|
| API |90.03MiB|0.33%|
| Worker |178.1MiB|0.35%|
| Beat |73.79MiB|0.00%|
| Postgres |23.46MiB|0.10%|
| Redis |4.555MiB|0.96%|

DB 15,973,399 bytes; Redis 1,774,376 bytes; recent5-minute log output 89,784 bytes.
Native compressed backup 460,779 bytes; all public table counts/fingerprints matched, one context hash
recomputed, prediction/result/evaluation/experiment/proposal identities present, temp DB/archive removed.
These are local snapshots after a bounded workload, not peak usage or an exact deployment capacity estimate.
Future explicitly authorized deployment must measure actual target capacity/space/conflicts and live workload.

## Historical verification failures preserved

Initial full M10 run:1084 PASS /50 setup errors /1 FAIL (158.76s). New M10 acceptance fixture retained
prediction rows before older M4 collector cleanup, causing an odds FK conflict. Scoped disposable fixture
cleanup now deletes experiment/evaluation/result/prediction dependencies in order. Alembic fileConfig
also disabled existing loggers inside the shared test process, hiding lifecycle records; fixed with
`disable_existing_loggers=False`. Corrected full1135 PASS, standalone900/235 PASS (historical checkpoint).
Final startup/accounting/calendar/concurrency gates:909 unit+237 integration=1146 full PASS. No production-like
schema/data change, leakage, fake forecast or accepted historical evidence rewriting resulted.

## Remaining deployment blockers

Required live sports gate is NOT_VERIFIED after provider API-error response; odds and real runtime LLM
credentials/routes unavailable. Independent M10 acceptance is PASS / ACCEPTED. Complete live command/human-receipt
and empirical multi-day operation remain unproven. Deployment gate is **NOT READY** regardless of green
local tests. No deploy, SSH, Hetzner or Hermes interaction occurred. M10 is merged/tagged; no M11 exists.


## Final operational deltas and evidence authority

Runtime factories now make one HTTP attempt; retries remain explicit/scanner failed-job CAS and quotas.
Cold odds event transport gets its own safe per-task observer/ledger without phantom paid fetch entries;
header-observed credit usage is kept separate from unknown monetary cost. Weekly time is configurable,
disabled Monday09 defaults unchanged. No schema/forecast math/provider normalization rewrite.
Startup input privacy is verified in a rebuilt production image; URI credentials with empty Redis
username are redacted. Known active credentials matched zero of3 live raw/normalized records.

Initial eaa/d6/2959 receipts and failures remain immutable history in the earlier evidence JSONs and
AI_WORKLOG. Current operational receipts use final-* evidence and committed source e137f4b. Live smoke
receipts are from the prior eaa implementation session; no later live calls were made. Target security/
capacity, complete live bot command/human receipt and multi-day empirical operation are not asserted.


## Completed acceptance and release closeout

Owner-supplied M10 PASS / ACCEPTED applies to review HEAD 76a221afbf06aeba464bbddbcfca315cf9b276d8 and exact CI 37083328438 (all jobs SUCCESS).
Acceptance receipt b44d859b0bff2f6671cadc3563e2129d6a978fc6 / CI 37107325599; PR #12 build/m10 → main; PR CI 37107458873; merge f289a82f2ae04ce455dc943f7d113470d4299e46; merged-main CI 37107597306. Every run passed all three jobs.
Annotated v0.11-m10 object 359c529b8424fd27d7dd82aad0a39c263e1a9bed peels to exact PR merge SHA f289a82f2ae04ce455dc943f7d113470d4299e46. This final docs-only main record leaves that tag target unchanged.
Release sequence is v0.1-m0 through v0.11-m10. No M11.

## Final release confirmation

M10 is independently PASS / ACCEPTED, merged and annotated-tagged. PR #12 merge `f289a82f2ae04ce455dc943f7d113470d4299e46` has passing merged-main CI `37107597306`. The tag `v0.11-m10` object `359c529b8424fd27d7dd82aad0a39c263e1a9bed` peels to that exact merge SHA. Final main documentation records the release receipt without changing the tag target/source. Live sports/odds/real-LLM stay NOT_VERIFIED, so deployment is **NOT READY**. No M11.
