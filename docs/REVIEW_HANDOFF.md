# M7 Review Handoff

**State:** M7.1 local acceptance and source CI passed; final docs-only HEAD CI pending.
**M7.1 code HEAD:** `07658d8e9fdd29f0e642447fd1639efb0b08aa47` (pushed).
**M7.1 code CI:** [36910780514](https://github.com/hirchak/Sports-Intelligence-AI/actions/runs/36910780514) — all jobs SUCCESS on that exact SHA.
The final documentation-only HEAD also passed CI; its SHA/run are in the final completion report.
**M7.1 reviewed starting HEAD:** `b0dd35c3606449d95c3be0723ded5f78a2883e67`.
**Branch:** `build/m7`; **base/main:** `11b6e782ab7256607992b70cc0d0dee4ebe92a3a`, `v0.7-m6`.
**Phase:** LOCAL DEVELOPMENT ONLY. M7 not merged/tagged; M8 not started.


## Scope and architecture

Binding complete user scope: [M7_SCOPE.md](M7_SCOPE.md).
Runtime/design/limitations: [PREDICTIONS.md](PREDICTIONS.md), [ADR 0010](adr/0010-m7-forecasting-and-comparison-identities.md).

Immutable M6 context → eligibility → separate baselines → deterministic ModelRouter → configured
runtime provider → strict validator/one repair → twelve probabilities → deterministic captured-price
comparison/ranking → immutable run records → API/Telegram. Development model is not runtime predictor.

- Adapters: deterministic Mock, OpenAI/OpenAI-compatible, MiniMax, OpenCode Go; chat/responses/messages
  protocols as configured. HTTP contracts offline-tested, live provider integration unverified.
- Router: capabilities, quality/budget route labels, recent health, permitted manual override, bounded
  configured fallback. Actual provider/returned model and config preserved separately from requested route.
- Prompt: `predictor`, `1.0.0`, source path + SHA-256 + persisted content at enqueue; model config/policy hashes.
- Identity: context + prompt/version + provider/model/config + variant/role/phase + route/policy + engine version;
  explicit rerun UUID adds request uniqueness; CAS execution prevents duplicate calls; old runs preserved.
- Probabilities: HOME/DRAW/AWAY; three DC; O/U1.5, O/U2.5; BTTS_YES/NO. Six direct estimates; Python derives rest.
- Validation: bounded strict schema, identity, finite [0,1], sum tolerance 1e-6, totals/BTTS coherence,
  abstention, duplicate/contradictory/outside evidence. One repair total, even with fallback; never retry repair.
- ABSTAINED has no normal probabilities/candidates; SUCCEEDED+NO_BET has all twelve, zero display candidates.
- Baseline: observed last10 GF/GA mean attack/defence Poisson, independent goals; missing rates unavailable.
  No fitted home/opponent adjustment/calibration; no arbitrary ensembles. Market captured no-vig benchmark
  separate; DC derived from same-bookmaker 1X2, preserving original context and old odds data.
- WITH/WITHOUT_ODDS coexist. Masking preserves original context but conservatively removes all research text,
  odds features/provenance and quality detail. Later odds-effect comparisons must account for research removal.
- PRIMARY/CHALLENGER coexist; shadow never promoted/averaged or shown as primary.
- Ranking: edge=Pmodel−Pmarket, EV=Pmodel*capturedOdds−1; allowed markets, quality, min/max odds,
  probability/edge thresholds, context staleness/age, league allow/deny, display cap. All filter reasons persisted.
- Automatic-first capability: eligible MORNING/PREMATCH context completion enqueues one deduplicated llm job
  when opt-in enabled; existing scheduler flags retained, no new LLM polling. Local stack activation not performed.
- API: POST `/v1/fixtures/{id}/analyze` (202 job enqueue), GET `/v1/predictions`, GET `/v1/predictions/{run_id}`.
  Safe phase/context/as_of/role/variant/allowlisted-route options; explicit rerun token, no keys/raw configs accepted.
- Telegram: Russian prediction menu, fixture analyze/view, table/why/risks/model/rerun; typed BackendClient,
  persisted reads only, allowlist on router, bounded callbacks, one acknowledgement, test transport verified.
- Migration 0012: prompt_versions, model_configs, prediction_runs, market_predictions, ranked_candidates,
  probability_baselines, llm_call_attempts. UUID/FK/index/uniqueness/checks; M0–M6 revisions unchanged.

## Actual local verification

- Unit (including offline provider contracts): **531 passed**, 128 deselected.
- Integration (Docker Postgres `sports_intel_m7_test`, Redis db15): **128 passed**, 531 deselected.
- Full pytest: **659 passed** in 23.18s.
- Ruff check/format: clean, **208 Python files**. Mypy: clean, **142 source files**.
- Alembic: fresh empty DB→head; populated accepted M6→0012; downgrade -1→upgrade head→check, zero drift.
- Docker Compose config and Telegram profile: valid. Secret sanity scan/diff hygiene: clean.
- Keyless complete discovery→collectors→context→MockLLM→persisted API→Telegram fake flow verified;
  real isolated Redis Celery message serialization verifies minimal UUID payload. Concurrency/rerun/fallback,
  failed/invalid output, can_predict=false and planted later lineup/odds/fixture status tested.
- Real runtime LLM calls: **0**; runtime provider/model/credentials were not configured locally.
- No new live Telegram smoke, no model accuracy/calibration claims.

## Known limits and review boundary

No empirical baseline/LLM accuracy evaluation (M8). Model-specific endpoints/sampling/schema availability
must be configured and validated before real usage. Go runtime disabled by default because current official
Go docs target coding traffic; permitted forecasting API use must be established separately.
No DB immutability triggers; existing append-only application policy applies. Worker crash after claim or lost
broker delivery requires inspection/explicit rerun; no automatic reset that might repeat paid calls.
No disagreement aggregation, fitted ensembles, settlement/evaluation or automatic Telegram push.

Main remains accepted M6; M7 not merged or tagged. Zero deployment/Hetzner/SSH/Hermes interaction.
M7 remains unmerged. M7.1 local gates passed: **535 unit + 128 integration = 663**; Ruff, format, mypy, Alembic and Compose clean. Push branch, verify exact remote CI, then STOP for independent review. Do not start M8.
Historical M6 failures/acceptance evidence remain in IMPLEMENTATION_STATUS and append-only AI_WORKLOG.

Accepted M6 reviewer packet remains in Git at
[M6 handoff](https://github.com/hirchak/Sports-Intelligence-AI/blob/11b6e782ab7256607992b70cc0d0dee4ebe92a3a/docs/REVIEW_HANDOFF.md).
No historical failure or acceptance worklog entries were rewritten.


## M7.1 canonical M4 1X2 follow-up

M4 `OddsPrice.market` is `h2h_1x2` (`home/draw/away`); the The Odds API request key remains `h2h`.
M7.1 aligns baseline/ranking with normalized `h2h_1x2`, retains backward-compatible M7 aliases,
verifies all three DC derivations from one bookmaker's complete 1X2, rejects incomplete/cross-book
sets, and updates M7 synthetic prices and the M4 mock DTO to the canonical output. M4 live parsing,
request protocol, schema, and migrations are unchanged.

Full local acceptance: **535 unit + 128 integration = 663 passed**; Ruff/format/mypy clean; Alembic
no new operations; Docker Compose default/dev/Telegram valid; secret sanity passed. M7.1 code CI
`36910780514` is green on HEAD `07658d8e9fdd29f0e642447fd1639efb0b08aa47`. The pending docs-only
commit must pass CI on its own exact HEAD. No live LLM calls.


## M7.1 M4 canonical 1X2 acceptance (2026-10-01)

`OddsPrice.market="h2h_1x2"`, selections `home/draw/away`, is the M4 persisted contract. M7 now maps
these actual values into HOME/DRAW/AWAY and the complete same-bookmaker no-vig group. DC benchmarks derive
from those 1X2 values; M4 overlapping DC margin-normalized values are ignored. Tests prove all three DC
selections, canonical candidate odds/edge, incomplete market rejection, and refusal to combine bookmaker
A's HOME/DRAW with bookmaker B's AWAY. Legacy M7 aliases remain compatible. Synthetic M7 odds rows and
MockOddsProvider normalized DTO now use the production canonical name; outbound provider request `h2h`
remains unchanged. No M4 live parsing or schema/migration changes.
