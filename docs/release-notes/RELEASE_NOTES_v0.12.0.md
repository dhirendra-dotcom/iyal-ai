# Release Notes — IYAL.ai Lite v0.12.0

## Purpose

Keep the Solution Workspace cumulative so evidence does not disappear as the agent advances through later tool stages.

## Change

- `showRecommendation()` no longer clears `market`, `measurements`, `design`, or `preview`.
- Grounded market-search citations shown under **Search sources** therefore remain visible after `present_adaptation_options` completes.
- Previously rendered workspace content stays in place until that specific section is intentionally updated by a new result.

## Retained

- Conversation and Solution Workspace layout from v0.11.1.
- Existing panel widths and independent scrolling.
- Always-visible chat composer.
- Inline generated image and inline 3D viewer.
- Existing artifact URL/loading safety implementation (`core.js` and `stl-viewer.js` unchanged).
- Backend market-search and grounding workflow unchanged.

## Naming

The release/build name is **v0.12.0**. `inline-chat` is not included in the current version name or package name.
