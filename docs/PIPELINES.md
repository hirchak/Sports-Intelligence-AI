# Pipelines

Status: **planned** — no pipeline code exists in M0.
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

| Piece                    | Milestone |
|--------------------------|-----------|
| Jobs, queues, retries    | M1        |
| Fixture discovery        | M2        |
| Match collectors + odds  | M4        |
| Research                 | M5        |
| Features + MatchContext  | M6        |
| Prediction + ranking     | M7        |
| Settlement + evaluation  | M8        |
| Improvements + replay    | M9        |
