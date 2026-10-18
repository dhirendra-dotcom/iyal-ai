# Release Notes — IYAL.ai Lite v0.11.0

## Goal

Increase usable conversation height on typical laptop screens without changing the established two-panel width ratio or breaking inline artifacts.

## UI changes

- Reduced vertical footprint of the brand/header and intro strip.
- Added an active-conversation compact state after the first submitted message.
- Increased effective chat-history height by tightening the conversation header, activity row and internal spacing.
- Slightly reduced composer height while keeping the text field, photo, image/video, voice, Stop and Send controls visible.
- Preserved fixed viewport shell and independent Conversation / Solution Workspace scrolling.
- Kept the existing desktop column widths unchanged.

## Artifact behavior

- Inline STL/3D viewer retained.
- Inline generated preview image retained.
- v3 artifact-loading fix retained. `core.js` and `stl-viewer.js` are unchanged from the previous UI-enhanced build.

## Backend

No agent/tool workflow change. Backend release/version strings are bumped to 0.11.0 for package consistency.
