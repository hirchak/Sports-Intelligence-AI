# Pipelines

Status: **M1** — queue/routing infrastructure present (`control`, `sports_io`,
`research_io`, `llm`, `evaluation`, `notifications`); pipeline code arrives
in M2+.
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
| Jobs, queues, retries    | M1        | queue infra + `jobs`/`job_attempts` schema done; orchestrator logic M2+ |
| Fixture discovery        | M2        | planned |
| Match collectors + odds  | M4        | planned |
| Research                 | M5        | planned |
| Features + MatchContext  | M6        | planned |
| Prediction + ranking     | M7        | planned |
| Settlement + evaluation  | M8        | planned |
| Improvements + replay    | M9        | planned |
