# Open Questions and Initial Configuration Defaults

This file separates product decisions from implementation.

The coding agent must not silently invent answers to unresolved product questions.

---

# 1. Decisions already made

## Project

- private personal project;
- football first;
- modular backend;
- local development first;
- GitHub source of truth;
- Docker Compose;
- later Hetzner deployment;
- Hermes remains independent;
- private Telegram bot.

## Runtime

- Python backend;
- PostgreSQL;
- Redis;
- job scheduler/workers;
- LLM provider abstraction;
- sports data provider abstraction;
- odds provider abstraction;
- web/search provider abstraction.

## Evaluation

- store every prediction;
- settle automatically;
- evaluate calibration/performance;
- improvement proposals are human-gated.

---

# 2. Provisional defaults

These can be changed through config.

```yaml
timezone: Europe/Warsaw

forecast_phases:
  morning:
    enabled: true
  prematch_final:
    enabled: false

markets:
  - 1x2
  - double_chance
  - over_under_1_5
  - over_under_2_5
  - btts

display:
  min_decimal_odds: 1.30
  max_candidates_per_fixture: 3

research:
  enabled: true
  max_queries_per_fixture: 6

challenger:
  enabled: false
```

Do not treat these as optimized values.

---

# 3. Open decision: sports provider

Candidates:

```text
API-Football / API-Sports
Sportmonks
```

Decision criteria:

- leagues needed;
- free/paid quota;
- injuries;
- lineups;
- historical stats;
- xG availability;
- odds quality;
- batch/include efficiency;
- cost.

MVP can begin with API-Football if account/key already exists or is easiest.

Create ADR when chosen.

---

# 4. Open decision: odds source

Options:

- same sports provider if adequate;
- dedicated odds API later.

Criteria:

- pre-match coverage;
- bookmakers;
- market coverage;
- historical/closing odds;
- cost;
- update freshness.

Architecture must not block later replacement.

---

# 5. Open decision: web/search provider

Requirements:

- current news search;
- source URL/title/date;
- affordable API;
- stable terms.

Research must be optional so system works without it.

---

# 6. Open decision: primary runtime predictor

Potential providers available to user include:

- OpenCode Go API;
- MiniMax direct API;
- OpenAI API.

Do not decide based only on coding benchmarks.

Run shadow prediction evaluation.

---

# 7. Open decision: enabled leagues

Start with 2–4.

Possible initial examples:

```text
Premier League
La Liga
Serie A
Bundesliga
Champions League
```

The user selects final set.

Do not hard-code all five.

---

# 8. Open decision: morning run time

Provisional:

```text
08:00 Europe/Warsaw
```

Should be configurable.

A second discovery refresh may be useful later if fixtures change.

---

# 9. Open decision: pre-match refresh

Provisional architecture supports:

```text
T-90 or T-60
```

Keep disabled until provider quota and lineup coverage are understood.

---

# 10. Open decision: automatic Telegram push

Possible modes:

```text
manual only
morning digest
all predictions
only high-ranked candidates
material pre-match changes
```

Start conservative.

---

# 11. Open decision: data-quality threshold

Do not set based on intuition permanently.

Provisional default can be used for plumbing tests, then calibrated from failure analysis.

---

# 12. Open decision: prediction methodology

V1 should compare:

- market baseline;
- simple statistical baseline;
- LLM predictor.

Do not prematurely choose ensemble weights.

See:
`15_FORECASTING_METHODOLOGY_V1.md`.

---

# 13. Rule for coding agent

If an open question is required to continue implementation:

1. prefer a reversible config/default;
2. document it in `docs/IMPLEMENTATION_STATUS.md`;
3. do not hard-wire it;
4. continue unless the choice creates expensive irreversible work.

If truly irreversible/high-impact, stop that specific decision and surface it.
