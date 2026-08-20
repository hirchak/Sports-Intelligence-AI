# Agent Catalog and Orchestration
## Roles, Inputs, Outputs and Execution DAG

"Agent" in this project means a bounded worker/service with one responsibility.

Not every agent needs an LLM.

---

# 1. Orchestrator

**Type:** deterministic service  
**LLM:** no

Responsibilities:

- receive scheduled/manual pipeline request;
- create job graph;
- enforce state machine;
- fan out independent work;
- join required dependencies;
- apply retries/timeouts;
- prevent duplicates;
- record job status.

The orchestrator must not contain football prediction logic.

---

# 2. Scheduler Agent

**Type:** deterministic  
**Trigger:** Celery Beat / scheduled task  
**Output:** discovery jobs

Schedules:

- morning discovery;
- optional pre-match refresh scan;
- result settlement scan;
- daily metrics;
- weekly improvement analysis.

---

# 3. Fixture Discovery Agent

**Type:** deterministic provider collector  
**Input:** date + enabled leagues  
**Output:** canonical fixtures + job IDs

Persistence:

- fixtures;
- raw provider payload;
- provider IDs.

Idempotency key:

```text
discover:{provider}:{date}:{league_config_version}
```

---

# 4. Core Match Collector

**Type:** deterministic provider collector

Collects provider fields that can be fetched efficiently in bulk:

- fixture details;
- embedded lineups/statistics when provider offers them;
- recent completed fixtures;
- event metadata needed for form.

Prefer batch endpoints.

---

# 5. Team Form Agent

**Type:** deterministic analytical service  
**LLM:** no

Inputs:

- recent fixture/results snapshots.

Outputs:

- last-5/last-10 metrics;
- home/away splits;
- scoring/conceding rates;
- rest-day inputs.

Cache reusable team snapshots because several fixtures may need the same team data.

---

# 6. Standings/Season Agent

**Type:** deterministic provider collector

Use league-season caching.

A table should normally be fetched once per league/season freshness window, not once per fixture.

---

# 7. Availability Agent

**Type:** provider collector + optional claim merger

Inputs:

- injury/suspension endpoints;
- lineup endpoints;
- web research availability claims.

Outputs:

- normalized availability snapshot;
- conflict flags;
- important-absence indicators.

---

# 8. Odds Agent

**Type:** deterministic provider collector

Inputs:

- fixture(s);
- supported market whitelist.

Outputs:

- normalized odds snapshots;
- best/median price;
- no-vig probabilities;
- overround;
- movement vs prior snapshot.

Quota-sensitive. Prefer bulk/date endpoints where possible.

---

# 9. Research Agent

**Type:** search + LLM-assisted extraction

Responsibilities:

- issue a bounded set of web searches;
- select fresh/relevant sources;
- extract claims;
- de-duplicate;
- attach source/time/confidence.

It must not provide the final forecast.

It may output no useful claims.

---

# 10. Data Quality Agent

**Type:** deterministic policy engine  
**LLM:** no

Inputs:
- all required snapshots.

Outputs:

```text
quality score
missing critical fields
warnings
conflicts
can_predict
```

---

# 11. Feature Builder

**Type:** deterministic analytical service

Inputs:
- normalized snapshots.

Outputs:
- versioned numeric/categorical feature snapshot.

No free-form model reasoning.

---

# 12. Context Builder

**Type:** deterministic assembler

Inputs:
- feature snapshot;
- normalized snapshots;
- research claims;
- odds;
- quality report.

Output:
- immutable/versioned MatchContext.

Idempotency:

```text
context:{fixture_id}:{forecast_phase}:{as_of_bucket}:{schema_version}
```

---

# 13. Prediction Agent

**Type:** LLM analytical agent

Input:
- MatchContext only.

Output:
- schema-valid probabilities;
- evidence;
- risk flags;
- abstain.

No direct provider/web access.

---

# 14. Prediction Validator

**Type:** deterministic

Checks:
- JSON/schema;
- probability constraints;
- market consistency;
- abstain/data-quality rules.

---

# 15. Candidate Ranking Agent

**Type:** deterministic policy engine

Calculates:
- no-vig market comparison;
- edge;
- EV;
- display filters;
- candidate ranking.

This is where minimum odds such as `1.30` belong.

---

# 16. Publisher Agent

**Type:** deterministic UI integration

Responsibilities:
- format Telegram message;
- send;
- persist delivery receipt;
- prevent duplicate sends.

---

# 17. Result Collector

**Type:** deterministic provider collector

Fetches completed match statuses in bulk where possible.

Persist final result independently from forecast data.

---

# 18. Settlement Agent

**Type:** deterministic

Given final score/status:

- settle each market;
- handle void/postponed cases.

Never use LLM.

---

# 19. Evaluation Agent

**Type:** deterministic statistics service

Calculates:
- Brier;
- log loss;
- calibration buckets;
- coverage;
- hit rate;
- ROI simulation;
- model/league/market segments.

---

# 20. Improvement Analyst

**Type:** LLM-assisted analyst

Inputs:
- aggregated evaluation;
- error examples;
- cost/latency;
- data-quality trends.

Outputs:
- proposals only.

Cannot:
- edit production prompt automatically;
- edit code automatically;
- change weights automatically.

---

# 21. Experiment Runner

**Type:** deterministic orchestration + optional LLM calls

Runs:
- challenger prompt/model;
- replay on historical frozen contexts;
- comparison vs baseline.

Stores experiment state separately.

---

# 22. Model Router

**Type:** deterministic runtime infrastructure

Inputs:

```text
task_type
quality_tier
required_capability
cost budget
provider health
configured route
```

Outputs:
- provider/model choice.

Example task types:

```text
research_extract
prediction_primary
prediction_challenger
improvement_analysis
```

The router is described separately in `12_LLM_ROUTER_AND_MODEL_POLICY.md`.

---

# 23. Primary pre-match DAG

```text
DISCOVER FIXTURE
      |
      +-----------------------+
      |                       |
      v                       v
CORE COLLECTOR          STANDINGS CACHE
      |
      +------------+------------+----------------+
      |            |            |                |
      v            v            v                v
TEAM FORM      AVAILABILITY    ODDS           RESEARCH
      |            |            |                |
      +------------+------------+----------------+
                           |
                           v
                     DATA QUALITY
                           |
                           v
                     FEATURE BUILDER
                           |
                           v
                     CONTEXT BUILDER
                           |
                           v
                     PREDICTION AGENT
                           |
                           v
                  PREDICTION VALIDATOR
                           |
                           v
                    CANDIDATE RANKER
                           |
                           v
                       PUBLISHER
```

---

# 24. Post-match DAG

```text
RESULT SCAN
    ↓
RESULT COLLECTOR
    ↓
SETTLEMENT
    ↓
EVALUATION
    ↓
AGGREGATES
    ↓
WEEKLY IMPROVEMENT ANALYST
```

---

# 25. Queue design

Suggested Celery queues:

```text
control
sports_io
research_io
llm
evaluation
notifications
```

Keep concurrency separately configurable.

Example:

- `sports_io`: IO-heavy, provider rate-limited;
- `research_io`: search provider limit;
- `llm`: expensive, low concurrency;
- `evaluation`: CPU-light batch work.

---

# 26. Task contract

Every task receives minimal identifiers, not giant Python objects.

Example:

```json
{
  "job_id": "...",
  "fixture_id": "...",
  "forecast_phase": "MORNING",
  "correlation_id": "..."
}
```

Workers load canonical state from DB.

Benefits:

- retries;
- smaller queue payloads;
- auditability;
- fewer serialization/version problems.

---

# 27. Retry policy

Classify errors.

## Retryable

- timeout;
- provider 5xx;
- transient 429;
- temporary LLM outage.

## Non-retryable

- invalid fixture ID;
- unsupported league;
- invalid configuration;
- permanent authentication failure;
- schema incompatibility requiring code change.

Use exponential backoff + jitter.

Respect provider reset headers when available.

---

# 28. Concurrency rule

Parallelize independent collectors but never exceed:

- provider per-minute limit;
- daily quota policy;
- LLM concurrency/cost budget;
- server resource limits.

The quota manager can reduce concurrency dynamically.

---

# 29. Agent acceptance criteria

For every agent/service implementation, document:

- responsibility;
- input schema;
- output schema;
- persistence;
- timeout;
- retry;
- idempotency key;
- metrics;
- unit/integration tests;
- whether it uses LLM.

An agent without these boundaries is not considered complete.
