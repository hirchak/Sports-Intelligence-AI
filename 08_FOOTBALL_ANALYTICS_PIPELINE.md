# Football Analytics Pipeline
## Exact Pre-Match Information Flow

This document defines what the system should collect and how a football fixture moves from discovery to forecast.

The pipeline is intentionally split into deterministic services, data collectors and LLM-assisted analytical steps.

---

# 1. Core rule

Do not ask an LLM:

> "Research Team A vs Team B and predict it."

Instead:

```text
discover fixture
→ collect auditable data
→ normalize
→ verify freshness/quality
→ calculate deterministic features
→ freeze MatchContext
→ produce probabilities
→ compare against market
→ persist everything
→ publish concise result
```

---

# 2. Forecast phases

Every forecast has a phase.

## MORNING

Generated during daily run.

Uses:

- scheduled fixture;
- recent team data;
- standings;
- available injuries/suspensions;
- morning odds;
- web/news context.

## PREMATCH_FINAL

Optional refresh around T-90/T-60.

Adds:

- confirmed/probable lineups;
- late availability news;
- latest odds;
- late context.

Never overwrite MORNING.

Later evaluation should compare both.

---

# 3. Discovery phase

Goal: build today's target fixture set.

Input:

- date;
- enabled leagues;
- provider league IDs.

Output:

- canonical fixture records;
- job records.

Filters:

- league enabled;
- supported fixture status;
- kickoff within configured window;
- not cancelled;
- not duplicate.

For a provider that can return all fixtures for a date, fetch broadly once and filter locally rather than issuing one call per league where this is quota-efficient.

---

# 4. Structured collection categories

## 4.1 Fixture metadata

Collect:

- fixture external ID;
- competition;
- country;
- season;
- stage/round;
- kickoff UTC;
- home/away team IDs;
- venue;
- status;
- referee if available.

## 4.2 Recent form

For each team target both:

- last 5;
- last 10.

Derived fields:

- W/D/L;
- goals for;
- goals against;
- points per game;
- scored in X of N;
- conceded in X of N;
- clean sheets;
- failed-to-score rate;
- first-half scoring if available;
- opponent quality indicator later.

Do not mix future fixtures into rolling form.

## 4.3 Home / away split

Home team:

- recent home matches.

Away team:

- recent away matches.

Calculate the same form metrics separately.

This is generally more meaningful than H2H alone.

## 4.4 Season strength

Where available:

- league position;
- games played;
- points;
- goals for/against;
- goal difference;
- home/away record;
- shots;
- shots on target;
- possession;
- xG/xGA;
- expected points if provider supports it.

## 4.5 Schedule and fatigue

Derive:

- days since last match;
- matches in previous 7 days;
- matches in previous 14 days;
- travel context if reliably available;
- extra-time participation in recent match if available.

## 4.6 Availability

Collect:

- injuries;
- suspensions;
- sidelined players;
- expected return;
- probable status;
- confirmed lineup when available.

Create impact flags rather than merely counting absences.

Examples:

```text
starting_goalkeeper_missing
top_scorer_missing
multiple_starting_defenders_missing
rotation_expected
```

Player impact scoring should initially be simple and transparent.

## 4.7 Tactical/team news

Web research may identify:

- manager statements;
- intended rotation;
- formation changes;
- prioritization of another competition;
- internal disruption;
- late fitness tests;
- credible lineup leaks;
- recent manager change.

Every claim requires source metadata.

## 4.8 Head-to-head

Collect a limited recent sample.

Use only as secondary context.

Do not allow H2H to dominate because:

- squads change;
- coaches change;
- old matches can be irrelevant.

## 4.9 Odds

For supported markets capture:

- bookmaker;
- market;
- selection;
- decimal odds;
- retrieved_at.

Prefer several bookmakers if cost permits.

Generate:

- best observed price;
- median/consensus price where meaningful;
- implied probability;
- no-vig probability;
- market overround;
- price movement.

## 4.10 Optional contextual data

Add only when reliable and cheap:

- extreme weather;
- pitch/venue anomalies;
- referee tendencies;
- major travel disruptions.

Do not add noisy features simply because they exist.

---

# 5. Research pipeline

The web/news research component should not write the final prediction.

Flow:

```text
search queries
→ candidate sources
→ relevance filter
→ extract factual claims
→ de-duplicate claims
→ source confidence
→ structured research snapshot
```

Suggested query families:

```text
"<home team> injuries <match date>"
"<away team> injuries <match date>"
"<home team> manager press conference <opponent>"
"<away team> lineup <opponent>"
"<team> suspension"
"<fixture> team news"
```

The research extractor returns structured claims:

```json
{
  "claim_type": "availability",
  "team_id": "...",
  "claim": "Player X is expected to miss the match",
  "source": "...",
  "published_at": "...",
  "retrieved_at": "...",
  "confidence": 0.84
}
```

Conflicting claims are retained and flagged.

---

# 6. Data quality gate

Before prediction evaluate:

- freshness;
- completeness;
- source conflicts;
- stale odds;
- missing fixture metadata;
- missing team form;
- missing lineup close to kickoff;
- provider errors.

Example:

```text
0.90–1.00  excellent
0.80–0.89  good
0.65–0.79  usable with warnings
<0.65      abstain by default
```

Thresholds must be configurable and empirically reviewed.

---

# 7. Deterministic feature set v1

Candidate features:

```text
home_last5_ppg
away_last5_ppg
home_last10_goals_for_per_match
away_last10_goals_for_per_match
home_last10_goals_against_per_match
away_last10_goals_against_per_match
home_home_split_ppg
away_away_split_ppg
home_scored_rate
away_scored_rate
home_conceded_rate
away_conceded_rate
home_clean_sheet_rate
away_clean_sheet_rate
league_position_delta
rest_days_delta
fixture_congestion_delta
important_absence_delta
market_home_no_vig
market_draw_no_vig
market_away_no_vig
market_over15_no_vig
market_over25_no_vig
market_btts_yes_no_vig
odds_move_home
odds_move_over25
```

Feature names and calculations must be versioned.

---

# 8. MatchContext assembly

Only approved/normalized data enters MatchContext.

Order:

1. fixture identity;
2. team form;
3. home/away form;
4. season strength;
5. schedule;
6. availability;
7. H2H;
8. research claims;
9. market snapshot;
10. deterministic features;
11. data quality.

Store `as_of`.

---

# 9. Prediction stage

The prediction model receives MatchContext only.

It returns probabilities for all supported selections, not just one favorite.

Initial markets:

```text
1X2
Double chance
Over/Under 1.5
Over/Under 2.5
BTTS Yes/No
```

Required:

- probabilities;
- evidence for;
- evidence against;
- risk flags;
- confidence;
- abstain flag.

No bookmaker recommendation language.

---

# 10. Validation stage

Normal Python code validates:

- schema;
- probability bounds;
- 1X2 sums;
- contradictory outputs;
- missing required markets;
- data-quality restrictions.

Invalid LLM output:

1. one structured repair attempt;
2. if still invalid, fail prediction safely.

---

# 11. Ranking stage

Ranking is deterministic.

It uses:

- model probability;
- market no-vig probability;
- captured odds;
- edge;
- expected value;
- data quality;
- configured market whitelist;
- minimum odds.

It may return zero candidates.

Store all probabilities even when not displayed.

---

# 12. Publishing stage

Publish to Telegram only after persistence succeeds.

Order:

```text
prediction persisted
→ ranked candidates persisted
→ publish message
→ publish receipt persisted
```

This prevents "Telegram showed a prediction that the DB never recorded."

---

# 13. Post-match pipeline

After expected match end:

```text
result collector
→ result validation
→ deterministic market settlement
→ prediction settlement
→ evaluation metrics
→ aggregate stats
```

Post-match workers must never alter the original prediction.

---

# 14. Daily / weekly evaluation

Daily:

- settle completed matches;
- update aggregates;
- surface errors.

Weekly:

- calibration by market;
- performance by league;
- model comparisons;
- high-confidence misses;
- data-quality failure patterns;
- API cost/latency;
- improvement proposals.

---

# 15. What should use an LLM?

Use LLM:

- web claim extraction/synthesis;
- contextual football reasoning;
- probability estimation/challenger model;
- improvement hypothesis generation.

Do not use LLM:

- scheduler;
- API quota manager;
- normalization;
- feature calculations;
- probability math;
- no-vig;
- EV;
- market settlement;
- DB migrations;
- duplicate detection;
- result truth.

---

# 16. Failure behavior

If research fails:
- continue if structured data quality remains sufficient;
- mark research unavailable.

If odds fail:
- model probabilities may still be stored;
- do not calculate market edge until odds exist.

If injuries are unavailable:
- lower data quality.

If fixture status changes/postponed:
- cancel pending prediction jobs safely.

If model fails:
- retain collected context;
- retry according to policy;
- never discard evidence.

---

# 17. First real-world configuration

Start narrower than the architecture.

Suggested:

- 2–4 leagues;
- MORNING phase;
- optional PREMATCH_FINAL for selected fixtures;
- one structured provider;
- one odds provider/source;
- research enabled for a limited fixture count;
- one primary runtime model;
- one challenger optionally in shadow mode.

The purpose of the first month is to build trustworthy data and evaluation, not to maximize the number of picks.
