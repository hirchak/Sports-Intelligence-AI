# Pipelines

Status: **M7 implemented, independent review pending** — discovery, collectors, research,
quality/features/context and predictions/ranking. LOCAL DEVELOPMENT ONLY.
Authoritative design: `08_FOOTBALL_ANALYTICS_PIPELINE.md` and
`09_AGENT_CATALOG_AND_ORCHESTRATION.md`.

## Core rule

Never ask an LLM to "research Team A vs Team B and predict it". The pipeline
is a deterministic chain with LLM used only where specified.

## Pre-match DAG (M2–M7)

```text
DISCOVER FIXTURE
      ├── CORE COLLECTOR ──┐
      ├── STANDINGS CACHE  │
      ├── TEAM FORM ───────┤
      ├── AVAILABILITY ────┼─→ DATA QUALITY → FEATURE BUILDER
      ├── ODDS ────────────┤         ↓
      └── RESEARCH ────────┘   CONTEXT BUILDER
                                        ↓
                                 PREDICTION AGENT
                                        ↓
                              PREDICTION VALIDATOR
                                        ↓
                                CANDIDATE RANKER
                                        ↓
                                    PUBLISHER
```

## Post-match DAG (M8+)

```text
RESULT SCAN → RESULT COLLECTOR → SETTLEMENT → EVALUATION
   → AGGREGATES → WEEKLY IMPROVEMENT ANALYST
```

## Deterministic vs LLM boundary

Deterministic code: scheduler, quota manager, normalization, feature
calculations, no-vig math, EV, market settlement, duplicate detection.

LLM: research claim extraction, contextual reasoning, probability estimation,
improvement hypotheses.

## Implementation plan

| Piece                    | Milestone | State |
|--------------------------|-----------|-------|
| Jobs, queues, retries    | M1        | done (jobs schema + queues) |
| Fixture discovery        | M2        | done (API-Football + mock, batch-first, idempotent) |
| Match collectors + odds  | M4        | accepted |
| Research                 | M5        | accepted |
| Features + MatchContext  | M6        | accepted |
| Prediction + ranking     | M7        | implemented; review pending |
| Settlement + evaluation  | M8        | implemented; review pending |
| Improvements + replay    | M9        | planned |

## M7 automatic prediction boundary

Existing M4 scheduler scans collector freshness, then enqueues `context.build_match_context`.
After M6 context persistence, `automatic_prediction` can enqueue one semantic prediction job
when `PREDICTION_AUTO_ENABLED=true`, the context is eligible, and its score meets policy.
Existing phases remain `MORNING` and `PREMATCH`. Context-generation and prediction-request
keys deduplicate repeated scans/completions; no LLM call occurs inside the scanner.
No scheduler or automatic calls were activated in the running local stack.

`prediction.predict_match` runs on `llm`, receives only job/run UUIDs, claims QUEUED by CAS,
loads exact context and frozen prompt/config/policy from PostgreSQL, validates integrity, applies
bounded calls/repair/fallback, stores every probability and candidate/filter reason, then marks
Job/JobAttempt. UI reads persisted state. See [PREDICTIONS.md](PREDICTIONS.md).

## M8 implementation

See [EVALUATION.md](EVALUATION.md) and [ADR 0011](adr/0011-m8-result-authority-and-measurement.md).
Migration 0013 adds versioned results, probability/candidate settlements, immutable evaluation runs,
normalized metrics and calibration buckets. Local scheduled date batches feed API and thin Telegram stats.
