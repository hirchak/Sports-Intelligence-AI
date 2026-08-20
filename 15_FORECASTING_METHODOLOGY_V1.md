# Forecasting Methodology v1
## Measurement-First Football Prediction Design

The system must not assume that an LLM alone is a superior forecaster.

V1 should create multiple measurable probability baselines and compare them.

---

# 1. Objective

Estimate calibrated probabilities for supported football markets.

Then separately determine whether a market price appears interesting.

Two different questions:

```text
A. What is the probability of the event?
B. Is the available price attractive relative to that probability?
```

Do not collapse them.

---

# 2. Initial market set

Keep small:

```text
1X2
Double chance
Over/Under 1.5
Over/Under 2.5
BTTS Yes/No
```

This is enough to build evaluation infrastructure.

---

# 3. Forecast sources

Maintain three conceptual probability sources.

## A. Market baseline

From bookmaker odds:

```text
raw implied probability
→ remove margin/no-vig
→ consensus where possible
```

Purpose:
- strongest external benchmark;
- not treated as ground truth.

## B. Statistical baseline

Start simple and auditable.

Possible first baseline:

- team scoring/conceding rates;
- home/away adjustment;
- league goal environment;
- Poisson-derived score probabilities.

Later improve with:

- xG;
- opponent adjustment;
- recency weighting;
- hierarchical/regularized models.

Do not build a huge ML model before the data pipeline is trustworthy.

## C. LLM contextual predictor

Receives MatchContext including:

- structured statistics;
- availability;
- research;
- deterministic features;
- market snapshot clearly labeled as market information.

Returns probabilities and uncertainty.

---

# 4. Why keep baselines separate?

If LLM output improves over a simple baseline, we can prove it.

If it merely echoes odds, we can detect it.

If market baseline wins, that is valuable information.

Store all three when available.

---

# 5. LLM anti-anchoring experiment

Odds can anchor the LLM.

Support two experiment variants:

```text
LLM_WITH_ODDS
LLM_WITHOUT_ODDS
```

Compare calibration/performance.

Do not assume seeing odds always helps.

---

# 6. Context importance

The LLM should reason over:

High relevance:
- recent team strength;
- home/away form;
- injuries/suspensions;
- confirmed lineup;
- schedule congestion;
- tactical/team news;
- season strength.

Medium:
- recent manager change;
- matchup/tactical context;
- competition motivation where evidence exists.

Lower default weight:
- old H2H;
- vague narratives;
- social media rumors;
- unverified "must win" claims.

---

# 7. Prediction output

For every market selection:

```text
model_probability
confidence
evidence_for
evidence_against
risk_flags
```

Confidence is not a substitute for probability.

---

# 8. Calibration

A useful 70% forecast should occur roughly 70% of the time over enough cases.

Measure by buckets.

Example:

```text
0.50–0.59
0.60–0.69
0.70–0.79
0.80–0.89
0.90+
```

Avoid overconfidence.

---

# 9. Core metrics

Use:

## Brier score

Good for probabilistic accuracy.

## Log loss

Penalizes confident wrong predictions strongly.

## Calibration

Reliability of stated probabilities.

## Coverage

How often the system is willing to present a candidate.

## Hit rate

Useful but insufficient alone.

## Research ROI simulation

For a fixed 1-unit stake model only as an analytical metric.

## Closing line comparison

If closing odds are captured later, compare forecast price quality.

---

# 10. Candidate selection

Display candidate only if policy passes.

Example configurable conditions:

```text
data_quality >= threshold
odds >= 1.30
model_probability >= threshold
edge >= threshold
supported market
odds not stale
```

Do not hard-code the threshold as a belief.

Track what would happen under different thresholds.

---

# 11. Do not optimize too early

Bad loop:

```text
20 forecasts
→ change prompt
→ 12 forecasts
→ change weights
→ repeat
```

This overfits noise.

Instead:

- collect;
- evaluate;
- keep version history;
- test challenger;
- use reasonable sample sizes;
- compare out-of-sample/future periods.

---

# 12. League segmentation

Leagues differ.

Metrics must eventually allow:

- league-specific calibration;
- market-specific calibration.

Do not create league-specific prompts/weights until data justifies it.

---

# 13. Ensemble later

After enough evidence, an ensemble may combine:

```text
statistical baseline
LLM probability
market baseline
```

But weights must be fit/evaluated from historical/future data.

Do not invent arbitrary "40% LLM + 30% odds + 30% stats" weights.

---

# 14. Abstention

A good forecaster can say:

```text
insufficient edge
insufficient data
high source conflict
```

Abstention is a feature.

Track abstention rate.

---

# 15. Improvement questions

Weekly analysis should ask:

- Is the model systematically overconfident?
- Which markets are best calibrated?
- Which leagues are weakest?
- Are late lineup forecasts better than morning forecasts?
- Does web research add measurable value?
- Does showing odds to the LLM help or anchor it?
- Which data categories correlate with large errors?
- Does challenger model improve after cost normalization?

---

# 16. V1 methodology acceptance criteria

- [ ] Market no-vig baseline exists.
- [ ] Simple statistical baseline exists or is explicitly scheduled as first analytical milestone.
- [ ] LLM predictions are separately stored.
- [ ] No arbitrary ensemble weights.
- [ ] Calibration is measured.
- [ ] LLM with/without odds can be experimentally compared.
- [ ] Prediction can abstain.
- [ ] Prompt/model versions are preserved.
