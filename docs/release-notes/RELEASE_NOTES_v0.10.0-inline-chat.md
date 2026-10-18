# Iyal.ai v0.10.0 — Inline design artifacts demo patch

This patch is based on Iyal.ai Lite v0.10.0 and changes the presentation layer only.

## Changes
- Generated STL designs now render as an interactive 3D viewer directly inside the conversation.
- Generated illustrative preview images now render directly inside the conversation.
- The right-side Solution Workspace remains available and continues to mirror the latest design and preview.
- Inline design cards show available profile/texture/dimension metadata.
- Added a `Refine this design` action that pre-fills the demo refinement prompt.
- Existing backend APIs, SSE event names, model/tool orchestration, sessions, memory, measurement, CAD, and artifact storage are unchanged.

## Verification
- Existing frontend Node tests: 10/10 passed.
- `frontend-lite/app.js`: JavaScript syntax check passed.
- Python compile check passed for backend application and local UI fixture.
- Shell syntax checks passed for deployment/package/run scripts.
- Static contract checks confirmed inline design, inline preview, refinement action, and retained workspace rendering.
