# M7 Review Handoff

**State:** IMPLEMENTED / VERIFIED — READY FOR INDEPENDENT REVIEW.
**Verified source HEAD:** `6c861b94c6300ae7da018176f5af12804f22b217`, pushed.
**Source CI:** [36890119992](https://github.com/hirchak/Sports-Intelligence-AI/actions/runs/36890119992)
— lint/type/unit SUCCESS; integration SUCCESS; Compose including Telegram SUCCESS.
The final documentation commit is rechecked against its exact remote HEAD; final SHA/run proof
is returned in the completion report (do not mistake source HEAD above for that final docs SHA).
**Branch:** `build/m7`; **base/main:** `11b6e782ab7256607992b70cc0d0dee4ebe92a3a`, `v0.7-m6`.
**Foundation commit:** `231d4539d074d5a3838bc535bbb81cd06855af84`.
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
STOP for independent review; M7 remains unmerged. Do not start M8.
Historical M6 failures/acceptance evidence remain in IMPLEMENTATION_STATUS and append-only AI_WORKLOG.

Accepted M6 reviewer packet remains in Git at
[M6 handoff](https://github.com/hirchak/Sports-Intelligence-AI/blob/11b6e782ab7256607992b70cc0d0dee4ebe92a3a/docs/REVIEW_HANDOFF.md).
No historical failure or acceptance worklog entries were rewritten.
