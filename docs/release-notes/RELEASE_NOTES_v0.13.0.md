# Release Notes — IYAL.ai Lite v0.13.0

## Purpose

Make live market research conversational and remove the fragile dependency on parsing Gemini's Google Search-grounded answer into custom product JSON.

## Market research flow

- `search_existing_products` now returns the grounded model answer as `market_text`.
- Google Search grounding links continue to come from `candidate.grounding_metadata.grounding_chunks` and are returned separately as `sources`.
- No application-defined JSON schema, JSON extraction, product normalization, or unparseable-response retry is required by the live market-search path.
- If the grounded response is empty or the API call fails, the tool returns a genuine market-search failure rather than a JSON parse failure.

## UI behavior

- Full market research appears in the **Conversation** pane.
- Grounded **Search sources** links appear directly below the market-research response.
- The **Solution Workspace** no longer renders market product cards. It shows a compact market-research status only:
  - In progress
  - Completed (+ grounded source count)
  - Could not complete
- The agent prompt instructs the main agent not to repeat the full market-research result after the tool output has already been displayed.

## Retained

- Current viewport layout and panel widths.
- Independent Conversation / Solution Workspace scrolling.
- Always-visible composer.
- Inline generated preview image.
- Inline 3D viewer.
- Existing artifact URL and STL loading safety implementation.
- Market-search prerequisite guards for purchasable adaptation paths.

## Naming

The release/build name is **v0.13.0**. `inline-chat` is not included in the release or package name.
