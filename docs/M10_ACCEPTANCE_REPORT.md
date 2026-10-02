# M10 local acceptance and deployment gate

Date: **2026-10-03, Europe/Warsaw**. LOCAL DEVELOPMENT ONLY.
Source checkpoint: `2959f68` plus subsequent scoped verification fixes; final source/CI receipt is pinned
in REVIEW_HANDOFF after commit. Historical failed verification below is preserved, not current authority.

**IMPLEMENTATION:** local gates verified, final source/delivery CI pending.
**LOCAL ACCEPTANCE:** PASS for scoped tests, with runtime-source final reproduction pending.
**LIVE INTEGRATIONS:** partial. **DEPLOYMENT GATE: NOT READY.**
Independent M10 audit = NOT_VERIFIED. M10 remains unmerged/untagged; main/tag remain accepted M9.

Every row below uses this date and the source checkpoint above unless its evidence states a different
historical source. Final docs-only delivery does not change the verified implementation.

| Gate | Status | Exact command/test and evidence | Limitation |
|---|---|---|---|
| Clean bootstrap | PASS | clean worktree of 2959f68; isolated sports-m10-clean; `make bootstrap`; command-receipts JSON | local Docker Desktop, no clean physical-machine/server proof |
| Full keyless v1 E2E | PASS | `pytest tests/integration/test_m10_acceptance.py`; m10-e2e-backup.json | explicit MOCK providers/LLM/analyst; HTTP network transport refused |
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
| Quota/degradation/cost | PASS | quota counters/headers/reserve/coalesce, LLM physical call/repair/challenger/experiment budgets, full suite | unknown monetary costs stay unknown; Redis reservation loss requires inspection |
| Scheduler simulation | PASS | M10 three-day frozen discovery slots ×duplicate; M4/M7 context/auto prediction; M8 repeated result scan; M9 weekly toggle/dedup | accelerated planning, no actual multi-day observation |
| Multi-day unattended empirical run | NOT_VERIFIED | no wall-clock multi-day run performed | explicit user acceptance allowed simulation; do not infer empirical proof |
| Restart/recovery | PASS | `python scripts/runtime_acceptance.py --project sports-m10-clean --env-file /tmp/sports-m10-clean/.env`, m10-runtime-resources.json | queued local mock work; lost broker dispatch/unknown paid RUNNING calls require manual inspection/rerun |
| Redis/Postgres outages | PASS | same runtime test, actual stop/start of isolated services;503 readiness/generic500/recovered unchanged forecast | does not prove automatic recovery of lost paid-call delivery |
| Telegram process restart | NOT_APPLICABLE | test transport/application startup validation; existing token already has a polling instance | no second concurrent polling process started; core remains stateless relative to bot |
| Backup/restore | PASS | `scripts/backup_restore.py` during complete E2E; m10-e2e-backup.json | native local temp restore, writers quiescent; no remote backup automation |
| Resource measurement | PASS | bounded12-job runtime batch; m10-runtime-resources.json | one synthetic fixture, snapshot not peak/target sizing |
| Private Compose/network | PASS | `scripts/compose_safety.py`; default/dev/Telegram/production-example config -q | future example only, zero deployment |
| Security pass | PASS | SECURITY findings/fixes, full security/access/failure gates, `scripts/security_check.py` | implementation-agent audit, not independent security acceptance |
| Secret/history sanity | PASS | known-local fingerprints + reachable Git blobs/private key/GitHub patterns; 352 working paths/1786 objects at checkpoint | heuristic, not exhaustive entropy/dependency-vulnerability audit; no values printed |
| Unit | PASS | `uv run pytest -q -m 'not integration'`:900 PASS | keyless |
| Integration | PASS | isolated Docker *_test/Redis15, `pytest -q -m integration`:235 PASS | keyless, no skips |
| Full pytest | PASS | `pytest -q`:1135 PASS,79.28s | keyless, no skips |
| Ruff/format/mypy | PASS | `ruff check .`, `ruff format --check .`, `mypy src`:258 Python files/171 source files | final docs-only change does not affect code |
| Alembic fresh | PASS | fresh sports_intel_m10_fresh_test →head→down -1→head→check; command receipt | destructive cycle only on generated empty *_test DB |
| Populated migration | PASS | accepted M8→M9 regression in full/integration, native M9 identities preserved; 0001–0014 byte-identical to v0.10-m9 | final populated M9→latest no-op receipt pending |
| Exact final GitHub CI | NOT_VERIFIED | final branch HEAD run to be pinned after push | must have all required jobs SUCCESS |
| Independent M10 review | NOT_VERIFIED | external review handoff only | implementation agent cannot self-accept |

## Exact M9 closeout

Accepted review HEAD354c8f5ff27fe5427313a459937c17054073f36a / accepted CI37061920047.
Acceptance receipt b0112a0dfb5328d8679526c17606805bd4bb9105 / CI37070235725, all jobs SUCCESS.
PR#11, PR CI37070527662 all SUCCESS; merged main03789b7b7b4af2179271a7797faa754d48ad0d0d.
Merged-main CI37070774858 all SUCCESS. Annotated v0.10-m9 object952356ed97ef8f47e7cdbd8a58a58cdbfc229c76,
peeled03789b7b7b4af2179271a7797faa754d48ad0d0d. Initial build/m10 remote/main/tag equality verified.

## Measured local capacity

Mac arm64,8 CPUs,8GiB host RAM; Docker Desktop VM limit3.826GiB. Synthetic one-fixture batch:
12 new jobs/144 probabilities, concurrency2,1.12s. Post-batch snapshots:

| Service | RAM | CPU snapshot |
|---|---:|---:|
| API |90.09MiB|0.22%|
| Worker |177.2MiB|0.61%|
| Beat |73.95MiB|0.00%|
| Postgres |23.38MiB|0.14%|
| Redis |4.539MiB|0.74%|

DB15,932,439 bytes; Redis1,773,384 bytes; recent5-minute log output89,894 bytes.
Native compressed backup460,915 bytes; all public table counts/fingerprints matched, one context hash
recomputed, prediction/result/evaluation/experiment/proposal identities present, temp DB/archive removed.
These are local snapshots after a bounded workload, not peak usage or an exact deployment capacity estimate.
Future explicitly authorized deployment must measure actual target capacity/space/conflicts and live workload.

## Historical verification failures preserved

Initial full M10 run:1084 PASS /50 setup errors /1 FAIL (158.76s). New M10 acceptance fixture retained
prediction rows before older M4 collector cleanup, causing an odds FK conflict. Scoped disposable fixture
cleanup now deletes experiment/evaluation/result/prediction dependencies in order. Alembic fileConfig
also disabled existing loggers inside the shared test process, hiding lifecycle records; fixed with
`disable_existing_loggers=False`. Corrected full1135 PASS, standalone900/235 PASS. No production-like
schema/data change, leakage, fake forecast or accepted historical evidence rewriting resulted.

## Remaining deployment blockers

Required live sports gate is NOT_VERIFIED after provider API-error response; odds and real runtime LLM
credentials/routes unavailable; independent M10 acceptance pending. Complete live command/human-receipt
and empirical multi-day operation remain unproven. Deployment gate is **NOT READY** regardless of green
local tests. No deploy, SSH, Hetzner, Hermes interaction, M10 merge/tag or M11 occurred.
