# Telegram Bot Specification
## Private Control Plane for Sports Intelligence AI

**Purpose:** define the Telegram bot as a private operational UI over the backend.  
**Non-goal:** the bot must not contain forecasting/business logic.

---

# 1. Product role

The Telegram bot is the user's primary control surface for v1.

It should answer four questions quickly:

1. What matches are being tracked today?
2. What forecasts are currently available?
3. What happened to previous forecasts?
4. Is the system healthy, and can I manually trigger/retry a job?

The bot must remain thin. It calls application services / internal API and renders results.

---

# 2. Access control

Private use only.

Required:

- allowlist of Telegram user IDs;
- reject all unknown users without exposing system details;
- no arbitrary shell commands;
- no secret/config values displayed;
- audit important manual actions.

Environment:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_ALLOWED_USER_IDS
```

---

# 3. Main navigation

Recommended persistent menu:

```text
🏠 Dashboard
⚽ Today
🎯 Predictions
📊 Results & Stats
🧪 Experiments
🛠 System
⚙️ Settings
```

For v1, commands remain available as fallback.

---

# 4. Commands

```text
/start
/dashboard
/today
/fixtures
/predictions
/match <fixture_id>
/analyze <fixture_id>
/refresh <fixture_id>
/stats
/evaluate
/improvements
/health
/settings
/help
```

Admin-only actions:

```text
/discover
/evaluate
/retry <job_id>
```

Do not expose destructive database operations through Telegram.

---

# 5. Dashboard screen

Example:

```text
Sports Intelligence

Date: 2026-08-20
Enabled leagues: 4

Today's fixtures: 18
Ready for prediction: 14
Predicted: 12
Waiting for data: 2
Failed jobs: 0

API quota:
Sports provider: 72 / 100 remaining
LLM provider: healthy

Last scheduler run: 08:00
Next refresh: 18:30
```

Buttons:

```text
[ Today's matches ]
[ Predictions ]
[ System health ]
[ Refresh ]
```

The exact quota UI is provider-specific and displayed only when supported.

---

# 6. Today flow

`/today` shows enabled leagues with counts.

Example:

```text
Today — 20 Aug

Premier League — 6
La Liga — 5
Serie A — 4
Champions League — 3
```

Buttons:

```text
[ Premier League ]
[ La Liga ]
[ Serie A ]
[ Champions League ]
[ All ]
```

League screen:

```text
Premier League

17:30 Team A — Team B   READY
20:00 Team C — Team D   PREDICTED
21:00 Team E — Team F   WAITING
```

Each fixture is clickable.

Use pagination when Telegram output would become long.

---

# 7. Match detail screen

Example:

```text
Team A — Team B
Premier League
Kickoff: 20:00 Europe/Warsaw

Pipeline status: PREDICTED
Prediction phase: MORNING
Data quality: 91%

Last data snapshot: 12:04
Last odds snapshot: 12:02
Research freshness: 38 min
```

Buttons:

```text
[ Prediction ]
[ Evidence ]
[ Odds ]
[ Data quality ]
[ Refresh data ]
[ Re-run prediction ]
```

A manual re-run creates a new prediction run. It must never overwrite the prior run.

---

# 8. Prediction screen

Default output must be concise.

Example:

```text
Team A — Team B
20:00

Top candidates

1. Over 1.5
Model probability: 74%
Captured odds: 1.42
Market no-vig: 68%
Estimated edge: +6 pp
Confidence: Medium

2. BTTS — Yes
Model probability: 63%
Captured odds: 1.72
Market no-vig: 59%
Estimated edge: +4 pp

Data quality: 91%
Forecast: MORNING
As of: 12:05
```

Buttons:

```text
[ Full probability table ]
[ Why? ]
[ Risks ]
[ Model metadata ]
```

Never use language such as "guaranteed", "safe bet", or "certain".

Allow:

```text
NO HIGH-CONFIDENCE OPPORTUNITY
```

---

# 9. Evidence screen

Detailed screen can show:

```text
Positive evidence
- home scoring form ...
- opponent defensive form ...

Negative evidence
- key player uncertainty ...
- recent schedule congestion ...

Research
- source/title/time
- extracted claim

Warnings
- confirmed lineup unavailable
```

Do not show raw multi-kilobyte JSON in Telegram.

---

# 10. Results & Stats

`/stats` default:

```text
Last 30 days

Predictions evaluated: 186
Coverage: 61%
Brier score: ...
Log loss: ...
Calibration: ...
Displayed-pick hit rate: ...
Research simulation ROI: ...

Best calibrated market: ...
Weakest segment: ...
```

Buttons:

```text
[ By league ]
[ By market ]
[ By model ]
[ By odds bucket ]
[ Last 7d ]
[ Last 30d ]
[ All time ]
```

Always show sample size.

---

# 11. Improvement flow

`/improvements` lists proposals only.

Example:

```text
#17 PROPOSED
Reduce reliance on H2H context

Evidence sample: 138 predictions
Risk: Low
```

Buttons:

```text
[ Details ]
[ Approve experiment ]
[ Reject ]
```

Do not allow "promote to production" without an explicit second confirmation.

Production changes should preferably happen through Git/config review, not one Telegram tap.

---

# 12. Settings

Initially read-mostly.

Possible settings:

- enabled leagues;
- prediction markets;
- minimum displayed odds;
- minimum model probability;
- minimum edge;
- morning run time;
- pre-kickoff refresh enabled;
- primary prediction model;
- challenger model;
- automatic notifications.

Settings changes must:

1. validate;
2. persist with audit metadata;
3. show old → new value;
4. require confirmation for high-impact changes.

No API keys in Telegram settings.

---

# 13. Automatic notifications

Optional configurable pushes:

## Morning digest

```text
Today's analysis is ready.
18 fixtures tracked.
11 predictions currently meet display thresholds.
```

## Pre-kickoff update

Only if prediction materially changed:

```text
Team A — Team B
Final lineup refresh changed Over 2.5 probability:
58% → 67%
```

## Daily settlement digest

```text
Yesterday
15 fixtures settled.
Evaluation updated.
```

## System alert

Only actionable alerts:

```text
Sports API quota below configured reserve.
Non-critical refreshes paused.
```

Avoid notification spam.

---

# 14. Telegram callback design

Do not put sensitive data or giant JSON in callback payloads.

Use short stable identifiers, e.g.:

```text
fx:view:<short_id>
fx:predict:<short_id>
league:view:<id>:<page>
stats:market:<slug>:<range>
```

Resolve details server-side.

---

# 15. Error UX

User-facing errors must be short and actionable.

Examples:

```text
Data provider temporarily unavailable.
The job was queued for retry.
```

```text
Not enough pre-match data yet.
Try again closer to kickoff.
```

```text
Daily API reserve reached.
Only critical refreshes are running.
```

Internal stack traces never go to Telegram.

---

# 16. Idempotency

Every manual action requires an idempotency key.

Repeated taps must not cause:

- duplicate fixture discovery;
- duplicate prediction publishing;
- duplicate improvement approval;
- duplicate notification.

Disable/acknowledge buttons while a job is already queued.

---

# 17. Bot architecture

```text
Telegram Update
      ↓
aiogram handler
      ↓
command/callback parser
      ↓
application service / internal FastAPI client
      ↓
job enqueue or DB read
      ↓
response DTO
      ↓
Telegram formatter
```

No provider calls directly from Telegram handlers.

No LLM calls directly from Telegram handlers.

---

# 18. Telegram v1 acceptance criteria

- [ ] Unknown users cannot access the bot.
- [ ] `/today` lists configured fixtures.
- [ ] Fixture detail screen works.
- [ ] Manual analysis queues a backend job.
- [ ] Duplicate tap does not duplicate work.
- [ ] `/predictions` shows concise ranked candidates.
- [ ] Detailed evidence is available on demand.
- [ ] `/stats` shows sample sizes and evaluation metrics.
- [ ] `/health` reports system state without secrets.
- [ ] Long lists paginate.
- [ ] Provider/LLM failures produce safe messages.
- [ ] Bot restart does not lose backend state.
