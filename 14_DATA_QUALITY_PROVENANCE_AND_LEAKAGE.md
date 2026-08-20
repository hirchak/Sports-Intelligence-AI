# Data Quality, Provenance and Leakage Control

Forecast evaluation is worthless if the system cannot prove what information was available before kickoff.

This document is mandatory.

---

# 1. Provenance rule

Every non-derived fact must be traceable to:

```text
provider/source
external identifier or URL
retrieved_at
published/observed time where available
raw snapshot/reference
normalizer version
```

Every derived feature must be traceable to source snapshots.

---

# 2. `as_of`

Every prediction has an `as_of`.

Only facts considered available at or before `as_of` may enter that MatchContext.

Examples:

Allowed for a 12:00 forecast:
- injury article published 10:00;
- odds captured 11:58;
- standings captured 08:00.

Not allowed:
- confirmed lineup published 18:45;
- closing odds captured 19:59;
- final result.

---

# 3. Publication time vs retrieval time

Store both when possible.

A page retrieved at 12:00 might have been published yesterday.

A page retrieved after kickoff might describe pre-kickoff information, but it still must not automatically enter historical replay unless reliable availability timing is known.

When uncertain, mark provenance uncertain.

---

# 4. Snapshot immutability

Once a MatchContext is used for a prediction:

- do not mutate it;
- create a new context for refresh.

Example:

```text
MORNING context 10:00
PREMATCH_FINAL context 18:55
```

Both remain stored.

---

# 5. Source conflict model

Do not "resolve" conflicting news by deleting one claim.

Example:

```text
Source A: Player X ruled out
Source B: Player X faces late fitness test
```

Store both.

Quality report:

```text
availability_conflict=true
```

Prediction model sees the conflict and confidence.

---

# 6. Freshness scoring

Each category has expected freshness.

Example:

```text
standings: stable
team historical form: stable until new game
injury news: moderately volatile
odds: volatile
lineups: highly time-sensitive near kickoff
```

Quality calculation weights freshness according to category.

---

# 7. Missingness

Missing data is information about uncertainty.

Never convert:

```text
missing injury data
```

into:

```text
no injuries
```

Use explicit states:

```text
KNOWN_NONE
KNOWN_PRESENT
UNKNOWN
STALE
CONFLICTED
```

---

# 8. Provider coverage flags

If provider documents field/league coverage, store coverage metadata.

A null field can mean:

- truly zero/none;
- unavailable for this league;
- provider failure;
- not yet published.

These are different.

---

# 9. Data Quality Report

Example dimensions:

```text
fixture_identity       1.00
form                    0.95
season_stats            0.90
availability            0.70
odds                    0.95
research                0.80
lineups                  N/A for MORNING
source_conflict         penalty
overall                 0.86
```

Report includes:

- critical missing;
- stale fields;
- conflicts;
- provider errors;
- can_predict.

---

# 10. Replay leakage controls

Replay takes:

```text
fixture_id
historical_as_of
variant
```

Database queries must explicitly constrain:

```text
snapshot.retrieved_at <= historical_as_of
```

For news where publication timing is known:

```text
published_at <= historical_as_of
```

Closing odds must not leak into morning forecast replay.

---

# 11. Test leakage deliberately

Create tests that plant forbidden future rows.

Example:

- morning context at 10:00;
- lineup snapshot at 18:45;
- context builder replayed at 10:00.

Test must prove lineup is excluded.

Same for:

- final result;
- later injury correction;
- closing odds.

---

# 12. Provenance in UI

Telegram detail screen should show compact source timing:

```text
As of: 10:05
Sports snapshot: 09:58
Odds: 10:02
Research: latest 09:47
```

Full provenance remains in DB/API.

---

# 13. Quality acceptance criteria

- [ ] Missing != zero/none.
- [ ] Every prediction has `as_of`.
- [ ] MatchContext immutable after prediction.
- [ ] Source and retrieval time stored.
- [ ] Conflicts preserved.
- [ ] Replay filters future snapshots.
- [ ] Automated tests demonstrate no future leakage.
