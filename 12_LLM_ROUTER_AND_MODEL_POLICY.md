# LLM Router and Model Policy
## Runtime Models, Providers, Fallback and A/B Evaluation

Development models and runtime prediction models are separate concerns.

OpenCode is used to build the software.

The running application calls model APIs through a provider abstraction.

---

# 1. Runtime providers

The architecture should support multiple configured providers such as:

```text
OpenCode Go API
MiniMax direct API
OpenAI API
future compatible providers
```

Do not hard-wire business logic to one vendor SDK.

---

# 2. OpenCode Go runtime usage

Current OpenCode Go documentation exposes API endpoints for Go models.

Examples documented by OpenCode include:

```text
https://opencode.ai/zen/go/v1/chat/completions
https://opencode.ai/zen/go/v1/responses
https://opencode.ai/zen/go/v1/messages
```

Different Go models use different compatible request styles.

Current docs:
- https://opencode.ai/docs/go/

Therefore OpenCode Go can be implemented as a runtime provider adapter, subject to the user's subscription limits/terms/current model availability.

Do not assume model IDs remain permanent.

Fetch/configure them explicitly.

---

# 3. Unified internal interface

Example:

```python
class LLMProvider(Protocol):
    async def generate_structured(
        self,
        *,
        task_type: str,
        model: str,
        system_prompt: str,
        payload: dict,
        output_schema: type[BaseModel],
        request_id: str,
    ) -> LLMResult:
        ...
```

`LLMResult`:

```text
parsed_output
raw_response_reference
provider
model
latency
usage
finish_reason
request_id
```

---

# 4. Provider adapters

Implement separately:

```text
OpenCodeGoProvider
OpenAIProvider
MiniMaxProvider
MockLLMProvider
```

Provider adapter responsibilities:

- auth;
- endpoint style;
- structured-output support;
- JSON parsing;
- usage fields;
- timeouts;
- retries;
- provider-specific errors.

Domain code sees normalized results.

---

# 5. Model Router

Create:

```text
ModelRouter
```

Do not let the LLM choose which LLM should be called.

Routing is deterministic/config-driven.

Input:

```json
{
  "task_type": "prediction_primary",
  "required_capabilities": ["structured_output"],
  "quality_tier": "high",
  "budget_class": "normal"
}
```

Output:

```json
{
  "provider": "opencode_go",
  "model": "deepseek-v4-pro",
  "fallbacks": [
    {"provider": "minimax", "model": "..."}
  ]
}
```

---

# 6. Task routes

Example configuration:

```yaml
routes:
  research_extract:
    primary:
      provider: opencode_go
      model: minimax-m3

  prediction_primary:
    primary:
      provider: opencode_go
      model: deepseek-v4-pro
    fallbacks:
      - provider: minimax
        model: <configured>

  prediction_challenger:
    primary:
      provider: opencode_go
      model: kimi-k3

  improvement_analysis:
    primary:
      provider: opencode_go
      model: glm-5.3
```

These are configuration examples, not permanent claims about model quality.

---

# 7. Fallback rules

Fallback on:

- timeout;
- temporary provider outage;
- retryable 5xx;
- rate limit when alternate route is allowed;
- invalid structured output after repair attempt.

Do not fallback silently for a primary production prediction without recording it.

Prediction run must show the actual provider/model used.

---

# 8. Model health

Maintain health state:

```text
HEALTHY
DEGRADED
RATE_LIMITED
UNAVAILABLE
```

Based on:

- recent error rate;
- latency;
- rate-limit status.

Router may avoid an unhealthy provider.

---

# 9. Cost/budget

Capture provider usage where available.

Track by:

- task type;
- provider;
- model;
- date;
- prediction run.

Set optional budgets:

```text
max_llm_calls_per_day
max_challenger_calls_per_day
max_research_llm_calls_per_fixture
```

---

# 10. Primary vs challenger

Do not swap the production predictor because one model "feels smarter."

Use shadow evaluation.

Example:

```text
Primary:
  shown in Telegram

Challenger:
  same MatchContext
  prediction stored
  not used for primary publication
```

After sufficient data compare:

- Brier;
- log loss;
- calibration;
- coverage;
- segment performance;
- latency;
- cost.

---

# 11. Prompt/model identity

Prediction cache key:

```text
context_hash
+ prompt_hash
+ provider
+ model
+ decoding config
```

If any component changes, it is a distinct run.

---

# 12. Structured output policy

For critical outputs prefer:

- native JSON schema where supported;
- strict Pydantic validation;
- JSON-only prompt fallback;
- one repair attempt.

Never rely on regex parsing of a long natural-language answer for probabilities.

---

# 13. Temperature policy

Forecasting should default to low/non-creative sampling.

Exact parameters are model-specific and must be benchmarked.

Store them per run.

A model that does not expose a parameter should not be forced into a fake abstraction.

---

# 14. Model disagreement

If primary and challenger disagree strongly:

Store:

```text
disagreement_score
```

Optionally surface it as a risk signal.

Do not automatically average incompatible outputs without an evaluated ensemble method.

---

# 15. Router acceptance criteria

- [ ] OpenCode Go can be configured as one runtime provider.
- [ ] Direct MiniMax/OpenAI adapters can coexist.
- [ ] Provider/model are config, not hard-coded.
- [ ] Actual provider/model recorded per run.
- [ ] Fallback is auditable.
- [ ] Provider health is measured.
- [ ] Primary/challenger shadow mode exists.
- [ ] Identical prediction requests can be cached by hashes.
