# Release Notes - IYAL.ai Lite v0.13.1

## Purpose

Serve the Iyal landing page from the same Cloud Run service and hand visitors into the live conversation.

## Changes

- New `site/` folder with the landing page, served at `/`. The hero image is now a 140 KB WebP instead of a 2.2 MB PNG.
- "Talk to Iyal" opens `/app/`. The starter form's "Continue with Iyal" button opens `/app/#starter=<text>`.
- The chat (`frontend-lite`) reads the starter from the URL fragment, prefills the composer, and clears the fragment. Nothing is sent until the person presses Send.
- `core.js` gains one pure helper, `starterFromHash`. The artifact URL and STL loading code is unchanged, and `stl-viewer.js` is byte-identical to v0.13.0.
- The FAQ copy no longer says the page is disconnected from the live application.

## Fixes

- The legacy `/analyze` and `/refine` endpoints passed arguments to `chat()` in the wrong positions and returned a 500 error. They now forward the request correctly.
- `.webp` files were served as `application/octet-stream` on `python:3.12-slim`. They are now served as `image/webp`.

## Retained

All v0.13.0 behaviour: conversational grounded market research, a status-only market card in the Solution Workspace, layout, inline preview and 3D viewer, and the market-search guards.