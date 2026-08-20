# Sports Intelligence AI
## Master Technical Specification

**Status:** authoritative implementation specification  
**Initial sport:** association football / soccer  
**Primary use:** private research and forecasting system  
**Initial interface:** private Telegram bot  
**Development:** local Docker environment first  
**Production target:** existing Hetzner Ubuntu server, isolated from Hermes  
**Source of truth for code:** GitHub repository

---

# 1. Product goal

Build a modular, automated sports intelligence platform that discovers configured football matches, collects high-quality structured and unstructured information, creates a frozen pre-match data snapshot, generates probabilistic forecasts for supported betting markets, stores all predictions, settles them after matches, evaluates calibration/performance, and proposes improvements.

The objective is **not** to create an LLM that casually guesses a result.

The objective is to build a reproducible forecasting laboratory where:

- raw data is separated from interpretation;
- deterministic features are separated from LLM reasoning;
- market odds are separated from model probabilities;
- every prediction is timestamped and reproducible;
- accuracy can be evaluated honestly;
- models, prompts, data providers and scoring rules can be A/B tested;
- the system can abstain when information quality is insufficient.

No prediction should ever be presented as guaranteed.

---

# 2. Core architectural principles

## 2.1 Modular

Every external dependency must sit behind an adapter/interface:

- sports data provider;
- odds provider;
- web/search provider;
- LLM provider;
- Telegram transport.

Changing API-Football to Sportmonks, MiniMax to another model, or Telegram to a web UI must not require rewriting the domain logic.

## 2.2 Event/job-driven

Long-running work must not happen inside Telegram request handlers or HTTP requests.

Commands create jobs. Workers execute pipelines.

## 2.3 Database-first

PostgreSQL is the system of record for:

- fixtures;
- data snapshots;
- research;
- features;
- prompts/model configuration;
- prediction runs;
- predictions;
- odds;
- results;
- evaluations;
- experiments;
- improvement proposals;
- audit logs.

GitHub stores code/config/templates—not live operational state.

## 2.4 Reproducible

Every forecast must have:

- fixture ID;
- prediction run ID;
- created_at;
- `as_of` timestamp;
- model/provider;
- model parameters;
- prompt version;
- feature schema version;
- provider snapshot IDs;
- odds snapshot IDs;
- data-quality score;
- final structured output.

## 2.5 No data leakage

A historical replay may use only information that was available before its configured `as_of` time.

Never overwrite old snapshots in a way that makes historical forecasts unknowable.

## 2.6 Human-controlled self-improvement

The system may automatically:

- evaluate forecasts;
- detect weak segments;
- generate hypotheses;
- create improvement proposals;
- run sandbox experiments if explicitly enabled.

It must **not** automatically modify production prompts, weights, source priorities or code.

Promotion to production requires explicit approval.

## 2.7 Portable

The complete runtime must be reproducible using:

- GitHub;
- Dockerfiles;
- Docker Compose;
- PostgreSQL migrations;
- `.env.example`;
- documented bootstrap commands.

---

# 3. High-level architecture

```text
                         ┌────────────────────┐
                         │  Telegram Bot       │
                         │  Private UI         │
                         └─────────┬───────────┘
                                   │
                                   ▼
                         ┌────────────────────┐
                         │ FastAPI Control API │
                         └─────────┬───────────┘
                                   │ create/read jobs
                                   ▼
                         ┌────────────────────┐
                         │ Orchestrator        │
                         │ Scheduler + Queue   │
                         └──────┬───────┬─────┘
                                │       │
                    fan-out jobs│       │scheduled jobs
                                ▼       ▼
 ┌────────────────┐   ┌─────────────────────┐   ┌────────────────┐
 │ Sports Provider │──▶│ Collection Workers  │◀──│ Search/News    │
 └────────────────┘   └──────────┬──────────┘   └────────────────┘
                                  │
 ┌────────────────┐               │
 │ Odds Provider   │───────────────┘
 └────────────────┘
                                  ▼
                         ┌────────────────────┐
                         │ PostgreSQL          │
                         │ immutable snapshots │
                         └─────────┬───────────┘
                                   ▼
                         ┌────────────────────┐
                         │ Feature Builder     │
                         │ deterministic       │
                         └─────────┬───────────┘
                                   ▼
                         ┌────────────────────┐
                         │ MatchContext Builder│
                         └─────────┬───────────┘
                                   ▼
                         ┌────────────────────┐
                         │ Prediction Engine   │
                         │ model adapter       │
                         └─────────┬───────────┘
                                   ▼
                         ┌────────────────────┐
                         │ Value/Rank Engine   │
                         │ deterministic       │
                         └─────────┬───────────┘
                                   ▼
                         ┌────────────────────┐
                         │ Telegram Formatter  │
                         └────────────────────┘

After match:
Results Collector -> Settlement -> Evaluator -> Metrics -> Improvement Proposals
```

---

# 4. Recommended technology stack

Use boring, mature technology.

## Backend

- Python 3.12
- FastAPI
- Pydantic v2
- SQLAlchemy 2
- Alembic
- httpx
- tenacity
- PostgreSQL 16
- Redis 7
- Celery 5 + Celery Beat
- aiogram 3 for Telegram
- pytest
- Ruff
- mypy
- structured JSON logging

Use `uv` or another lockfile-based Python package manager. Commit the lockfile.

## Infrastructure

- Docker
- Docker Compose
- GitHub
- GitHub Actions
- Hetzner Ubuntu server for production
- long polling for Telegram in v1 so no public webhook endpoint is required

Do not introduce Kubernetes, Kafka, Temporal or a vector database in v1 unless a concrete requirement appears.

---

# 5. Repository structure

Use a clean Python monorepo similar to:

```text
sports-intelligence/
├─ README.md
├─ pyproject.toml
├─ uv.lock
├─ .env.example
├─ .gitignore
├─ Makefile
├─ compose.yaml
├─ compose.dev.yaml
├─ Dockerfile
├─ opencode.json.example
│
├─ src/
│  └─ sports_intelligence/
│     ├─ api/
│     │  ├─ app.py
│     │  ├─ dependencies.py
│     │  └─ routes/
│     ├─ bot/
│     │  ├─ app.py
│     │  ├─ handlers/
│     │  ├─ keyboards/
│     │  └─ formatters/
│     ├─ core/
│     │  ├─ config.py
│     │  ├─ logging.py
│     │  ├─ time.py
│     │  └─ ids.py
│     ├─ domain/
│     │  ├─ fixtures/
│     │  ├─ predictions/
│     │  ├─ evaluation/
│     │  └─ experiments/
│     ├─ db/
│     │  ├─ models/
│     │  ├─ repositories/
│     │  ├─ session.py
│     │  └─ migrations/
│     ├─ providers/
│     │  ├─ sports/
│     │  ├─ odds/
│     │  ├─ search/
│     │  └─ llm/
│     ├─ pipelines/
│     │  ├─ discover_fixtures.py
│     │  ├─ collect_match.py
│     │  ├─ build_context.py
│     │  ├─ predict_match.py
│     │  ├─ settle_results.py
│     │  └─ evaluate.py
│     ├─ workers/
│     │  ├─ celery_app.py
│     │  └─ tasks/
│     ├─ features/
│     ├─ research/
│     ├─ ranking/
│     └─ schemas/
│
├─ prompts/
│  ├─ predictor/
│  ├─ research/
│  └─ improvement/
│
├─ config/
│  ├─ leagues.example.yaml
│  ├─ markets.yaml
│  └─ scoring.yaml
│
├─ tests/
│  ├─ unit/
│  ├─ integration/
│  ├─ contract/
│  └─ fixtures/
│
├─ scripts/
│  ├─ bootstrap.sh
│  ├─ seed_leagues.py
│  ├─ replay.py
│  └─ backup_db.sh
│
└─ docs/
   ├─ ARCHITECTURE.md
   ├─ DATA_MODEL.md
   ├─ PIPELINES.md
   ├─ TELEGRAM.md
   ├─ DEPLOYMENT.md
   ├─ IMPLEMENTATION_STATUS.md
   └─ adr/
```

Exact names may vary, but the separation of responsibilities must remain.

---

# 6. Docker topology

The project must use its own Compose project name, network, containers and volumes.

Recommended services:

```text
sports-api
sports-worker
sports-beat
sports-bot
sports-postgres
sports-redis
```

Requirements:

- PostgreSQL and Redis are not exposed publicly.
- Bot uses Telegram long polling.
- API is internal/local by default.
- Production project name: `sports-intel`.
- Use unique named volumes.
- Do not use Hermes volumes, environment files, network names, databases or ports.
- A deployment script must verify that no proposed container/port conflicts with existing services.

Hermes must remain completely independent.

---

# 7. Configuration and secrets

All environment-dependent configuration must come from environment variables or versioned non-secret YAML.

Commit:

- `.env.example`
- config schemas
- sample league config
- sample market config

Never commit:

- Telegram token
- sports API token
- LLM keys
- GitHub tokens
- server credentials
- database production passwords

Minimum variables:

```text
APP_ENV
APP_TIMEZONE=Europe/Warsaw

DATABASE_URL
REDIS_URL

TELEGRAM_BOT_TOKEN
TELEGRAM_ALLOWED_USER_IDS

SPORTS_PROVIDER
SPORTS_API_KEY

ODDS_PROVIDER
ODDS_API_KEY

SEARCH_PROVIDER
SEARCH_API_KEY

LLM_PROVIDER
LLM_API_KEY
LLM_BASE_URL

PREDICTOR_MODEL
RESEARCH_MODEL
IMPROVEMENT_MODEL

DEFAULT_MIN_ODDS=1.30
DEFAULT_MIN_MODEL_PROBABILITY
DEFAULT_MIN_EDGE
```

Use strong validation at startup.

---

# 8. Provider layer

## 8.1 SportsDataProvider interface

At minimum:

```python
class SportsDataProvider(Protocol):
    async def get_fixtures(self, date, league_ids): ...
    async def get_fixture(self, external_fixture_id): ...
    async def get_standings(self, league_id, season): ...
    async def get_team_recent_matches(self, team_id, limit): ...
    async def get_head_to_head(self, home_team_id, away_team_id, limit): ...
    async def get_injuries(self, fixture_id): ...
    async def get_lineups(self, fixture_id): ...
    async def get_team_statistics(self, team_id, league_id, season): ...
    async def get_result(self, fixture_id): ...
```

The first implementation should support a real football data API.

Recommended MVP options:

- **API-Football / API-Sports** as a practical first provider;
- **Sportmonks Football API 3.0** as a valid alternative.

Do not couple the domain model to a provider's raw JSON.

Store raw provider payloads for traceability, then normalize into internal schemas.

## 8.2 OddsProvider interface

Support:

- pre-match markets;
- multiple bookmakers where available;
- timestamped snapshots;
- decimal odds normalized internally.

Store opening/current/pre-kickoff snapshots where possible.

Calculate:

- raw implied probability;
- market overround;
- no-vig normalized implied probability.

Do not use odds as the sole source of prediction.

## 8.3 SearchProvider interface

Used for pre-match web/news research.

Provider can be implemented later using a search API such as a general web search provider.

Research targets:

- injuries/suspensions not yet reflected in structured provider;
- expected rotation;
- manager/team statements;
- schedule congestion;
- travel issues;
- confirmed or probable lineup information;
- meaningful tactical/context news.

Every research item must store:

- URL/source identifier;
- title;
- publication time when available;
- retrieval time;
- extracted claim;
- confidence/relevance;
- fixture ID.

Do not silently scrape websites that prohibit it. Prefer documented APIs or compliant search providers.

## 8.4 LLMProvider interface

The runtime must support swapping models through configuration.

At minimum expose:

```python
async def generate_structured(
    system_prompt: str,
    input_payload: dict,
    output_schema: type[BaseModel],
    model: str,
    temperature: float | None = None,
) -> BaseModel:
    ...
```

Implement:

- retry/backoff;
- timeout;
- token/latency logging;
- raw response retention where appropriate;
- schema validation;
- one repair attempt for invalid structured output;
- failure state if still invalid.

Do not parse critical decisions out of free-form prose.

---

# 9. League configuration

The system must not analyze every competition on the planet by default.

Use `config/leagues.yaml` or DB configuration.

Example:

```yaml
leagues:
  - slug: premier-league
    enabled: true
    provider_ids:
      api_football: 39
  - slug: la-liga
    enabled: true
    provider_ids:
      api_football: 140
  - slug: champions-league
    enabled: true
    provider_ids:
      api_football: 2
```

Telegram/admin API must later allow enabling/disabling leagues without code changes.

---

# 10. Match lifecycle

Use an explicit state machine.

Suggested states:

```text
DISCOVERED
COLLECTION_PENDING
COLLECTING
DATA_READY
QUALITY_FAILED
PREDICTION_PENDING
PREDICTED
PUBLISHED
STARTED
FINISHED
SETTLED
EVALUATED
FAILED_RETRYABLE
FAILED_FINAL
```

State transitions must be idempotent.

A retry must never create duplicate forecasts accidentally.

---

# 11. Daily automation pipeline

Default scheduler uses `Europe/Warsaw`.

Recommended initial schedule:

## 11.1 Morning discovery

At configurable morning time:

1. fetch fixtures for configured leagues;
2. upsert fixtures;
3. create collection/prediction jobs;
4. skip fixtures already processed for the same forecast phase.

## 11.2 Per-fixture fan-out

For every fixture:

- collect core fixture metadata;
- collect recent team form;
- collect league table;
- collect home/away splits when available;
- collect H2H;
- collect injuries/suspensions;
- collect team statistics;
- collect odds;
- perform web/news research;
- calculate rest days/schedule congestion;
- run data-quality checks.

Independent collectors should run in parallel where safe.

## 11.3 Morning prediction

Build a frozen `MatchContext` with an `as_of` timestamp.

Generate prediction version `MORNING`.

## 11.4 Optional pre-kickoff refresh

Architecture must support, even if disabled initially:

- T-90 minutes;
- T-60 minutes;
- retrieve fresh odds;
- retrieve confirmed lineups when available;
- retrieve late injuries/news;
- generate `PREMATCH_FINAL`.

Never overwrite the morning prediction.

This lets the system later compare:

- early forecast;
- final lineup-aware forecast.

---

# 12. Data collected per fixture

The exact provider availability varies. The internal schema must tolerate missing fields.

Target categories:

## Fixture

- competition
- season
- round
- kickoff time UTC
- local display timezone
- venue
- home/away
- referee if available

## Team strength/form

- last N matches
- W/D/L
- goals for/against
- home/away form
- points per game
- shots
- shots on target
- possession
- xG/xGA if available
- clean sheets
- scoring/conceding streaks
- opponent-strength-adjusted metrics later

## Table/context

- position
- points
- goal difference
- games played
- relegation/title/qualification context where derivable

## Player availability

- injuries
- suspensions
- expected absences
- confirmed lineup
- missing high-impact players

## Schedule

- days since last match
- matches in previous 7/14 days
- travel/context if confidently known

## H2H

Store it, but do not overweight it by default.

## Odds

Per market/bookmaker:

- timestamp
- selection
- decimal odds
- implied probability
- no-vig probability

## Research

Structured claims plus source metadata.

---

# 13. Data-quality layer

Before prediction, create a quality report.

Example dimensions:

- fixture metadata completeness;
- team form completeness;
- standings availability;
- injury availability;
- odds availability;
- research freshness;
- lineup availability;
- provider conflicts;
- stale data.

Output:

```json
{
  "overall_score": 0.84,
  "missing_critical": [],
  "warnings": ["confirmed lineups not yet available"],
  "source_conflicts": [],
  "can_predict": true
}
```

If critical information is missing, the system may abstain.

Never force a prediction merely because a fixture exists.

---

# 14. Deterministic feature builder

Create features in normal Python code before asking the LLM.

Examples:

- rolling points per game;
- rolling goals for/against;
- home-vs-away performance;
- rest-day differential;
- league position differential;
- recent scoring/conceding rates;
- injury count;
- key-player availability indicator;
- normalized no-vig market probability;
- odds movement;
- schedule congestion.

Every feature set has:

- schema version;
- generated_at;
- source snapshot references.

The LLM should receive both human-readable context and canonical numbers.

---

# 15. Canonical MatchContext

Prediction models consume one canonical versioned object.

Example top-level structure:

```json
{
  "schema_version": "1.0",
  "fixture": {},
  "home_team": {
    "form": {},
    "season": {},
    "availability": {}
  },
  "away_team": {
    "form": {},
    "season": {},
    "availability": {}
  },
  "h2h": {},
  "schedule": {},
  "odds": {},
  "research": [],
  "features": {},
  "data_quality": {},
  "as_of": "..."
}
```

Store the final serialized context or an immutable reference to all component snapshots.

The prediction engine must not make hidden web requests itself.

Its entire evidence set must be auditable.

---

# 16. Prediction engine

## 16.1 Principle

The LLM is an analytical layer—not the database and not the scheduler.

It receives `MatchContext` and must return strict structured JSON.

## 16.2 Supported initial markets

Start with a small, measurable set:

- Home / Draw / Away (1X2)
- Double chance
- Total Over/Under 1.5
- Total Over/Under 2.5
- Both Teams To Score — Yes/No

Add markets only after enough evaluation data exists.

## 16.3 Output schema

Illustrative:

```json
{
  "fixture_id": "...",
  "model_assessment": {
    "home_win": 0.52,
    "draw": 0.27,
    "away_win": 0.21
  },
  "markets": [
    {
      "market": "total_over_1_5",
      "model_probability": 0.73,
      "confidence": "medium",
      "evidence_for": [
        "..."
      ],
      "evidence_against": [
        "..."
      ],
      "risk_flags": [
        "lineups_not_confirmed"
      ]
    }
  ],
  "summary": "...",
  "abstain": false,
  "abstain_reason": null
}
```

Validation rules:

- 1X2 probabilities sum approximately to 1;
- probabilities are 0..1;
- model cannot invent missing facts;
- evidence must reference supplied context;
- if data quality is below threshold, model should abstain or reduce confidence.

## 16.4 Prompt versions

Prompts are files in Git.

Every run records prompt version/hash.

Do not edit a production prompt without versioning.

---

# 17. Value/ranking engine

The LLM should estimate probabilities.

A deterministic engine decides which predictions are displayed as candidate opportunities.

For each selection:

```text
market_probability = no-vig implied market probability
edge = model_probability - market_probability
expected_value = model_probability * decimal_odds - 1
```

Configurable filters:

- minimum decimal odds, default 1.30;
- minimum model probability;
- minimum edge;
- minimum data quality;
- allowed markets;
- allowed leagues;
- maximum number of picks per fixture;
- optional odds upper bound;
- exclude stale odds.

Important:

- store all model market probabilities, not only displayed picks;
- odds thresholds are presentation/ranking rules, not the model's knowledge;
- allow `NO BET / NO HIGH-CONFIDENCE OPPORTUNITY`.

---

# 18. Telegram bot

Private bot only.

Restrict access by Telegram user ID allowlist.

Initial commands:

```text
/start
/today
/fixtures
/predictions
/match <fixture_id>
/analyze <fixture_id>
/stats
/evaluate
/improvements
/health
/help
```

Recommended UX:

### `/today`

Show leagues and today's fixture count.

Buttons:

- Premier League
- La Liga
- Champions League
- All
- Refresh

### `/predictions`

Concise result:

```text
Premier League

Liverpool — Arsenal
20:00

1) Over 1.5
Model probability: 74%
Best captured odds: 1.42
Market no-vig probability: 68%
Estimated edge: +6 pp
Confidence: Medium
Data quality: 91%

2) BTTS — Yes
Model probability: 63%
...
```

Do not dump research essays by default.

`/match` may show detailed evidence and diagnostics.

Telegram handlers must only call application services / enqueue jobs. No business logic inside handlers.

---

# 19. API

Create an internal FastAPI control plane.

Minimum endpoints:

```text
GET  /health
GET  /ready

GET  /v1/fixtures
GET  /v1/fixtures/{id}

POST /v1/fixtures/{id}/analyze

GET  /v1/predictions
GET  /v1/predictions/{run_id}

POST /v1/jobs/discover
POST /v1/jobs/evaluate

GET  /v1/evaluations/summary
GET  /v1/improvements
```

In v1 the API need not be public.

Add authentication before exposing it outside localhost/private Docker networking.

---

# 20. Database model

The agent must design normalized SQLAlchemy models and Alembic migrations.

Minimum logical entities:

## Reference/domain

- `leagues`
- `seasons`
- `teams`
- `fixtures`
- `provider_entity_ids`

## Snapshots

- `raw_provider_payloads`
- `standings_snapshots`
- `team_form_snapshots`
- `team_statistics_snapshots`
- `availability_snapshots`
- `lineup_snapshots`
- `odds_snapshots`
- `research_documents`
- `data_quality_reports`
- `feature_snapshots`
- `match_contexts`

## Prediction

- `prediction_runs`
- `market_predictions`
- `ranked_candidates`
- `prompt_versions`
- `model_configs`

## Outcomes/evaluation

- `fixture_results`
- `prediction_settlements`
- `evaluation_runs`
- `evaluation_metrics`

## Experimentation

- `experiments`
- `experiment_variants`
- `experiment_results`
- `improvement_proposals`

## Operations

- `jobs`
- `job_attempts`
- `audit_logs`

Use UUID primary keys internally. Store external provider IDs separately.

Use UTC in the database.

---

# 21. Idempotency and reliability

Required.

Examples:

- discovering the same fixture twice must update/upsert, not duplicate;
- re-running a collector must create or reuse an appropriate timestamped snapshot;
- retrying prediction should not publish duplicate Telegram messages;
- tasks use stable idempotency keys;
- external calls use timeouts + retries with exponential backoff;
- rate limits are respected;
- provider errors are classified as retryable/non-retryable;
- failed tasks are visible through logs/status.

---

# 22. Result settlement

A scheduled worker must look for matches that should be finished but are not settled.

Process:

1. fetch final fixture result;
2. persist final score/status;
3. settle each supported market deterministically;
4. mark void/postponed/cancelled cases properly;
5. never ask an LLM whether a bet won.

Settlement must be unit tested extensively.

---

# 23. Evaluation system

Do not evaluate only "percentage of correct picks."

Required metrics where applicable:

## Probabilistic quality

- Brier score
- log loss
- calibration curve/buckets
- calibration error
- probability sharpness

## Selection quality

- hit rate
- number of selections
- abstention/coverage rate
- average captured odds
- realized ROI for a fixed 1-unit research simulation
- expected value at prediction time
- closing-line-value proxy if closing odds are captured

## Segmentation

Report by:

- league
- market
- odds bucket
- confidence bucket
- model version
- prompt version
- prediction phase
- data-quality bucket
- time period

Do not optimize based on a tiny sample.

Evaluation reports must clearly show sample size.

---

# 24. Improvement pipeline

Run weekly by default, manually triggerable.

Inputs:

- evaluation metrics;
- worst calibrated segments;
- high-confidence misses;
- source/data-quality failures;
- model disagreements if ensemble testing exists;
- latency/cost;
- missing-data patterns.

Output is a structured `ImprovementProposal`, e.g.:

```json
{
  "title": "Reduce weight of H2H context",
  "problem": "...",
  "evidence": {
    "sample_size": 138,
    "metrics": {}
  },
  "hypothesis": "...",
  "proposed_change": "...",
  "test_plan": "...",
  "risk": "low",
  "status": "PROPOSED"
}
```

Allowed statuses:

```text
PROPOSED
APPROVED_FOR_EXPERIMENT
EXPERIMENT_RUNNING
REJECTED
PROMOTED
ROLLED_BACK
```

Never auto-promote.

---

# 25. Experiment / replay framework

This is a critical long-term capability.

Create a CLI such as:

```bash
python -m sports_intelligence.replay \
  --from 2026-08-01 \
  --to 2026-08-31 \
  --variant prompt-v2
```

The replay engine must:

- use frozen historical snapshots only;
- prevent future information leakage;
- run a selected model/prompt/feature version;
- persist experiment outputs separately from production;
- compare to a baseline.

If historical snapshots do not exist, do not pretend a leak-free replay is possible.

---

# 26. LLM model experimentation

The prediction system must not be hardwired to one model.

Store provider/model per prediction run.

Support side-by-side "shadow" prediction:

- production model A;
- challenger model B;
- challenger predictions are stored but not shown as primary picks.

After sufficient sample size compare:

- Brier score;
- log loss;
- calibration;
- coverage;
- ROI/CLV research metrics;
- cost/latency.

This is the correct way to decide whether MiniMax, GPT, Kimi, GLM, etc. is "better" for this system.

---

# 27. Observability

Minimum v1:

- structured logs;
- correlation ID;
- job ID;
- fixture ID;
- prediction run ID;
- provider latency;
- provider errors;
- LLM latency;
- token usage when available;
- task duration.

`/health` verifies process health.

`/ready` verifies required dependencies such as DB and Redis.

Do not log secrets or full auth headers.

---

# 28. Testing strategy

## Unit

Must cover:

- probability normalization;
- no-vig calculations;
- edge/EV calculations;
- market settlement;
- feature calculations;
- data-quality rules;
- state transitions;
- ranking filters.

## Contract

Fixture JSON payload samples for each provider.

Ensure adapter changes do not silently alter domain schemas.

## Integration

Use test Postgres + Redis.

Test:

- fixture discovery;
- data collection;
- prediction persistence;
- queue retry behavior;
- settlement;
- Telegram formatting.

## End-to-end local smoke test

Using one configured fixture or recorded provider fixtures:

```text
discover
→ collect
→ build context
→ predict
→ persist
→ show in Telegram/test transport
→ inject/mock final result
→ settle
→ evaluate
```

This test must pass before production deployment.

---

# 29. CI

GitHub Actions on every pull request / push:

- install locked dependencies;
- Ruff;
- mypy;
- pytest unit;
- integration tests where practical;
- migration consistency check.

Do not deploy automatically to the Hetzner server in v1.

---

# 30. Documentation required from implementation agent

The repository is incomplete unless these exist:

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/DATA_MODEL.md`
- `docs/PIPELINES.md`
- `docs/TELEGRAM.md`
- `docs/LOCAL_DEVELOPMENT.md`
- `docs/DEPLOYMENT.md`
- `docs/SECURITY.md`
- `docs/IMPLEMENTATION_STATUS.md`
- `docs/adr/`

README must let a new engineer boot the project without reading an AI conversation.

---

# 31. Local-development acceptance criteria

Before server deployment, the following must work locally:

- [ ] `docker compose up` starts required services.
- [ ] database migrations run from an empty database.
- [ ] one command seeds configured leagues.
- [ ] `/health` and `/ready` work.
- [ ] private Telegram bot starts.
- [ ] `/today` returns fixtures from the configured provider.
- [ ] a fixture can be manually analyzed.
- [ ] raw provider snapshots are stored.
- [ ] a canonical MatchContext is created.
- [ ] an LLM produces schema-valid predictions.
- [ ] prediction records contain all version metadata.
- [ ] ranking respects minimum odds and edge configuration.
- [ ] Telegram shows concise predictions.
- [ ] a mocked/completed fixture can be settled.
- [ ] evaluation metrics are calculated.
- [ ] failed provider calls retry safely.
- [ ] duplicate command execution does not duplicate critical data.
- [ ] test suite passes.
- [ ] no secrets exist in Git history.

---

# 32. Production deployment target

The server already hosts Hermes.

The sports project must:

- be a separate directory;
- be a separate Docker Compose project;
- use separate containers;
- use separate network;
- use separate volumes;
- use separate `.env`;
- avoid Hermes ports;
- never stop/restart/change Hermes;
- bind Postgres/Redis only to internal Docker network;
- use Telegram long polling initially;
- expose no new public port unless required.

Before deployment, inspect server resources and existing Docker state.

If resources are inadequate, report this instead of degrading or modifying Hermes.

---

# 33. Database backup

Production must include a documented backup strategy.

MVP:

- nightly `pg_dump`;
- compressed;
- retention e.g. 7 daily backups;
- secrets excluded from dump filenames/logs;
- restore procedure documented and tested once.

Later add off-server backup.

---

# 34. Security requirements

- Telegram allowlist.
- SSH key authentication for deployment.
- Non-root container users where practical.
- No secrets in Git.
- Principle of least privilege.
- No arbitrary shell commands exposed to Telegram.
- Validate all command arguments.
- Database/Redis not public.
- Dependency versions locked.
- Production debug mode disabled.
- Sensitive raw LLM/provider headers redacted.
- Backups protected.

---

# 35. Cost controls

Every external provider may have limits.

Implement:

- request counters;
- cache;
- per-provider rate limiting;
- no duplicate API requests within freshness window;
- configurable maximum daily fixtures;
- configurable enabled leagues;
- LLM token/cost telemetry if provider returns usage.

For first local tests analyze only a few selected leagues.

---

# 36. Initial delivery milestones

The coding agent must implement in milestones.

## M0 — Architecture and repository

- repository scaffold;
- docs;
- ADRs;
- Docker;
- CI skeleton;
- config;
- dependency lock.

## M1 — Core infrastructure

- FastAPI;
- Postgres;
- Redis;
- Celery;
- migrations;
- health/readiness;
- structured logs.

## M2 — Sports provider and fixtures

- provider interface;
- first provider adapter;
- leagues config;
- fixture discovery;
- persistence;
- `/today` backend data.

## M3 — Telegram

- private bot;
- allowed user IDs;
- `/today`;
- `/fixtures`;
- `/health`.

## M4 — Match data collection

- form;
- standings;
- H2H;
- injuries;
- team stats;
- odds;
- raw snapshots;
- data quality.

## M5 — Research

- search-provider interface;
- research pipeline;
- structured claims;
- source metadata;
- graceful operation if research provider is disabled.

## M6 — Feature and context builder

- deterministic features;
- MatchContext v1;
- schema/versioning.

## M7 — Prediction

- LLM interface;
- structured output;
- prompt versioning;
- market probabilities;
- ranking/value engine;
- `/predictions`;
- Telegram output.

## M8 — Settlement and evaluation

- final results;
- deterministic settlement;
- Brier/log loss/calibration;
- segmented stats.

## M9 — Improvement and experiments

- weekly evaluator;
- proposals;
- experiment entities;
- replay CLI.

## M10 — Production readiness

- security pass;
- backups;
- resource checks;
- deployment docs;
- local E2E;
- independent code review.

Each milestone must end with:

1. tests;
2. docs update;
3. `docs/IMPLEMENTATION_STATUS.md` update;
4. Git commit with meaningful message.

---

# 37. Definition of done

The project is done for v1 when:

1. it can run for multiple days unattended;
2. scheduled fixture discovery works;
3. prediction jobs are idempotent;
4. every forecast can be reconstructed from its snapshot/version metadata;
5. Telegram provides useful concise output;
6. completed matches are settled automatically;
7. evaluation reports show probabilistic quality, not just win rate;
8. model/provider configuration can be changed without domain rewrites;
9. self-improvement only proposes/test changes and cannot silently mutate production;
10. project can be recreated from GitHub + secrets + Docker on a clean machine.

---

# 38. Non-goals for v1

Do not spend early development time on:

- public SaaS;
- payments;
- multi-user accounts;
- fancy dashboard;
- live in-play betting;
- automated bookmaker execution;
- mobile app;
- Kubernetes;
- large vector DB;
- dozens of sports;
- dozens of markets;
- autonomous code self-modification.

Build the measurement loop first.

---

# 39. Important implementation instruction to the coding agent

When a requirement is ambiguous:

- choose the simplest production-safe design;
- document the assumption in `docs/IMPLEMENTATION_STATUS.md`;
- do not block the whole implementation on minor questions.

When a major architecture change is proposed:

- create an ADR before changing it.

Do not fake integrations.

If an API key is absent, provide:

- mock/recorded adapter;
- clear disabled state;
- setup documentation.

Never mark an integration complete if it has not been exercised.

---

# 40. First product iteration

For the first real-world test, constrain scope:

- 2–4 major football leagues;
- morning predictions;
- 1X2, O/U 1.5, O/U 2.5, BTTS;
- one sports data provider;
- one odds source;
- optional web research;
- one primary prediction model;
- PostgreSQL evaluation.

Collect a meaningful sample before changing the methodology.

The architecture is intentionally larger than the first active configuration so the system can grow without a rewrite.
