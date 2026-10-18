# Iyal.ai v0.13.3 Lite

## v0.13.3: demo-scenario improvements

See `RELEASE_NOTES_v0.13.3.md` for the changes and `LOCAL_DEPLOYMENT.md` to run locally and rehearse the three demo scenarios.

## v0.13.2: faster, cheaper market research

See `docs/release-notes/RELEASE_NOTES_v0.13.2.md`. New optional settings, all with safe defaults:

```text
PRODUCT_SEARCH_ATTEMPT_TIMEOUT_SECONDS=25   per-attempt deadline (also the server deadline)
PRODUCT_SEARCH_MAX_ATTEMPTS=2               retries only 429 / 499 / 5xx / timeouts
PRODUCT_SEARCH_MAX_PER_SESSION=3            live grounded searches per conversation
PRODUCT_SEARCH_MAX_SOURCES=5                source links shown, most-cited first
PRODUCT_SEARCH_CACHE_TTL_SECONDS=21600      reuse identical searches across sessions (0 disables)
PRODUCT_SEARCH_CACHE_MAX_ENTRIES=128        per-instance cache size
AGENT_MODEL_FIRST_CHUNK_TIMEOUT_SECONDS=40  main agent: resend once if no output by then (0 disables)
AGENT_MODEL_MAX_ATTEMPTS=2
```

## v0.13.1: landing page at `/`

v0.13.1 is v0.13.0 plus a landing page. The market-research behaviour from v0.13.0 is unchanged.

- The static landing page lives in `site/`. It was copied from `arthistics/sites/iyal-personal-fit/dist`, with the hero image converted to WebP.
- FastAPI serves the landing page at `/` as the last mount, so `/api/...`, `/health` and `/app/` are unaffected. The JSON root response is only registered when `site/` is missing.
- "Talk to Iyal" opens the chat at `/app/`.
- "Continue with Iyal" opens `/app/#starter=<text>`. The URL fragment is never sent to the server. The chat prefills the message box, clears the fragment, and waits for the person to press Send.
- Cloud Run service `iyalaiv3` runs this release with the same service account, scaling, Sessions and Memory Bank as `iyalaiv2`.

Iyal.ai Lite runs the native browser UI + FastAPI + one ADK agent in a single Cloud Run service. v0.13.0 simplifies market research: Google Search-grounded `response.text` is displayed directly in the conversation with grounding links below it, while the Solution Workspace shows only market-research progress/completion status.

## Runtime

```text
Browser
  -> Cloud Run (FastAPI + ADK root agent)
       -> Gemini / Vertex AI
       -> Google Search grounding
       -> GCS artifacts
       -> Agent Platform Sessions (optional)
       -> Memory Bank (optional)
```

Cloud Run remains the execution runtime. The Agent Runtime ID is only the backing resource for managed Sessions.

## v0.13.0 highlights

- `search_existing_products` no longer asks Gemini to produce application-defined product JSON.
- The tool returns grounded conversational `market_text` plus Google Search grounding links.
- Market research is rendered in the Conversation pane under a dedicated **Market research** message.
- Grounded source links are displayed directly beneath the market-research response.
- The Solution Workspace shows only **Market research — In progress / Completed / Could not complete** status, including grounded-source count when available.
- The root agent is instructed not to repeat the full market-research response after the tool result is already displayed.
- The prior JSON parse/retry failure path is no longer part of the live market-search flow.
- Existing viewport layout, inline generated image, inline 3D viewer, and artifact URL/loading safety behavior are retained.
- Release/build naming remains simple: `v0.13.0`; `inline-chat` is not part of the release name.

## Local run

Install dependencies and configure `backend/.env`, then:

```bash
./scripts/run-lite.sh
```

Windows PowerShell:

```powershell
.\scripts\run-lite.ps1
```

Open `http://127.0.0.1:8000/app/`.

Without Agent Platform IDs:

```text
SESSION_DB_URL set -> DatabaseSessionService
otherwise          -> InMemorySessionService
Memory Bank        -> disabled
```

## Managed Sessions + Memory Bank

Provision once per environment if you have not already done so:

```bash
python scripts/provision-agent-context.py \
  --project YOUR_PROJECT_ID \
  --location asia-south1
```

Use the printed values:

```text
AGENT_PLATFORM_LOCATION=asia-south1
VERTEX_SESSION_RUNTIME_ID=...
VERTEX_MEMORY_BANK_ID=...
MEMORY_ENABLED=true
```

**Existing Agent Platform Session/Memory Bank resources are reused by v0.13.0. Do not provision again solely for this release.**

`services.py` selects Sessions in this order:

```text
VERTEX_SESSION_RUNTIME_ID -> VertexAiSessionService
SESSION_DB_URL            -> DatabaseSessionService
otherwise                 -> InMemorySessionService
```

The browser retains an opaque `iyal_user_id` in `localStorage`. For production authentication, bind `user_id` server-side to the authenticated user's immutable identity instead of trusting a browser-provided ID.

## Memory behavior

Memory is not generated for every message.

- Explicit outcome feedback is converted to a safe pre-extracted fact and submitted to Memory Bank in a background task.
- Gemini may call `remember_adaptation_preference` for durable design preferences/fit feedback.
- `LoadMemoryTool` retrieves prior memories only when useful.
- Do not persist diagnoses, symptoms, contact details or object-specific measurements as intended personalization.

An asynchronous Memory Bank write now logs:

```text
memory_candidate_created
memory_write_started
memory_write_accepted
```

`memory_write_accepted` means the GenerateMemories request was accepted; consolidation can still create, update, merge or omit a memory.

### Verify Memory Bank directly

Use the same user ID as the browser when verifying application memories. In browser DevTools:

```javascript
localStorage.getItem('iyal_user_id')
```

Then:

```bash
python scripts/test-memory-bank.py \
  --project YOUR_PROJECT_ID \
  --location YOUR_LOCATION \
  --memory-bank-id YOUR_MEMORY_BANK_ID \
  --user-id usr-... \
  --list-only
```

For a blocking write + retrieval smoke test, omit `--list-only`.

## Market grounding rule

The Python tool guard, not just the prompt, requires a live market-search attempt before these strategies are presented:

```text
buy_existing
modify_object
custom_cad (unless explicitly requested)
standard_adaptation
edge_protection
visual_cue
impact_padding
reach_access
custom_environment_fixture
```

These pure no-purchase strategies are exempt:

```text
change_technique
path_clearance
furniture_repositioning
professional_help
```

If Google Search fails, Iyal.ai may continue with generic low-risk guidance but must not claim current product evidence.

## Current root tools

```text
search_existing_products
present_adaptation_options
present_measurement_plan
register_usage_video
measure_object_from_capture
register_manual_measurement
validate_design
generate_3d_design
generate_usage_preview
generate_environment_preview
assess_support_need
offer_product_support
```

When Memory Bank is enabled, `LoadMemoryTool` and `remember_adaptation_preference` are also registered.

There are no extra intake/design/support sub-agents in this release.

## Model timing logs

For each logical model request, look for:

```text
model_request_start
model_first_chunk
model_request_complete
```

`model_request_complete` is emitted only for ADK's final aggregated `partial=False` response, so it no longer repeats for each streaming chunk.

Tool logs remain:

```text
tool_start
tool_complete
tool_error
```

This makes it possible to distinguish model latency from tool latency.

## Deployment

The deployment script no longer sends Agent Search variables or `GEMINI_THINKING_LEVEL`.

Example:

```bash
export REGION=asia-south1
export AGENT_PLATFORM_LOCATION=asia-south1
export VERTEX_SESSION_RUNTIME_ID=...
export VERTEX_MEMORY_BANK_ID=...
export MEMORY_ENABLED=true

./scripts/deploy-lite.sh \
  /path/to/iyal-v0.13.0 \
  YOUR_ARTIFACT_BUCKET \
  YOUR_RUNTIME_SERVICE_ACCOUNT
```

The script fails fast if `MEMORY_ENABLED=true` but no Memory Bank ID is supplied.

## Packaging

```bash
./scripts/package-lite.sh
```

The clean ZIP excludes virtual environments, caches, `.env` files, generated artifacts and logs.
