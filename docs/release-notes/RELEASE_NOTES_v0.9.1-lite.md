# Iyal.ai v0.9.1 Lite — Memory Bank write reliability + latency patch

v0.9.1 is a focused patch on top of v0.9.0.

## Fixed: explicit outcomes now reach Memory Bank

- `/api/sessions/{session_id}/outcomes` now creates a safe pre-extracted adaptation-outcome fact and submits it directly to the configured standalone Memory Bank.
- The write uses `wait_for_completion=false`, so Memory Bank generation/consolidation is asynchronous and does not block the outcome response.
- Added structured logs: `memory_candidate_created`, `memory_write_started`, `memory_write_success`, `memory_write_failed`.
- The existing Gemini-controlled `remember_adaptation_preference` path remains for conversational preferences/fit feedback.
- Direct outcome facts intentionally exclude medical/symptom text and object-specific measurements.

## Latency changes

- Disabled `research_adaptation_options` from the live agent tool list. Market search and design-knowledge retrieval are now separate so a BUY_EXISTING check does not also pay design-knowledge latency.
- Default Lite thinking level changed from `medium` to `low` (override with `GEMINI_THINKING_LEVEL`).
- Main-agent response budget reduced from 8192 to 4096 tokens.
- Grounded product-search response budget reduced from 4096 to 2048 tokens.
- Product-search HTTP timeout defaults to 45 seconds and GenAI SDK transport retries are limited to one attempt.
- The extra retry for malformed market-search JSON is disabled by default; opt in with `PRODUCT_SEARCH_RETRY_UNPARSEABLE=true`.

## New configuration

```text
PRODUCT_SEARCH_TIMEOUT_SECONDS=45
PRODUCT_SEARCH_RETRY_UNPARSEABLE=false
```

## Expected local Memory Bank logs after Save outcome

```text
event_type=adaptation_outcome
event_type=memory_candidate_created
event_type=memory_write_started
event_type=memory_write_success
```

Memory generation itself is a managed long-running operation, so the memory may appear shortly after the write is accepted.
