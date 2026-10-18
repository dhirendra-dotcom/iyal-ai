# Release Notes - IYAL.ai Lite v0.13.3

## Purpose

Make the three demo scenarios reliable and easier to follow: understand the need before searching, measure in seconds instead of minutes, and end every custom design with Gemini's fit-risk rating and a clear next step.

Deployed to Cloud Run service `iyalaiv3` (latest revision `iyalaiv3-00012-gcf`; the version label change below ships with the next deploy).

## Measured before/after (live logs)

| | Before | After |
|---|---|---|
| Measuring a spoon from an A4 photo | 125 s (one unbounded Gemini call) | 5.0 s |
| First reply to an open request ("Can you help me?") | searched straight away | asks one context question, 5.1 s |
| Main-agent stall before retry | 40 s | 25 s |

## Scenario 1: understand first, then research

- **Context question enforced.** On the first message, `search_existing_products` returns `context_question_first` instead of searching, and tells Gemini what to ask: which spoon (soup or dessert), whether it twists more when lifting liquids, whether fingers close fully. Skipped only with `skip_context_question=true` (explicit product request, or context already given). User messages are counted by a new `before_agent_callback` (`app/turns.py`).
- **Plain language** in market research; no clinical terms.
- **One source link per site.** Grounding links are redirects titled with the domain, so duplicates from one site are dropped and the next site is shown.
- **Search sources** are collapsed with a count.
- **Side panel**
  - Progress steps only move as far as the work done (no jump to "Next step").
  - Plain risk label ("Low-risk everyday adaptation · Check physical fit before use").
  - "Options considered" list with Gemini's pick tagged Recommended.
  - "With Gemini" open by default, with a label per capability used.
  - "Comparing your options" placeholder between the research and the recommendation.
  - "What's next" card with a **Design a custom grip →** button (also shown under Iyal's reply in the chat). It fills in the Scenario 2 prompt; nothing is sent until Send.

## Scenario 2: personal design from real measurements

- **Fast handle detection** (`app/domain/segmentation.py`): Gemini gets a 1,536 px copy of the photo (OpenCV keeps full resolution), low thinking, outline capped at 24 points, 30 s per attempt with one retry, and the previous Interactions call as a fallback.
- **Plausibility check**: a photo reading outside 4-40 mm width, 20-300 mm length, or a width not smaller than the length is rejected (`rejected_readings`) and never saved; Iyal asks for a ruler value.
- **Measurement plan**: common method names (`calibrated_photo`, `photo`, `ruler`, `manual`) are accepted; rejections list the allowed methods (one live turn had looped 8 times).
- **No photo, no measurement**: calling the measurement tool without an uploaded photo returns `photo_required` instead of an error.
- **Approximate values**: `register_manual_measurement(approximate=true)` when the user says "about", "maybe", "not sure".
- **Side panel**
  - "Measuring from your photo" progress card.
  - "Your measurements" with value, source and "A4 detected 0.96" (the score rates the A4 sheet detection, not the reading), rejected readings crossed out, and Gemini's detected box drawn on the photo.
  - "Current design · version N": design checks passed, shape and size, the measurements it was fitted to, preview thumbnail, View 3D, Download STL.
  - The card that changes scrolls into view and is briefly highlighted (not on phones or with reduced motion).
- **Chat**: the duplicate "measurement plan is ready" message is removed; Gemini describes the plan exactly as the panel shows it.

## Scenario 3: Gemini's fit-risk rating and professional review

- **`assess_support_need(fit_risk_rating, gemini_concerns)`**: Gemini rates GREEN, AMBER or RED from the whole conversation and gives up to 4 plain-language concerns. Observed evidence can only raise the rating (for example two approximate values raise GREEN to AMBER), noted as "Raised from GREEN to AMBER by the observed evidence".
- **RED is the final step of a custom design**: the design is kept, but `offer_product_support` returns a required professional fit-review visit (in person first) with booking dates. A request that is RED before any design still gets no design and no booking.
- **Fit review card** in the side panel: one line for GREEN with strong evidence; for AMBER or RED, "Why Gemini recommends a review" with Gemini's concerns and the failed evidence checks.
- **After booking**: a confirmation card in the chat (date, time, type, booking ID, what to bring), a "Your fit-review visit" card in the side panel, and the outcome question moved into that card as "After you've tried it".
- **Gemini knows about the booking**: confirmed visits are added to the next message as application context.

## Reliability and observability

- Main-agent stall retry after 25 s instead of 40 s (`AGENT_MODEL_FIRST_CHUNK_TIMEOUT_SECONDS`).
- If the connection drops after the turn has completed, the browser keeps the turn instead of showing "network error".
- Tool rejections log `error_detail`; fit ratings log `fit_risk_rating`, `gemini_rating` and `concern_count`.

## Other

- Landing page and app hero images crossfade every 5 s (static with reduced motion), with a per-image crop.
- Older release notes moved to `docs/release-notes/`.
- `backend/.env.example` added; `LOCAL_DEPLOYMENT.md` describes the local run and the demo scenarios.

## New optional settings

```text
SEGMENTATION_MAX_IMAGE_PX=1536            Gemini localization copy (OpenCV keeps full size)
SEGMENTATION_ATTEMPT_TIMEOUT_SECONDS=30
SEGMENTATION_MAX_ATTEMPTS=2
AGENT_MODEL_FIRST_CHUNK_TIMEOUT_SECONDS=25 (was 40)
```

## Known issues

- `tests/test_custom_design_preference.py::...[professional_help-False-RED]` fails. It predates this release: it expects `market_check_skipped` for the `professional_help` path.
- Bookings are kept in memory per instance and are lost on restart.
- The detection box on the photo assumes the browser and OpenCV agree on photo orientation; not yet checked on rotated phone photos.
- Vertex latency varies; one turn in testing waited 94 s for a stalled model call before recovering.
