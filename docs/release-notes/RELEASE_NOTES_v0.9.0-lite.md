# Iyal.ai v0.9.0 Lite

## Scope

This release implements only the agreed next items: concrete market-option cards, internal-label cleanup, managed Agent Platform Sessions for Cloud Run, and optional Memory Bank integration.

## Market options

- Google Search-grounded product results now include `product_type` and a validated `source_url` when the URL is actually available in search evidence.
- The Live Solution panel shows up to five concrete product cards with fit rationale, limitations, seller/brand metadata, grounded price/availability when available, and a source link when verified.
- Users can choose **Try this option**, **Compare more**, or **Continue with custom design** without retyping the decision.
- The agent prompt now requires concrete options to be named when product search found them; it must not merely say that commercial products exist.

## UI cleanup

- Internal strategy enums such as `custom_cad` and `buy_existing` are converted to user-facing labels.
- Empty/internal option titles are suppressed rather than leaking labels such as `custom_cad:` into the workspace.

## Managed Sessions

- Added optional `VertexAiSessionService` support. Cloud Run remains the application runtime; the configured Agent Runtime ID is used only as the managed Sessions backing resource.
- The browser now creates one opaque `iyal_user_id` in `localStorage` and reuses it across new conversations in that browser.
- New custom session IDs use Agent Platform-compatible `ses-...` values (lowercase letters/numbers/hyphens).
- Existing `DatabaseSessionService` and `InMemorySessionService` paths remain as fallbacks when no managed Sessions ID is configured.

Configuration:

```text
AGENT_PLATFORM_LOCATION=asia-south1
VERTEX_SESSION_RUNTIME_ID=<runtime-id>
```

## Memory Bank

- Added optional `VertexAiMemoryBankService` wiring to the ADK Runner.
- Added `LoadMemoryTool` only when Memory Bank is configured, so Gemini retrieves prior adaptation context on demand rather than injecting memory on every turn.
- Added controlled memory generation: the agent must first queue an explicit durable adaptation preference, real-world fit feedback, or adaptation outcome; an `after_agent_callback` then sends only the recent event window to Memory Bank.
- Added a deterministic memory policy that rejects obvious health/symptom content from the long-term personalization candidate. The prompt also prohibits persisting diagnoses, symptoms, treatment/medication information, contact details, raw media, or object-specific measurements.
- Recalled memory is context only; the prompt explicitly requires re-measuring a new object rather than reusing old fit dimensions.

Configuration:

```text
VERTEX_MEMORY_BANK_ID=<memory-bank-id>
MEMORY_ENABLED=true
```

## One-time provisioning

Added:

```text
scripts/provision-agent-context.py
```

Run intentionally once with an identity that can create Agent Platform resources:

```bash
python scripts/provision-agent-context.py \
  --project YOUR_PROJECT_ID \
  --location asia-south1
```

The script creates a Sessions backing Runtime and a standalone Memory Bank and prints the environment variables to use in Cloud Run.
