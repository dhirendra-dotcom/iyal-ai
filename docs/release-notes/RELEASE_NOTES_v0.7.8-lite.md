# Arthistics v0.7.8 Lite

This release makes the native Lite edition easier to run and deploy while retaining the v0.7.8 backend behavior.

## Deployment cleanup

- Added a root `Dockerfile` that packages FastAPI + `frontend-lite` into one Cloud Run service.
- Added root `.dockerignore` and `.gcloudignore` so Cloud Run source deployments do not send local environments, caches, tests, secrets, generated outputs, or archives.
- Strengthened root `.gitignore` for `.venv`, `__pycache__`, `.pytest_cache`, `.env`, generated outputs, logs, and build artifacts.
- Added `scripts/prepare-lite.sh` for GCS download/unzip.
- Added `scripts/deploy-lite.sh` for one-command Cloud Run source deployment using the default Cloud Build identity.
- Added `scripts/package-lite.sh` for clean future source ZIPs.
- Removed local `.venv`, cache, local `.env`, and generated demo artifacts from the release.
- Optimized the UI hero asset from a multi-megabyte PNG to a ~100 KB WebP asset.

## Voice input

- Added a clearly visible **Record voice** control.
- Recording status is shown while microphone permission, recording, and transcription are in progress.
- Browser recording selects a supported WebM/MP4/OGG audio format.
- Audio is sent to the existing `/transcribe` endpoint, transcribed with the configured Gemini transcription model, and inserted into the editable composer.
- The transcript is never auto-sent; the user can edit it before pressing Send.

## Lite/runtime integration

- Ported the optional static UI mount into the v0.7.8 backend so `/app/` is served by the same Cloud Run service as the APIs.
- Kept the v0.7.8 dependency policy:
  - `google-cloud-discoveryengine` unpinned.
  - `opencv-contrib-python-headless>=4.10.0,<6.0.0`.
- Preserved SSE heartbeat behavior and the v0.7.8 market/research, measurement, preview, support, and outcome flows.

## Small correctness fixes

- Outcome feedback now requires a real positive design version rather than treating `null` as a completed design.
- Capability attribution no longer treats an empty tool response as successful generation.

## Verification performed

- Python source compilation: PASS.
- Browser JavaScript syntax checks: PASS.
- Frontend native unit tests: 10 passed.
- Backend dependency-light tests (`static_ui`, `product_search`, `support_and_logging`): 8 passed.
- Shell script syntax checks: PASS.
- Full backend integration tests still require the Google ADK / Google GenAI dependencies and configured cloud environment.
