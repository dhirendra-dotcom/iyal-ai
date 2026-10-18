# Release Notes - IYAL.ai Lite v0.13.2

## Purpose

Make the Google Search-grounded market research faster, cheaper and more reliable without changing the v0.13 conversational design.

## Measured before/after (same two needs, live Vertex AI, local benchmark)

| | v0.13.0 prompt | v0.13.2 |
|---|---|---|
| Google searches per research | 3-5 | 1-2 |
| Research text length | ~3,000-3,500 chars | ~1,200-1,600 chars |
| Typical duration (successful first attempt) | 12-18 s | 5-14 s |
| Stalled calls (504 at ~45 s) | failed | retried within the per-attempt deadline; 8/8 succeeded |

Gemini 3 grounding is billed per executed search query, so fewer queries also lowers cost.

## Changes

- **Focused research brief.** One focused query, plus at most one follow-up. 2-3 options in under 220 words, ending with the most promising option.
- **Cited sources only.** Links are ranked by how many parts of the answer they support (grounding supports). Uncited chunks are dropped, up to 5 links.
- **Bounded retry.** Each attempt has a 25 s deadline, which the SDK also sends as the server deadline. One retry on 429, 499 (cancelled at the deadline), 5xx (including 504) or timeout.
- **No repeated research in a conversation.** The same need (normalized object, barrier, intent, constraints and country) reuses the earlier research. The chat shows no duplicate message. Live searches are capped at 3 per conversation.
- **Per-instance cache.** Identical needs from other conversations reuse a successful result for 6 hours. Failures are never cached.
- **Fewer wasted agent round trips.** The `present_adaptation_options` description now lists the allowed `context_type` and strategy values. Its errors name the bad value and the allowed set, and inputs are case-normalized. In v0.13.1 the first call failed in every observed market turn, costing a full model round trip of 5-6 s.
- **Prompt.** Search once per distinct need, use one focused query, and search first when the user explicitly asks for existing products.
- **Logging.** `tool_complete` for search now records `search_query_count`, `attempt_count`, `search_duration_ms`, `cache_hit`, `reused` and `error_code`. Rejected tool calls log a specific `error_type`.

## Not changed

The v0.13 market-text contract and UI, the landing page, layout, the CAD and preview paths, and the market-search guards.

## Main agent model: stalled-request retry

Live logs showed the slowest part of a market turn was not research but the main agent's Gemini calls. Vertex AI accepted the request, then sent nothing for 59-222 s. Normal calls return their first chunk in 2-16 s, and `gemini-3.8-flash` is only served from the `global` endpoint.

- New `app/resilient_model.py` wraps the ADK Gemini model. If no output arrives within `AGENT_MODEL_FIRST_CHUNK_TIMEOUT_SECONDS` (default 40), the request is cancelled and resent once (`AGENT_MODEL_MAX_ATTEMPTS`, default 2).
- Only the wait for the first chunk is bounded. A stream that has started is never interrupted, and the final attempt has no limit, so no turn fails that would previously have succeeded.
- A retry logs `model_first_chunk_timeout` and, on success, `model_retry_recovered`.
- The SDK's own timeout and retry were not used. A client-side deadline raises a timeout that the SDK does not retry, and it also caps the whole stream.