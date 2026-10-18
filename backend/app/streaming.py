from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from urllib.parse import quote

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.genai import types

from app.services import runtime
from app.logging_config import get_logger, log_event

logger = get_logger("arthistics.streaming")

DisconnectChecker = Callable[[], Awaitable[bool]]


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump(mode="json", exclude_none=True))
    return str(value)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(_json_safe(data), ensure_ascii=False)}\n\n"


def sse_heartbeat() -> str:
    """SSE comment used only to keep intermediaries from treating the stream as idle."""
    return ": heartbeat\n\n"


def artifact_content_path(
    *, session_id: str, user_id: str, key: str, version: int
) -> str:
    return (
        f"/api/sessions/{quote(session_id, safe='')}/artifacts/content"
        f"?user_id={quote(user_id, safe='')}"
        f"&key={quote(key, safe='')}"
        f"&version={version}"
    )


async def stream_agent_run(
    *,
    user_id: str,
    session_id: str,
    message: types.Content,
    heartbeat_seconds: float = 10.0,
    is_disconnected: DisconnectChecker | None = None,
) -> AsyncIterator[str]:
    runner = runtime.require_runner()
    run_config = RunConfig(streaming_mode=StreamingMode.SSE)

    started = time.perf_counter()
    pending_next: asyncio.Task[Any] | None = None
    disconnected_logged = False
    first_output_logged = False

    def record_first_output(kind: str) -> None:
        nonlocal first_output_logged
        if first_output_logged:
            return
        first_output_logged = True
        log_event(
            logger, logging.INFO, "First visible agent output",
            event_type="agent_first_output", session_id=session_id,
            duration_ms=round((time.perf_counter() - started) * 1000),
            status="success", output_kind=kind,
        )

    async def client_is_disconnected() -> bool:
        if is_disconnected is None:
            return False
        try:
            return bool(await is_disconnected())
        except Exception:
            # Disconnect checks are observability aids and must never break the stream.
            return False

    try:
        log_event(
            logger, logging.INFO, "Agent stream connected",
            event_type="stream_connected", session_id=session_id, status="connected",
            heartbeat_seconds=heartbeat_seconds,
        )
        # Emit bytes immediately so the browser/proxy knows the SSE response is live.
        yield sse(
            "connected",
            {"session_id": session_id, "heartbeat_seconds": heartbeat_seconds},
        )

        log_event(
            logger, logging.INFO, "Agent run started",
            event_type="agent_run_start", session_id=session_id, status="started"
        )
        yield sse("run_started", {"session_id": session_id})

        events = runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=message,
            run_config=run_config,
        )
        event_iterator = events.__aiter__()
        pending_next = asyncio.create_task(event_iterator.__anext__())

        while True:
            done, _ = await asyncio.wait(
                {pending_next},
                timeout=max(0.05, heartbeat_seconds),
                return_when=asyncio.FIRST_COMPLETED,
            )

            if not done:
                if await client_is_disconnected():
                    disconnected_logged = True
                    elapsed_ms = round((time.perf_counter() - started) * 1000)
                    log_event(
                        logger, logging.WARNING, "Client disconnected from agent stream",
                        event_type="client_disconnected", session_id=session_id,
                        duration_ms=elapsed_ms, status="cancelled", reason="client_disconnected",
                    )
                    log_event(
                        logger, logging.WARNING, "Agent run cancelled after client disconnect",
                        event_type="agent_run_cancelled", session_id=session_id,
                        duration_ms=elapsed_ms, status="cancelled", reason="client_disconnected",
                    )
                    pending_next.cancel()
                    break

                # This comment is intentionally invisible to the application UI. It simply
                # ensures there are response-body bytes while Gemini/tools are busy.
                yield sse_heartbeat()
                continue

            try:
                event = pending_next.result()
            except StopAsyncIteration:
                pending_next = None
                break

            # Progressive function-call argument chunks can appear as partial
            # events. We only map complete function calls to UI events.
            if not event.partial:
                for call in event.get_function_calls() or []:
                    name = call.name
                    args = _json_safe(call.args or {})
                    if name == "report_progress":
                        record_first_output("progress")
                        yield sse(
                            "progress",
                            {
                                "stage": args.get("stage", "progress"),
                                "title": args.get("title", "Iyal.ai update"),
                                "lines": args.get("lines", []),
                            },
                        )
                    elif name in {"present_measurement_plan", "register_usage_video", "measure_object_from_capture", "register_manual_measurement", "present_adaptation_options", "search_existing_products", "validate_design", "generate_3d_design", "generate_usage_preview", "generate_environment_preview", "assess_support_need", "offer_product_support"}:
                        record_first_output("tool")
                        yield sse(
                            "tool_start",
                            {
                                "tool": name,
                                "args": args if name == "validate_design" else {},
                            },
                        )

                for response in event.get_function_responses() or []:
                    name = response.name
                    payload = _json_safe(response.response or {})
                    if name in {"present_measurement_plan", "register_usage_video", "measure_object_from_capture", "register_manual_measurement", "present_adaptation_options", "search_existing_products", "validate_design", "generate_3d_design", "generate_usage_preview", "generate_environment_preview", "assess_support_need", "offer_product_support"}:
                        yield sse(
                            "tool_complete",
                            {
                                "tool": name,
                                "response": payload,
                            },
                        )

                    if name == "generate_3d_design" and payload.get("status") == "success":
                        key = payload["artifact_key"]
                        artifact_version = int(payload["artifact_version"])
                        yield sse(
                            "design_ready",
                            {
                                "design_version": payload.get("design_version"),
                                "artifact_key": key,
                                "artifact_version": artifact_version,
                                "stl_path": artifact_content_path(
                                    session_id=session_id,
                                    user_id=user_id,
                                    key=key,
                                    version=artifact_version,
                                ),
                                "design": payload.get("design", {}),
                                "mesh": payload.get("mesh", {}),
                            },
                        )

                    if name == "generate_usage_preview" and payload.get("status") == "success":
                        key = payload["artifact_key"]
                        artifact_version = int(payload["artifact_version"])
                        yield sse(
                            "preview_ready",
                            {
                                "artifact_key": key,
                                "artifact_version": artifact_version,
                                "image_path": artifact_content_path(
                                    session_id=session_id,
                                    user_id=user_id,
                                    key=key,
                                    version=artifact_version,
                                ),
                                "label": payload.get("label", "Illustrative in-use preview"),
                                "disclaimer": payload.get(
                                    "disclaimer",
                                    "Concept visualization only; final fit must be checked before use.",
                                ),
                            },
                        )

                    if name == "generate_environment_preview" and payload.get("status") == "success":
                        key = payload["artifact_key"]
                        artifact_version = int(payload["artifact_version"])
                        yield sse(
                            "environment_preview_ready",
                            {
                                "artifact_key": key,
                                "artifact_version": artifact_version,
                                "image_path": artifact_content_path(
                                    session_id=session_id,
                                    user_id=user_id,
                                    key=key,
                                    version=artifact_version,
                                ),
                                "label": payload.get("label", "Illustrative environment preview"),
                                "disclaimer": payload.get(
                                    "disclaimer",
                                    "Concept visualization only; confirm physical changes before implementation.",
                                ),
                            },
                        )

            if event.partial and event.content and event.content.parts:
                text = "".join(
                    part.text or ""
                    for part in event.content.parts
                    if not getattr(part, "thought", False)
                )
                if text:
                    record_first_output("text")
                    yield sse("assistant_delta", {"text": text})

            if event.is_final_response() and event.content and event.content.parts:
                final_text = "".join(
                    part.text or ""
                    for part in event.content.parts
                    if not getattr(part, "thought", False)
                ).strip()
                if final_text:
                    record_first_output("text")
                    yield sse("final", {"text": final_text})

            pending_next = asyncio.create_task(event_iterator.__anext__())

        if disconnected_logged:
            return

        duration_ms = round((time.perf_counter() - started) * 1000)
        log_event(
            logger, logging.INFO, "Agent run completed",
            event_type="agent_run_complete", session_id=session_id,
            duration_ms=duration_ms, status="success"
        )
        yield sse("run_complete", {"session_id": session_id})
    except asyncio.CancelledError:
        duration_ms = round((time.perf_counter() - started) * 1000)
        log_event(
            logger, logging.WARNING, "Agent stream task was cancelled",
            event_type="agent_run_cancelled", session_id=session_id,
            duration_ms=duration_ms, status="cancelled",
            reason="stream_task_cancelled",
        )
        raise
    except Exception as exc:
        duration_ms = round((time.perf_counter() - started) * 1000)
        log_event(
            logger, logging.ERROR, "Agent run failed",
            event_type="agent_run_error", session_id=session_id,
            duration_ms=duration_ms, status="error", error_type=type(exc).__name__
        )
        yield sse("error", {"message": str(exc)})
    finally:
        if pending_next is not None and not pending_next.done():
            pending_next.cancel()
            try:
                await pending_next
            except (asyncio.CancelledError, StopAsyncIteration):
                pass
