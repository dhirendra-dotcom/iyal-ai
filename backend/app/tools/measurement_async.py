"""Async ADK adapter for calibrated measurement with event-loop-owned state."""

from __future__ import annotations

import asyncio
import time

from google.adk.tools import ToolContext

from app.tools.measurement import _apply_capture_measurement, _compute_capture_measurement


async def measure_object_from_capture(
    image_uri: str,
    object_name: str,
    target_region: str,
    dimensions: list[str],
    reference_type: str,
    tool_context: ToolContext,
) -> dict:
    """Measure dimensions from a calibrated photo without blocking other tools.

    Use an A4 top photo for width and length; request a manual measurement for
    thickness/depth. Explicit user measurements take precedence over photos.
    """
    started = time.perf_counter()
    # The worker receives only immutable inputs/a private dimension list, never
    # ToolContext. All session reads and writes happen after awaiting the work.
    result = await asyncio.to_thread(
        _compute_capture_measurement,
        image_uri,
        object_name,
        target_region,
        list(dimensions),
        reference_type,
    )
    return _apply_capture_measurement(
        result, image_uri, target_region, tool_context, started, preserve_manual=True
    )
