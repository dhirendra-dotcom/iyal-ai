Iyal.ai
Personal Adaptation Intelligence for everyday objects and environments
Iyal.ai helps people explore practical adaptations when standard products do not fit their everyday needs. It combines conversational reasoning, live market research, guided measurement, constrained 3D design, generated previews, and optional human support in one workflow.
> **Design assistance only.** Iyal.ai is not a medical device and does not provide diagnosis, treatment, therapy, prognosis, or medical advice. Generated designs and previews require physical fit and manufacturing checks before real-world use.
Problem
Many everyday products are designed for an average user. When grip, reach, visibility, stability, or environmental fit differs from that assumption, people often have to choose between an off-the-shelf product that may not fit and a fully custom solution that is difficult to create.
Iyal.ai closes that gap by first checking whether a simpler or existing solution already works, then moving to personalized adaptation only when needed.
What Iyal.ai does
Iyal.ai can:
understand an everyday task, object, environment, and desired outcome through conversation;
perform live Google Search-grounded market research before recommending purchasable adaptations;
show grounded market findings and source links directly in the conversation;
compare simple alternatives such as technique changes, existing products, object modification, or custom design;
guide the user through only the measurements required for the selected adaptation;
measure supported object dimensions from calibrated images or accept explicit manual measurements;
validate supported CAD parameters against deterministic engineering constraints;
generate a 3D-printable STL for the supported custom grip-sleeve family;
generate an illustrative usage preview;
assess whether an optional human fit review would be useful;
optionally use managed Sessions and Memory Bank for durable, non-sensitive adaptation preferences.
User journey
```text
Describe the everyday challenge
        ↓
Understand need, object and desired outcome
        ↓
Check simple/no-purchase alternatives
        ↓
Live market research when a purchasable option is relevant
        ↓
Choose an adaptation strategy
        ↓
Collect only the measurements needed
        ↓
Validate engineering constraints
        ↓
Generate custom 3D design when supported
        ↓
Show STL + illustrative usage preview
        ↓
Optional product-support / fit review
```
The Conversation pane carries the user interaction, grounded market research, generated images, and inline 3D viewer. The Solution Workspace provides compact progress and solution status as the workflow advances.
Current capabilities
Market research and adaptation reasoning
The agent can reason about low-risk everyday object and environment adaptations such as grip support, edge protection, visual cues, impact protection, reach/access aids, path clearance, and other practical adjustments. Any recommendation that involves buying a product is preceded by a live Google Search-grounded market check.
Custom 3D design
Current CAD generation is intentionally constrained to `GRIP_SLEEVE_V1`, a reusable grip-sleeve family for elongated handheld objects.
Supported examples include:
spoon;
fork;
pen;
toothbrush;
paint brush;
suitable small hand tools.
The supported design family can vary outer width/depth, adapter length, interface dimensions, angle, profile, texture, and palm flare within deterministic engineering limits.
Environment adaptations
Iyal.ai can recommend or visualize reversible, low-risk changes such as path clearance, visual cues, and impact protection. It does not generate structural, electrical, load-bearing, fall-protection, or medical-device designs.
Key features
Google Search-grounded market research — current market findings with grounding links.
Conversational decision flow — custom CAD is one option, not the default.
Guided measurement — calibrated image measurement plus explicit manual measurement fallback.
Engineering validation — deterministic checks before CAD generation.
3D-printable output — OpenSCAD-based STL generation for the supported grip-sleeve family.
Inline 3D viewer — generated STL remains inside the conversation experience.
Generated usage preview — illustrative visualization of the proposed adaptation.
Structured observability — model/tool timing and error events suitable for Cloud Run logs.
Optional managed context — Vertex AI Sessions and Memory Bank can be enabled without moving execution away from Cloud Run.
Optional human support flow — fit-review recommendation based on evidence and unresolved uncertainty.
Architecture
```text
Browser UI
   │
   ▼
Cloud Run
FastAPI + Google ADK root agent
   │
   ├── Gemini 3.8 Flash
   │     ├── conversational reasoning
   │     ├── tool selection
   │     └── Google Search grounding
   │
   ├── Measurement pipeline
   │     ├── calibrated image measurement
   │     └── manual measurement fallback
   │
   ├── Engineering validation
   │
   ├── OpenSCAD CAD generation
   │     └── STL artifact
   │
   ├── Gemini image generation
   │     └── illustrative usage preview
   │
   ├── Google Cloud Storage
   │     └── generated artifacts
   │
   └── Optional Agent Platform context services
         ├── managed Sessions
         └── Memory Bank
```
Cloud Run is the application execution runtime. Agent Platform resources, when configured, are used only for managed session and memory services.
Technology stack
Layer	Technology
Frontend	HTML, CSS, JavaScript
Backend	Python 3.12, FastAPI
Agent framework	Google ADK
Primary model	Gemini 3.8 Flash
Market research	Google Search grounding
Image/vision	Gemini + OpenCV
CAD	OpenSCAD
3D processing	Trimesh
Artifact storage	Google Cloud Storage
Runtime	Google Cloud Run
Optional context	Vertex AI / Agent Platform Sessions and Memory Bank
Repository structure
```text
.
├── backend/
│   ├── app/                 # FastAPI, ADK agent, tools and workflow logic
│   ├── cad/                 # OpenSCAD design source
│   ├── tests/               # Backend tests
│   └── requirements.txt
├── frontend-lite/           # Browser UI, inline viewer and frontend tests
├── scripts/                 # Local run, deployment, packaging and provisioning
├── docs/                    # Supporting design/implementation documentation
├── Dockerfile               # Cloud Run container
├── VERSION.txt
└── README.md
```
Prerequisites
For local development:
Python 3.12 recommended;
OpenSCAD available on `PATH`;
a Google Cloud project with Vertex AI / Gemini access;
a Google Cloud Storage bucket for generated artifacts;
Application Default Credentials or equivalent Google Cloud authentication.
The container image installs OpenSCAD automatically.
Configuration
Create `backend/.env` with the required environment values. At minimum:
```text
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=global
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GCS_BUCKET=your-artifact-bucket
OPENSCAD_BINARY=openscad
```
Optional managed session/memory configuration:
```text
AGENT_PLATFORM_LOCATION=asia-south1
VERTEX_SESSION_RUNTIME_ID=...
VERTEX_MEMORY_BANK_ID=...
MEMORY_ENABLED=true
```
Without managed Agent Platform resources, the application can use a configured database session service or fall back to in-memory sessions.
Run locally
Install dependencies:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```
Run:
```bash
./scripts/run-lite.sh
```
Windows PowerShell:
```powershell
.\scripts\run-lite.ps1
```
Open:
```text
http://127.0.0.1:8000/app/
```
Deploy to Cloud Run
Example:
```bash
export REGION=asia-south1

./scripts/deploy-lite.sh \
  /path/to/iyal-v0.13.0 \
  YOUR_ARTIFACT_BUCKET \
  YOUR_RUNTIME_SERVICE_ACCOUNT
```
If managed Sessions or Memory Bank are required, provision the backing context resources once per environment and provide their IDs as environment variables.
Demo walkthrough
A representative end-to-end scenario is an everyday utensil grip:
The user explains that a spoon is difficult to hold securely.
Iyal.ai identifies the functional goal and performs live market research for existing adaptations.
Grounded market findings and source links appear in the conversation.
If a personalized solution is preferred, Iyal.ai requests only the required handle measurements.
Measurements are registered from calibrated capture and/or explicit user values.
The proposed grip sleeve is checked against engineering constraints.
OpenSCAD generates the STL.
The STL appears in the inline 3D viewer.
An illustrative usage preview is generated.
Iyal.ai can recommend an optional product-support review when fit uncertainty remains.
The same custom CAD family can be applied to other suitable elongated handheld objects such as forks, pens, toothbrushes, paint brushes, and small hand tools.
Safety and design boundaries
Iyal.ai intentionally separates design assistance from clinical or safety-critical decision-making.
It does not diagnose or infer a medical condition.
It does not provide treatment, therapy, prognosis, or medical advice.
It does not fabricate measurements from an image without physical scale.
Generated previews are illustrative and do not prove fit or effectiveness.
A CAD design passing software checks is not equivalent to a physically validated product.
Structural, electrical, load-bearing, fall-protection, and medical-device designs are outside the supported scope.
Real-world fit must be checked after manufacturing before use.
Current limitations
Custom CAD is currently limited to the `GRIP_SLEEVE_V1` family.
Arbitrary free-form CAD generation is not supported.
Articulated parts, embedded electronics, active stabilization, and load-bearing structures are outside the current design capability.
Market availability, price, delivery, and final product fit must be verified with the cited seller/source.
Generated usage images are concept previews, not evidence of physical performance.
Mobile UI is responsive but the current primary layout is optimized for the desktop/tablet demo experience.
Testing
Frontend tests:
```bash
node --test \
  frontend-lite/tests/core.test.mjs \
  frontend-lite/tests/stl-viewer.test.mjs
```
Backend tests:
```bash
PYTHONPATH=backend pytest -q backend/tests
```
See `BUILD_VERIFICATION.md` for the verification summary associated with the release.
Release
Current release: v0.13.0
See `RELEASE_NOTES_v0.13.0.md` for release-specific implementation changes.