# Release Notes — IYAL.ai Lite v0.11.1

## UI correction release

This release makes the laptop-height improvement visually substantial while preserving the v0.11 two-column width split and v3 artifact behavior.

### Changes
- Removed the entire Conversation panel heading block: **YOUR CONVERSATION / Let’s find your fit. / Ask · upload · refine**.
- Reduced the global Iyal.ai brand/header bar from 54 px class height to a compact 42 px baseline, with a smaller logo and tighter typography.
- Reduced the top context strip from 82 px to 70 px, and to 54 px after the first submitted turn.
- Reclaimed additional vertical space by tightening the composer while keeping the input permanently visible.
- Conversation and Solution Workspace column widths are unchanged (`1.58fr / .92fr`).
- Conversation and Solution Workspace remain independently scrollable.
- Inline generated image rendering is unchanged.
- Inline 3D viewer rendering is unchanged.
- `core.js` and `stl-viewer.js` are unchanged, retaining the v3 artifact-loading fix.

### Scope
Frontend layout only. No backend agent, measurement, CAD, preview, session, or artifact API behavior was changed.
