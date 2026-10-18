"""Gemini model wrapper that retries a stalled request before any output is produced.

Observed on the Vertex AI ``global`` endpoint: most agent model calls return a first
chunk within ~2-16 s, but some sit silently for 60-220 s before the first chunk. A
request that has produced no output can be abandoned and resent safely: nothing has
been streamed to the user and no tool has run.

Rules:
- Only the time to the FIRST response is bounded. Once output starts, the stream is
  never interrupted.
- The final attempt has no first-chunk limit, so a turn never fails where it would
  previously have succeeded; it only gets a chance to finish sooner.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from google.adk.models import Gemini

from app.config import settings
from app.logging_config import get_logger, log_event

logger = get_logger("arthistics.model")


async def retry_before_first_chunk(
    start: Callable[[], AsyncIterator[Any]],
    *,
    first_chunk_timeout_seconds: float,
    max_attempts: int,
    label: str = "agent_model",
) -> AsyncIterator[Any]:
    attempts = max(1, int(max_attempts))
    for attempt in range(1, attempts + 1):
        stream = start()
        iterator = stream.__aiter__()
        last_attempt = attempt >= attempts
        started = time.perf_counter()
        try:
            if last_attempt or first_chunk_timeout_seconds <= 0:
                first = await iterator.__anext__()
            else:
                first = await asyncio.wait_for(iterator.__anext__(), timeout=first_chunk_timeout_seconds)
        except StopAsyncIteration:
            return
        except asyncio.TimeoutError:
            log_event(
                logger, logging.WARNING, "Model produced no output in time; retrying",
                event_type="model_first_chunk_timeout", status="retrying", operation=label,
                attempt=attempt, duration_ms=round((time.perf_counter() - started) * 1000),
            )
            aclose = getattr(stream, "aclose", None)
            if aclose is not None:
                try:
                    await aclose()
                except Exception:  # noqa: BLE001 - cleanup must not mask the retry
                    pass
            await asyncio.sleep(0.5)
            continue

        if attempt > 1:
            log_event(
                logger, logging.INFO, "Model retry produced output",
                event_type="model_retry_recovered", status="success", operation=label,
                attempt=attempt, duration_ms=round((time.perf_counter() - started) * 1000),
            )
        yield first
        async for item in iterator:
            yield item
        return


class ResilientGemini(Gemini):
    """ADK Gemini model with a bounded wait for the first streamed response."""

    async def generate_content_async(self, llm_request, stream: bool = False):  # type: ignore[override]
        parent = super().generate_content_async
        async for response in retry_before_first_chunk(
            lambda: parent(llm_request, stream=stream),
            first_chunk_timeout_seconds=settings.agent_model_first_chunk_timeout_seconds,
            max_attempts=settings.agent_model_max_attempts,
        ):
            yield response
