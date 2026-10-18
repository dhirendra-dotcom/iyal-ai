# IYAL.ai v0.11.0 — Viewport UI Enhancement

This release is intentionally presentation-focused. It keeps the v0.10.0 single-agent/backend behavior and the inline-chat-v3 artifact path, while giving the conversation substantially more usable vertical space.

## Layout changes

- Conversation / Solution Workspace width split is unchanged.
- Both panels remain fixed to the viewport and independently scrollable.
- Top context area reduced from 104 px to 82 px at normal desktop height.
- After the first submitted user turn, the top context compacts to 64 px.
- On shorter laptop viewports (<=760 px high), the context area uses 68 px and compacts to 56 px after conversation starts.
- Brand/header height and application shell gaps are slightly reduced.
- Conversation heading, message padding and activity rail are tightened.
- Composer textarea reduced to 46 px (43 px on short screens), buttons to 30 px minimum height, and lower padding/gaps reduced.
- The composer remains outside the message scroll rail, so it stays visible at all times.

## Preserved behavior

- Inline 3D viewer retained.
- Inline generated image retained.
- `frontend-lite/core.js` unchanged.
- `frontend-lite/stl-viewer.js` unchanged.
- Existing artifact-loading URL validation, same-origin rules, timeout/retry behavior and v3 safety path retained.
