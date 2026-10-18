# Iyal.ai v0.7.9 Lite

## Scope

Minimal product-branding release based on v0.7.8 Lite. No architecture, API, deployment-resource, tool-flow, measurement, CAD, search, or model behavior changes were introduced beyond the product-facing name update.

## Changes

- Updated Lite UI branding from Arthistics to **Iyal.ai**.
- Updated browser title, header/logo letter, disclaimer, and footer/version.
- Updated agent-facing product self-reference in the system instruction so responses identify the product as **Iyal.ai**.
- Updated product-support booking email wording to **Iyal.ai**.
- Updated other user-visible backend messages, calibration-marker text, stream titles, and API display title so the old brand does not surface during the demo.
- Updated release/package references to `iyal-v0.7.9-lite.zip`.
- Included the latest complete `prepare-lite.sh` and `deploy-lite.sh` deployment scripts from the prior v0.7.8 Lite deployment cleanup.

## Intentionally unchanged

To keep this release low-risk and minimal, internal technical identifiers remain unchanged, including existing logger namespaces, environment-variable names, Cloud Run service defaults, GCS configuration, ADK/internal symbols, and other runtime identifiers.

## Baseline

All v0.7.8 Lite capabilities are retained, including the lightweight browser UI, microphone/audio recording with transcription into the editable composer, FastAPI backend, streaming, measurement/CAD flow, support booking, and Cloud Run deployment structure.
