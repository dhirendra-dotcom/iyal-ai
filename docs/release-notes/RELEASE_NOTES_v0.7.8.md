# Arthistics v0.7.8 — market-aware parallel research

v0.7.8 keeps **v0.7.3 as the application base** (Next.js frontend + FastAPI backend) and selectively ports the strongest v0.7.7 product-intelligence and runtime changes. The experimental `frontend-lite` is intentionally not included.

## What changed

- Added current-market product checks before custom fabrication with `search_existing_products` (Gemini + Google Search grounding).
- Added `buy_existing`, `change_technique`, and `modify_object` as first-class adaptation strategies.
- Added explicit custom-design preference handling: market search can be skipped when the user clearly requests custom design, without bypassing fit/risk/validation gates.
- Added `research_adaptation_options`, which runs independent market research and design-knowledge retrieval concurrently with `asyncio.gather` and preserves partial results.
- Added async/non-blocking execution for calibrated measurement and preview generation so blocking work does not freeze the event loop/SSE heartbeats.
- Added contextual usage-video gating instead of requiring video for every personalized recommendation.
- Added deterministic GREEN / AMBER / RED recommendation risk context and risk-based professional-support behavior.
- Restored the outcome-feedback backend endpoint from the later implementation.
- Added market-check UI to the existing Next.js conversation and Live Solution workspace.
- Hardened the Next.js SSE parser for split UTF-8 / CRLF network chunks and oversized frames.
- Preserved the v0.7.3 production dependency policy requested for deployment:
  - `google-cloud-discoveryengine` is unpinned.
  - `opencv-contrib-python-headless>=4.10.0,<6.0.0`.

## Parallelism model

This remains a **single ADK agent**. Parallelism is used only for independent work:

```text
Arthistics Agent
      |
      +-- market/product search ---------+
      |                                  |
      +-- design knowledge retrieval ----+--> combined research result
```

Dependent engineering steps remain sequential (measurement -> DesignSpec -> validation -> CAD).

## Frontend decision

v0.7.8 retains the v0.7.3 Next.js/TypeScript frontend. It does **not** adopt the v0.7.7 native `frontend-lite` implementation.

## Verification

- Python source compile check: PASS.
- Pure backend tests run in this environment: **8 passed** (`product_search`, `design_rules`, `outcomes`).
- TypeScript parse check on modified files: no syntax/type-structure errors were surfaced; only expected unresolved module imports occurred because `node_modules` is not bundled in the release workspace.
- Full backend integration tests require the configured Google ADK / Google GenAI environment and should be run after installing `backend/requirements.txt`.
- Full Next.js verification should run `npm install` followed by `npm run build` in the deployment environment.
