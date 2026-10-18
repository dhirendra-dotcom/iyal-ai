# Iyal.ai v0.8.0 Lite

## Scope

Behavior release focused on market-search reliability, visible recommendation rationale, operational observability, and evidence-aware post-design fit-review support. The single FastAPI + `frontend-lite` Cloud Run shape is unchanged.

## Fixed

- Fixed a market-search runtime defect: `product_search.py` called `_grounding_sources(...)` but the helper was missing.
- Added robust Google Search grounding-source extraction across SDK object/dict shapes.
- Added one controlled retry when the grounded model response cannot be parsed as the required JSON object.
- Market-search results now expose `search_performed`, `source_count`, `product_count`, `attempt_count`, and `failure_reason` rather than silently returning an apparently successful result.
- Added a deterministic pre-CAD market gate: non-explicit custom CAD cannot be selected/validated until market research has completed or failed explicitly.

## Recommendation visibility

- `present_adaptation_options` now accepts concise `design_features` (`feature`, `value`, `reason`) for the solution panel.
- The browser UI renders those feature-level reasons under **Why this adaptation?**.
- This exposes decision rationale without exposing private model chain-of-thought.

## Design-check wording

- `validate_design` now returns `check_status="passed"`, `physical_fit_verified=false`, and the user-facing status **Design checks passed. Physical fit remains unverified.**
- The system prompt explicitly prohibits describing a generated prototype itself as "validated".

## Observability

Structured ADK tool-completion logs now add safe metadata such as:

- market-search performed/source/product counts and failure reason;
- measurement quality/source/dimensions/fit readiness;
- selected strategy/risk/market-check state/design-feature count;
- design-check result/version/measurement source;
- CAD version/artifact key and preview status;
- fit-evidence quality/completeness/confidence and support priority.

Raw customer media/content is not added to these logs.

## Fit-confidence and professional support

- Added `assess_support_need`, run after the custom design and usage-preview attempt.
- The assessment uses observed data rather than invented "accuracy": required-data completeness, calibrated measurement confidence, calibrated image quality, measurement provenance, missing/estimated inputs, risk level and physical-fit status.
- Gemini uses that structured assessment to choose `optional`, `recommended`, or `strongly_recommended` review strength.
- `offer_product_support` now accepts that recommendation level and reason, enforces the AMBER minimum, and keeps RED outside generic product-support booking.
- A completed GREEN custom prototype may therefore still receive an optional or stronger fit-review CTA when appropriate.
- The UI opens the fit-review CTA automatically after the design/preview flow and shows the evidence-quality band.

## Tool cleanup

- Commented the unused/unregistered legacy `measure_calibrated_image` tool out of the active tool surface.
- Kept lower-level ArUco/calibration measurement code because it remains useful for tests and fallback research.

## Deferred

The following previously identified items are intentionally deferred to the next release:

- flexible thickness acquisition / alternative thickness capture;
- deeper numeric design-parameter provenance;
- broader post-design flow restructuring beyond the support insertion/order implemented here.
