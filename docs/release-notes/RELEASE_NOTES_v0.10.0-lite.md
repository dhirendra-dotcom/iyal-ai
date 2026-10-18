# Iyal.ai v0.10.0 Lite — focused routing and latency release

v0.10.0 simplifies the single-agent runtime without introducing sub-agents.

## Changes

- Removed `search_design_knowledge` from the application/runtime and removed the Discovery Engine dependency.
- Removed the unused `research_adaptation_options` wrapper and its obsolete tests/UI event mapping.
- Reduced the root system instruction from ~28 KB to ~6 KB. Workflow prerequisites are enforced in Python tools instead of repeated prompt rules.
- Removed ADK `BuiltInPlanner` from the root agent. Root/model calls use a fixed LOW thinking configuration without exposing thoughts.
- Reduced root response budget to 2048 tokens; grounded market-search budget to 1536 tokens.
- `present_adaptation_options` now deterministically requires `search_existing_products` for strategies that normally involve a purchasable product/accessory or precede custom fabrication. Pure no-purchase changes remain exempt.
- Fixed model timing instrumentation for progressive SSE: logs distinguish `model_request_start`, `model_first_chunk`, and the final `model_request_complete` (`partial=False`) instead of logging every streaming chunk as complete.
- Memory Bank background writes now log `memory_write_accepted` rather than implying the memory has already been materialized.
- `scripts/test-memory-bank.py` now supports `--list-only` and retrieves memories using the exact `{user_id, app_name}` scope after a blocking smoke-test write.
- `deploy-lite.sh` no longer carries Agent Search or root-planner settings. It validates Memory Bank configuration before deployment.

## No reprovisioning required

Existing `VERTEX_SESSION_RUNTIME_ID` and `VERTEX_MEMORY_BANK_ID` values remain valid. Do not rerun `provision-agent-context.py` for an existing environment.

## Expected market flow

```text
User asks for a purchasable adaptation
        -> search_existing_products (Google Search grounding)
        -> present_adaptation_options
        -> visible grounded product choices
```

Pure no-purchase changes such as path clearance may proceed without market search.

## Memory verification

To write and immediately retrieve a harmless test fact:

```bash
python scripts/test-memory-bank.py \
  --project PROJECT_ID \
  --location LOCATION \
  --memory-bank-id MEMORY_BANK_ID \
  --user-id USER_ID
```

To inspect an existing scope without writing:

```bash
python scripts/test-memory-bank.py \
  --project PROJECT_ID \
  --location LOCATION \
  --memory-bank-id MEMORY_BANK_ID \
  --user-id USER_ID \
  --list-only
```
