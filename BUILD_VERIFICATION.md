# Build Verification — IYAL.ai Lite v0.13.0

## Scope

This release changes only the live market-research contract/rendering plus release markers and related tests/docs.

## Verified

- UI build marker is `v0.13.0`.
- `search_existing_products` returns grounded conversational `market_text` plus grounding `sources`; the live path no longer calls JSON extraction/product normalization.
- Grounding source extraction still deduplicates source URLs.
- Market research renders in the Conversation pane with **Search sources** links below it.
- Solution Workspace renders only compact market-research status (`In progress`, `Completed`, or failure), not product cards.
- Agent instruction explicitly avoids repeating the full already-displayed market-research response.
- `core.js` is byte-identical to v0.12.0.
- `stl-viewer.js` is byte-identical to v0.12.0.
- JavaScript syntax check passed.
- Python compile check passed for modified backend/tool/prompt/fixture files.
- Frontend core/STL test suite: **10/10 passed**.
- Targeted backend release/static tests: **9/9 passed**.
- A local dependency-stubbed contract check confirmed `market_text` + deduplicated grounding sources and absence of product/summary JSON fields.

## Environment note

The full backend pytest suite could not be collected in this build container because the Google GenAI/ADK SDK packages are not installed in the container environment. The failure occurred during test import/collection, before application tests ran; targeted tests that do not require those external SDK imports passed as above.

## Artifact safety

The v3 artifact URL/STL loading implementation was not changed in this release. SHA-256 values match v0.12.0:

- `frontend-lite/core.js`: `463f3a7829b627535765d3f78ae38e523a24a464765c4077760157a1b05c35e8`
- `frontend-lite/stl-viewer.js`: `edbc02682a9f3c40426a3a534039c630cd0f185e67808f579afe1e1bf94a6007`
