# Arthistics Hackathon Implementation Plan

**Plan version:** 1.4  
**Application release:** v0.7.3  
**Status:** Active living plan

---

## 1. Product Goal

Arthistics helps a person adapt everyday objects and low-risk environments around their abilities and real usage.

Core idea:

```text
Person + Ability + Task + Object/Environment + Context
                         ↓
                 Arthistics reasoning
                         ↓
         Best practical adaptation strategy
                         ↓
 Workaround / environment change / custom design / professional help
```

The product is not limited to creating a 3D object. A good result may be a simpler workaround, furniture/layout change, edge protection, visual cue, impact padding, standard adaptation, custom CAD, or a professional handoff.

### Prototype principles

- Conversation first, not form first.
- Usage video is mandatory for every first personalized solution.
- No diagnosis from media.
- No exact physical measurements guessed from an ordinary photo/video.
- Measure only what the chosen solution actually needs.
- Prefer the easiest reliable capture/measurement method for the user.
- Use one ADK agent as the design-intelligence orchestrator.
- Keep deterministic engineering actions in tools/services.
- Generate custom CAD only when custom geometry is actually useful.
- Keep safety-critical/high-risk changes outside automatic prototype scope.

---

## 2. Current User Journey

```text
1. User describes the difficulty by typing or voice dictation
                     ↓
2. Mic path when used:
      record → stop → Gemini transcription
      → editable text in composer → user presses Send
                     ↓
3. User shares object/environment image(s)
                     ↓
4. Arthistics requests a short usage video (mandatory)
                     ↓
5. Gemini observes functional interaction only
                     ↓
6. Agent compares practical adaptation strategies
                     ↓
7. If physical fit is required:
      determine minimum dimensions required
      create MeasurementPlan
                     ↓
8. Collect each dimension using easiest reliable method
                     ↓
9. Retrieve relevant design knowledge from Agent Search
                     ↓
10. Propose numeric DesignSpec when custom CAD is appropriate
                     ↓
11. Deterministic validation/retry loop
                     ↓
12. Generate STL with OpenSCAD when required
                     ↓
13. Show recommendation + 3D/environment visualization
                     ↓
14. Only after the completed recommendation/result:
      show Schedule a visit
                     ↓
15. User may choose date/time and book
```

---

## 3. Conversation + Live Solution Workspace

The UX is conversation-first, but the desktop experience is no longer a single long chat column.

```text
┌──────────────────────────────┬─────────────────────────────┐
│ CONVERSATION                 │ LIVE SOLUTION              │
│                              │                             │
│ user messages                │ current inputs             │
│ agent questions              │ current status             │
│ progress                     │ recommendation             │
│ photo/video attachments      │ measurements               │
│                              │ 3D/result preview          │
│ [ + ] [ 🎤 ] [ text ] Send   │                             │
└──────────────────────────────┴─────────────────────────────┘
```

### Conversation panel

- natural chat instead of a form
- image/video attachments
- mandatory usage-video request when missing
- voice dictation via the mic button
- progress cards with user-facing conclusions, not hidden chain-of-thought
- final recommendation text
- **Schedule a visit only after the final recommendation/result**

### Live solution panel

Keep the evolving result visible while the user continues talking:

- most recent reference image/usage video
- current workflow status
- best-match adaptation recommendation
- alternative strategies
- MeasurementPlan when relevant
- 3D design readiness
- illustrative object/environment result

Internal taxonomy names such as `edge_protection` remain internal. The UI displays user-facing labels such as **Edge protection**.

### Mobile

Conversation remains first. The solution workspace follows below rather than forcing a desktop split-screen layout onto a narrow display.

### Assistant text rendering

Do not show raw escaped markdown such as `\###`, `\*`, `\**`, or `&#x20;`. Render headings, bullets, emphasis, code labels and separators as UI.

### Persistent disclaimer

Display at the top of the UI:

> **Design assistance only.** Arthistics does not provide medical advice, diagnosis, or treatment. For health concerns, consult a qualified healthcare professional.

---

## 4. Primary Architecture

```text
Next.js conversational frontend
          │
          ├── mic recording → /transcribe → Gemini → editable composer text
          │
          └── submitted text / image / video
                         ↓
FastAPI backend
          │
          ▼
Google ADK — Arthistics Agent
          │
          ├── report_progress()
          ├── register_usage_video()
          ├── present_adaptation_options()
          ├── present_measurement_plan()
          ├── measure_object_from_capture()
          ├── register_manual_measurement()
          ├── search_design_knowledge() [DEFERRED / not active in v0.10.0]
          ├── validate_design()
          ├── generate_3d_design()
          ├── generate_usage_preview()
          ├── generate_environment_preview()
          └── offer_product_support()
```

Supporting services:

```text
Gemini 3.8 Flash     → multimodal understanding / design reasoning
Gemini transcription → separate mic dictation service
Gemini Interactions  → target-region segmentation helper
OpenCV               → deterministic physical calibration/measurement
Agent Search         → managed design knowledge retrieval
Python               → validation and business rules
OpenSCAD             → parametric 3D geometry
GCS                  → private media/STL/preview artifacts
Nano Banana 2.1      → illustrative visual previews
Cloud Run            → frontend/backend deployment
Cloud Logging        → structured runtime debugging
```

---

## 5. Streaming Transport Reliability

The chat endpoint is a long-lived SSE stream. A multimodal turn can be silent for a while while Gemini is reading a video, analyzing an image, or waiting on a tool. That silence must not be interpreted by the Next.js proxy as an abandoned response body.

Current flow:

```text
Browser
   ↓
Next.js backend proxy
   ↓
FastAPI /chat (SSE)
   ↓
ADK → Gemini / tools
```

The v0.7.3 transport contract is:

```text
/chat opens
   ↓
connected event immediately
   ↓
run_started
   ↓
model/tool may be busy
   ↓
: heartbeat        every ~10 seconds while silent
   ↓
normal progress/tool/text events
   ↓
run_complete
```

The heartbeat is an SSE comment, so it keeps HTTP response-body traffic flowing without appearing as a user-visible message. `SSE_HEARTBEAT_SECONDS` is configurable and defaults to 10 seconds.

Structured logging distinguishes:

- `stream_connected`
- `client_disconnected`
- `agent_run_cancelled`
- `agent_run_error`
- `agent_run_complete`

If a specific deployment still terminates the proxied SSE stream despite heartbeats, the fallback architecture is to route only `/chat` directly from the browser to FastAPI while leaving ordinary upload/REST endpoints behind the Next.js proxy.

---

## 6. Why One Agent for v0.x

The ADK agent is responsible for one coherent job: **Design Intelligence**.

It understands, classifies, retrieves relevant knowledge, chooses a practical adaptation strategy, proposes a design when needed, and revises a proposal when validation fails.

It does not personally perform:

- pixel-to-mm conversion
- deterministic constraints
- CAD geometry generation
- artifact storage
- email delivery
- booking-slot management

Those are tools/services.

A second Engineering Design Agent should only be introduced later if dynamic CAD composition becomes complex enough to justify a separate planning responsibility.

---

## 7. Mandatory Usage Video

A short usage video is mandatory for **every** first personalized solution.

Why:

```text
Photo / geometry
→ what the object/space looks like

Video
→ how the person actually interacts with it
```

Allowed observations include:

- slipping
- rotation
- repeated re-gripping
- instability
- hesitation
- reach compensation
- collision with an edge
- obstruction along a walking path
- visible difficulty accessing a control

Not allowed:

- diagnosing a disease
- confirming a condition from appearance
- recommending medication/treatment/therapy

`validate_design()` and environment/adaptation tools enforce the video gate rather than relying only on prompting.

---

## 8. Measurement Strategy — v0.6 Decision

### Previous approach

The earlier design asked Gemini to decide how many photos were required and attempted to obtain width/depth/length from multiple calibrated views.

That created an important UX problem: some theoretically useful views are physically awkward for users, for example trying to balance a spoon on its narrow side.

### New principle

> **Determine the minimum physical facts required, then obtain each with the easiest reliable method.**

```text
Selected adaptation
       ↓
What physical dimensions are actually required?
       ↓
MeasurementPlan
       ↓
For each dimension choose:
   ├── calibrated_top_photo
   ├── manual_measurement
   ├── trusted_known_dimension
   └── assisted_capture
       ↓
ObjectGeometry + provenance
```

### Example — spoon grip sleeve

Fit-critical facts:

- handle/interface width
- handle/interface depth/thickness
- usable handle length

Recommended acquisition:

```text
One natural A4 top photo
→ interface width
→ usable length
→ visible outline/taper

Simple ruler/caliper entry
→ interface thickness/depth
```

No extra photo should be requested merely because computer vision could theoretically derive another dimension.

### MeasurementPlan schema concept

```json
{
  "object_name": "spoon",
  "target_region": "handle",
  "adaptation_family": "grip_sleeve",
  "measurements": [
    {
      "dimension": "interface_width_mm",
      "required": true,
      "preferred_method": "calibrated_top_photo"
    },
    {
      "dimension": "available_length_mm",
      "required": true,
      "preferred_method": "calibrated_top_photo"
    },
    {
      "dimension": "interface_depth_mm",
      "required": true,
      "preferred_method": "manual_measurement",
      "fallback_method": "assisted_capture"
    }
  ]
}
```

### Measurement provenance

Every value keeps its origin:

```json
{
  "measurements": {
    "interface_width_mm": {
      "value_mm": 7.3,
      "source": "calibrated_photo",
      "confidence": 0.91,
      "image_uri": "gs://..."
    },
    "interface_depth_mm": {
      "value_mm": 1.8,
      "source": "user_measurement",
      "confidence": null
    }
  },
  "measurement_source": "mixed"
}
```

Allowed source summaries for physical design validation:

- `calibrated_capture`
- `user_provided`
- `mixed`

No `prototype_fallback` or guessed physical-fit source is allowed.

---

## 9. Calibrated Photo Measurement

### Default reference

Use ordinary A4 paper when practical:

```text
210 mm × 297 mm
```

User guidance:

- place the target naturally/flat on the A4 sheet
- keep all four A4 corners visible
- photograph approximately from above
- keep the target fully visible
- avoid hands covering the target
- avoid blur, glare, and deep shadows

A printed ArUco marker remains an optional advanced/fallback calibration reference.

### Responsibility split

```text
Gemini
→ Which physical target pixels/contour matter?

OpenCV
→ Where is the known reference?
→ What is the perspective transform?
→ What do the calibrated pixels represent in mm?
```

Gemini must not directly estimate physical millimetres from visual appearance.

---

## 10. Gemini Target Segmentation — v0.6 Fix

`backend/app/domain/segmentation.py` now follows the current Gemini image-understanding pattern using the **Interactions API**:

```text
client.interactions.create()
```

The helper is deliberately stateless and sets:

```text
store = false
```

It returns structured image-space data:

```json
{
  "label": "spoon handle",
  "box_2d": [320, 220, 620, 790],
  "mask": [[20, 80], [950, 70], [970, 850], [30, 900]],
  "fully_visible": true,
  "capture_quality": "good",
  "issues": []
}
```

Coordinates are normalized and are passed to OpenCV for physical calibration.

### Important v0.6 correction

Remove the previous direct segmentation configuration based on:

```text
Models.generate_content()
Automatic Function Calling settings
ThinkingConfig settings
```

Those settings were causing runtime warnings/errors and are unnecessary for this one-shot segmentation helper.

The main conversational agent continues to run through ADK.

---

## 11. Environment Adaptation

Arthistics should support problems involving rooms, walls, furniture, controls, and other everyday environments without assuming that the solution is a custom printed object.

Example user problem:

> “I frequently hit this wall/furniture corner while moving through the room.”

Arthistics can compare:

```text
edge_protection
path_clearance
furniture_repositioning
visual_cue
impact_padding
reach_access
custom_environment_fixture
standard_adaptation
custom_cad
professional_help
```

### Decision flow

```text
Understand room/environment + mandatory usage video
                    ↓
Identify the functional problem
                    ↓
Compare practical strategies
                    ↓
Does selected solution require physical geometry?
          ┌─────────┴─────────┐
          │                   │
         NO                  YES
          │                   │
Recommendation /          MeasurementPlan
visual preview                 ↓
                         custom fixture/CAD
```

Do **not** measure an entire room unless the selected solution needs those dimensions.

### Environment safety boundary

Low-risk prototype suggestions may include:

- edge guards
- bumpers/padding
- non-structural furniture repositioning
- path-clearance suggestions
- visual contrast/cues
- simple non-load-bearing fixtures

Escalate rather than autonomously design:

- structural modifications
- electrical work
- stairs/railings
- fall protection
- load-bearing safety equipment
- major construction
- other changes where failure could cause serious harm

---

## 12. Design Knowledge / Agent Search

Arthistics uses a custom ADK function tool rather than depending on a built-in search tool:

```python
search_design_knowledge(
    query,
    adaptation_family,
    problem_types,
    knowledge_types,
)
```

Reasoning split:

```text
Gemini
→ writes semantic query
→ selects values from controlled taxonomy

Python
→ validates taxonomy values
→ constructs metadata filter
→ calls Agent Search
```

Recommended filter dimensions:

- adaptation family
- knowledge type
- review status
- optionally object family/evidence level

Detailed user problem terms belong primarily in the semantic query so a strict metadata filter does not hide general safety/manufacturing guidance.

### Controlled taxonomy

Runtime taxonomy remains the allow-list for values such as:

- adaptation families
- problem types
- knowledge types
- design features
- review status/evidence level

Environment-related values are included in v0.6.

---

## 13. Design Proposal and Validation Loop

When custom CAD is selected:

```text
Retrieved knowledge + measured object geometry + user preference
                         ↓
                 Gemini DesignSpec
                         ↓
                 validate_design()
                    │           │
                  invalid      valid
                    │           │
                    ▼           ▼
          structured violation  OpenSCAD
                    │
                    └── Gemini revises
```

Python should return violations rather than silently changing Gemini's proposal.

The same authoritative constraint JSON is:

```text
indexed/retrievable for Gemini reasoning
             +
read directly by deterministic Python validation
```

This avoids prompt/validator drift.

---

## 14. CAD Strategy

Current supported manufacturing family:

```text
GRIP_SLEEVE_V1
```

Longer-term CAD should use reusable primitives instead of one template per object:

```text
create_sleeve()
create_slot()
add_ribs()
add_flare()
create_clamp()
add_extension()
```

Concept:

```text
Gemini = design planner
CAD primitives = controlled geometry vocabulary
Python/OpenSCAD/CadQuery = deterministic geometry builder
STL = finished prototype
```

This is controlled generative design, not arbitrary LLM-authored CAD code.

---

## 15. Illustrative Preview

After a successful 3D design, Arthistics may generate an illustrative image of a generic person using the adapted object.

For an environment recommendation, it may generate an illustrative redesigned-room preview.

These must always be labeled clearly as concept visualizations, not evidence of:

- exact fit
- safety
- medical benefit
- clinical effectiveness
- manufacturing quality

Default image model configuration:

```dotenv
GEMINI_IMAGE_MODEL=gemini-nano-banana-2.1
```

---

## 16. Product-Support Scheduling

Product support is a **closing action**, not part of the design reasoning flow.

Correct sequencing:

```text
analysis
→ adaptation comparison
→ recommendation
→ measurement/design if required
→ 3D/environment visualization if applicable
→ final solution summary
→ Schedule a visit
```

Even if the ADK tool call is emitted before the final streamed text, the frontend buffers the support offer and does not render it until the final recommendation event has been displayed.

Offer:

> Would you like help finalizing this solution?

A trained product-support professional can review practical fit/setup and final details before ordering or implementation. The service is explicitly **not a medical consultation**.

### UI flow

```text
[ Schedule a visit ]
        ↓
select date
        ↓
select time
        ↓
select review type
  • In-person
  • Video review
        ↓
enter email
        ↓
[ Confirm visit & email details ]
```

### Backend

```text
GET  /api/sessions/{session_id}/support/slots
POST /api/sessions/{session_id}/support/book
```

Hackathon implementation uses in-memory availability with replaceable SMTP email confirmation.

Future production integration can connect the same interface to a real workforce/calendar scheduling system.

### Confirmation behavior

- Booking reserves the slot first.
- If SMTP is configured and succeeds: `email_status=sent`.
- If SMTP is not configured: `email_status=simulated` and the UI states this honestly.
- If SMTP is configured but fails: the booking remains reserved, `email_status=failed`, and the UI displays the booking ID instead of falsely claiming delivery.

---

## 17. Voice Dictation — Audio to Editable Text

The mic is **dictation**, not an automatic audio-message send action.

```text
🎤 Mic
   ↓
record speech
   ↓
Stop
   ↓
separate Gemini transcription request
   ↓
transcript appears in composer
   ↓
user reviews / edits
   ↓
Send
   ↓
normal ADK text turn
```

### Responsibility split

```text
Browser MediaRecorder
    = capture speech

POST /api/sessions/{session_id}/transcribe
    = separate input-service request

Gemini
    = speech → text

Composer
    = user review/edit control

Arthistics ADK agent
    = receives only what user finally submits
```

The transcription call is intentionally outside the ADK agent loop because the user has not submitted the message yet.

Default configuration:

```dotenv
GEMINI_TRANSCRIPTION_MODEL=gemini-3.8-flash
MAX_TRANSCRIPTION_MB=10
```

Short recordings use inline audio data. The frontend never auto-sends the returned transcript. Browser microphone access normally requires HTTPS or localhost and explicit user permission.

---

## 18. Logging and Observability

### Goal

A single user turn must be traceable across:

```text
request
→ ADK run
→ model call
→ tool call
→ segmentation
→ OpenCV measurement
→ Agent Search
→ validation
→ CAD
→ artifact creation
→ response
```

### ADK callbacks

Use the official model/tool lifecycle hooks:

```text
before_model_callback
after_model_callback
on_model_error_callback
before_tool_callback
after_tool_callback
on_tool_error_callback
```

Callbacks observe timing/status and do not replace normal results.

### Structured fields

At minimum:

```text
timestamp
severity
session_id
turn_id / invocation_id
event_type
tool_name / operation
duration_ms
status
error_type
```

Do not routinely log raw user prompts, images, audio/video contents, or secret credentials.

### Local vs Cloud Run

```text
Local development
→ human-readable console format

Cloud Run
→ one JSON object per log line
→ Cloud Logging parses fields into jsonPayload
```

Configuration:

```dotenv
ARTHISTICS_LOG_LEVEL=INFO
ARTHISTICS_LOG_FORMAT=auto
```

Example Cloud Logging queries:

```text
jsonPayload.session_id="ses_..."
jsonPayload.event_type="tool_error"
jsonPayload.tool_name="measure_object_from_capture"
severity>=ERROR
```

---

## 19. Storage and Session State

### Artifacts

Private GCS remains the artifact store for:

- object/environment photos
- usage videos
- audio messages
- generated STL
- illustrative previews

Session state stores lightweight references and structured design/measurement state rather than binary payloads.

### Cloud Run local disk

OpenSCAD can use an OS temporary directory during CAD generation:

```text
Windows local → %TEMP%/arthistics
Cloud Run     → /tmp/arthistics
```

Generated STL is uploaded to GCS and temporary local files are disposable.

### Production note

The prototype may use in-memory ADK session/scheduling stores for a single-instance hackathon demo. Multi-instance production requires persistent shared session and booking stores.

---

## 20. Medical / Scope Guardrails

Arthistics is an everyday adaptation/design assistant, not a healthcare provider.

It must not provide:

- medical diagnosis
- disease confirmation from media
- medication advice
- treatment advice
- therapy prescriptions
- prognosis
- unrelated general-purpose answers outside product/environment adaptation scope

If a user mentions a medical condition, it may be treated only as user-supplied context for the functional design problem.

The agent should redirect medical questions to a qualified healthcare professional and continue only with the supported object/environment adaptation aspect when appropriate.

---

## 21. Cloud Run Deployment

Two independent services:

```text
arthistics-frontend
arthistics-backend
```

Backend container includes:

- Python runtime
- FastAPI/Uvicorn
- OpenCV headless contrib package
- OpenSCAD
- Google ADK / Google Gen AI SDK

Frontend container includes:

- Next.js standalone runtime

Recommended hackathon deployment settings:

- backend memory approximately 2 GiB
- backend timeout longer than default for model/CAD operations
- one backend instance if using in-memory sessions
- dedicated runtime service account
- GCS + Vertex/Gemini + Agent Search permissions as needed

Future improvement: use signed URLs so large video uploads go browser → GCS directly instead of being proxied through Cloud Run.

---

## 22. Runtime Configuration

Key environment variables:

```dotenv
GOOGLE_CLOUD_PROJECT=
GOOGLE_CLOUD_LOCATION=global
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GCS_BUCKET=

GEMINI_MODEL=gemini-3.8-flash
GEMINI_SEGMENTATION_MODEL=gemini-3.8-flash
GEMINI_TRANSCRIPTION_MODEL=gemini-3.8-flash
MAX_TRANSCRIPTION_MB=10
GEMINI_IMAGE_MODEL=gemini-nano-banana-2.1
# BuiltInPlanner removed in v0.10.0; no GEMINI_THINKING_LEVEL runtime setting

OPENSCAD_BINARY=openscad

AGENT_SEARCH_LOCATION=global
AGENT_SEARCH_DATA_STORE_ID=
AGENT_SEARCH_TOP_K=8

A4_SHORT_SIDE_MM=210
A4_LONG_SIDE_MM=297

ARTHISTICS_LOG_LEVEL=INFO
ARTHISTICS_LOG_FORMAT=auto
SSE_HEARTBEAT_SECONDS=10

SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_USE_TLS=true
SUPPORT_EMAIL_FROM=
```

---

## 23. v0.7.3 Verification Plan

Deterministic tests should cover:

- numeric design validation
- invalid wall/profile/source rejection
- ArUco reference measurement
- missing-marker recapture
- A4 detection
- A4 calibrated target measurement
- missing-A4 recapture
- product-support booking reservation
- SMTP-simulated booking path
- SMTP-failure preservation of booking
- invalid email rejection
- structured JSON log fields
- mic record → Gemini transcript → editable composer flow
- transcript must not auto-send to ADK
- support CTA must not render before final recommendation
- desktop conversation + live-solution workspace rendering
- assistant escaped-markdown rendering cleanup

Additional release checks:

- Python compile check
- TypeScript/TSX parse check
- prohibited terminology scan
- removal of caches/build residue from archive
- live Gemini segmentation must be tested in the target Google project
- live Nano Banana image generation must be tested in the target Google project
- production Next.js build should be run where npm package installation is available

---

## 24. Known Prototype Limits

- Physical measurement accuracy still needs calibration against real photographs and caliper/ruler ground truth.
- A4 calibrated measurement assumes the measured visible dimension is approximately on the reference plane.
- Gemini segmentation quality depends on image clarity and target visibility.
- Manual measurement remains appropriate when it is easier/more reliable than computer vision.
- Environment redesign recommendations are low-risk concept guidance, not architectural/structural engineering.
- Support booking availability is in memory in the hackathon implementation.
- SMTP is optional; a real production scheduling/email provider is not yet required for the demo.
- Media uploads are still proxied by the web/backend path; large-video direct-to-GCS signed upload is a later improvement.

---

## 25. Roadmap After v0.7

### Near-term

- real-world measurement accuracy benchmark
- better guided capture visualization/examples
- persistent ADK sessions for multi-instance Cloud Run
- direct signed-GCS media upload
- real calendar/workforce scheduling integration
- richer Agent Search corpus/evidence metadata

### Later

- more reusable CAD adaptation families
- component-based CAD composition (`sleeve + ribs + flare - slot`, etc.)
- depth/AR capture for larger/complex environments
- multi-view geometry when truly necessary
- reusable Ability Profile / Digital Ability Twin
- optional Engineering Design Agent once CAD composition complexity justifies it

---

## 26. Version History

### Plan v1.4 / App v0.7.3

- added immediate SSE `connected` event for `/chat`
- added invisible heartbeat comment frames during long silent ADK/Gemini/tool processing
- added configurable `SSE_HEARTBEAT_SECONDS` (default 10 seconds)
- added explicit client-disconnect vs task-cancellation logging
- strengthened SSE cache/proxy headers with `no-cache, no-transform` and `X-Accel-Buffering: no`
- kept text + image + video as one logical user turn; upload behavior is unchanged

### Plan v1.3 / App v0.7.1

- removed the large conversational-design intro/hero block from the main workspace
- removed the TEXT / IMAGE / VIDEO / VOICE / 3D capability legend from the main workspace
- the page now moves directly from the compact header/disclaimer into the working conversation + solution workspace
- no agent, measurement, transcription, booking, or recommendation behavior changed in this patch

### Plan v1.2 / App v0.7.0

- buffered product-support offer so **Schedule a visit** renders only after the final recommendation/result
- removed product support from user-visible reasoning/progress stages
- added desktop conversation + persistent live-solution workspace
- added cleaner rendering for assistant headings/bullets/emphasis instead of raw escaped markup
- changed microphone behavior to voice dictation: record → Gemini transcription → editable composer text → user Send
- added separate session-scoped `/transcribe` API outside the ADK agent loop
- retained the v0.6 measurement redesign, environment adaptations, segmentation fix and structured observability

### Plan v1.1 / App v0.6.0

- replaced fixed photo/view measurement with dimension-first hybrid MeasurementPlan
- removed awkward capture as the default approach for thickness/depth
- added measurement provenance and mixed-source geometry
- moved segmentation helper to Gemini Interactions API
- added ADK callback-based structured observability and Cloud Run JSON logs
- added microphone recording to the conversation composer
- added product-support booking UI/API + optional email delivery
- expanded recommendation reasoning to low-risk environment adaptations
- added optional environment visualization
- retained mandatory usage-video gate and medical/out-of-scope guardrails

### Plan v1.0 / App v0.5.0

- mandatory video for first personalized design
- in-use visual preview after 3D model
- medical disclaimer and strict scope guardrails
- product-support handoff prompt

### Earlier versions

- conversation-first UX
- A4/OpenCV calibrated measurement
- Gemini target-region segmentation
- Agent Search custom function tool design
- numeric DesignSpec validation/retry loop
- reusable CAD-family/primitives direction

---

## 27. Current Demo Story

A concise demonstration should show:

```text
1. User explains an everyday difficulty by text or mic dictation
2. Shares image/environment photo
3. Shares mandatory usage video
4. Arthistics observes the functional difficulty
5. Compares practical adaptation options
6. Requests only the minimum fit measurements when needed
7. Retrieves grounded design knowledge
8. Validates the recommendation/design
9. Shows generated 3D model when appropriate
10. Shows illustrative use/environment preview
11. After the solution is shown, offers optional trained product-support booking
```

The intended message is:

> Arthistics does not merely generate a shape. It understands how a person interacts with an everyday object or environment, identifies a practical adaptation strategy, measures only what is necessary, and carries the selected solution through to a reviewable result.
