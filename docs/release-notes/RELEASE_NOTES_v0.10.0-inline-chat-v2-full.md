# IYAL.ai Lite v0.10.0 — Inline Chat v2 Full Source

This package is based on IYAL.ai Lite v0.10.0 (not v0.10.1).

## UI change
- Generated 3D STL design is rendered in the conversation stream.
- Generated illustrative preview image is rendered in the conversation stream.
- Generated 3D/preview artifacts are no longer duplicated in the right-side Solution Workspace.
- "Refine this design" is shown below the inline 3D design.
- UI deployment marker: `v0.10.0-inline-chat-v2`.

## Dependency baseline
Pinned to the versions confirmed in the current local and Cloud Run environments:
- `google-adk[db,gcp]==2.11.0`
- `google-genai==2.28.0`
- `google-cloud-aiplatform==1.165.1`
- `google-cloud-agentplatform==2.5.0`
- `httpx==0.28.1`
- `tenacity==9.1.4`

Other application dependencies retain the v0.10.0 compatible ranges.

## Scope
No intentional backend behavior, prompt, tool, CAD, Session Service, or Memory Bank logic changes were made for the inline-chat feature.
