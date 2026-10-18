from __future__ import annotations

import itertools
import logging
import threading
import time
from typing import Any

from app.logging_config import get_logger, log_event


logger = get_logger("arthistics.adk")
_timing_lock = threading.Lock()
_model_seq = itertools.count(1)
_model_active: dict[str, int] = {}
_model_starts: dict[int, float] = {}
_model_first_chunk_seen: set[int] = set()
_tool_starts: dict[tuple[str, str], float] = {}


def _context_ids(context: Any) -> tuple[str | None, str | None]:
    """Read stable ADK identifiers without depending on one context implementation."""
    session_id = getattr(context, "session_id", None)
    if not session_id:
        session = getattr(context, "session", None)
        if session is not None:
            session_id = getattr(session, "id", None)
    if not session_id:
        invocation_context = getattr(context, "invocation_context", None)
        session = getattr(invocation_context, "session", None) if invocation_context else None
        if session is not None:
            session_id = getattr(session, "id", None)

    invocation_id = getattr(context, "invocation_id", None)
    turn_id = str(invocation_id) if invocation_id else None
    return str(session_id) if session_id else None, turn_id


def _key(turn_id: str | None, name: str) -> tuple[str, str]:
    return (turn_id or "unknown", name)


def _tool_result_metadata(name: str, response: Any) -> dict[str, Any]:
    """Return safe, compact diagnostics without logging user content or raw media."""
    if not isinstance(response, dict):
        return {}
    metadata: dict[str, Any] = {}

    if name == "search_existing_products":
        metadata.update(
            search_performed=response.get("search_performed"),
            source_count=response.get("source_count", len(response.get("sources") or [])),
            market_text_length=len(str(response.get("market_text") or "")),
            failure_reason=response.get("failure_reason"),
            error_code=response.get("error_code"),
            search_query_count=response.get("search_query_count"),
            attempt_count=response.get("attempt_count"),
            search_duration_ms=response.get("search_duration_ms"),
            cache_hit=bool(response.get("cache_hit")),
            reused=bool(response.get("reused")),
        )
    elif name in {"measure_object_from_capture", "register_manual_measurement"}:
        geometry = response.get("object_geometry") or {}
        metadata.update(
            quality_score=response.get("quality_score", geometry.get("quality_score")),
            measurement_source=geometry.get("measurement_source") or response.get("source"),
            measured_dimensions=sorted((response.get("measurements") or {}).keys()),
            ready_for_cad_fit=response.get("ready_for_cad_fit", geometry.get("ready_for_cad_fit")),
        )
    elif name == "present_adaptation_options":
        metadata.update(
            recommended_strategy=response.get("recommended_strategy"),
            risk_level=response.get("risk_level"),
            custom_design_requested=response.get("custom_design_requested"),
            market_check_completed=response.get("market_check_completed"),
            market_check_status=response.get("market_check_status"),
            design_feature_count=len(response.get("design_features") or []),
        )
    elif name == "validate_design":
        metadata.update(
            valid=response.get("valid"),
            design_version=response.get("design_version"),
            measurement_source=response.get("measurement_source"),
            physical_fit_verified=response.get("physical_fit_verified"),
        )
    elif name == "generate_3d_design":
        metadata.update(
            design_version=response.get("design_version"),
            artifact_key=response.get("artifact_key"),
        )
    elif name in {"generate_usage_preview", "generate_environment_preview"}:
        metadata.update(
            artifact_version=response.get("artifact_version"),
            preview_status=response.get("status"),
        )
    elif name == "assess_support_need":
        metadata.update(
            risk_level=response.get("risk_level"),
            evidence_quality=response.get("evidence_quality"),
            data_completeness=response.get("data_completeness"),
            measurement_confidence=response.get("measurement_confidence"),
            image_quality=response.get("image_quality"),
            missing_dimension_count=len(response.get("missing_dimensions") or []),
            uncertain_input_count=len(response.get("uncertain_inputs") or []),
            fit_risk_rating=response.get("fit_risk_rating"),
            gemini_rating=response.get("gemini_rating"),
            concern_count=len(response.get("gemini_concerns") or []),
        )
    elif name == "offer_product_support":
        metadata.update(
            fit_risk_rating=response.get("fit_risk_rating"),
            risk_level=response.get("risk_level"),
            review_priority=response.get("review_priority"),
            evidence_quality=response.get("evidence_quality"),
        )
    elif name == "remember_adaptation_preference":
        metadata.update(
            memory_category=response.get("category"),
            memory_status=response.get("status"),
        )

    # Tool-authored rejection text (never user content) explains loops such as repeated
    # invalid plans; without it, logs only showed "status=error".
    if response.get("status") == "error" and response.get("error"):
        metadata["error_detail"] = str(response["error"])[:200]

    return {k: v for k, v in metadata.items() if v is not None}


def before_model_callback(callback_context: Any, llm_request: Any):
    session_id, turn_id = _context_ids(callback_context)
    turn_key = turn_id or "unknown"
    call_id = next(_model_seq)
    with _timing_lock:
        _model_active[turn_key] = call_id
        _model_starts[call_id] = time.perf_counter()
        _model_first_chunk_seen.discard(call_id)
    log_event(
        logger,
        logging.INFO,
        "Model request started",
        event_type="model_request_start",
        session_id=session_id,
        turn_id=turn_id,
        operation="agent_model",
        model_call_id=call_id,
        agent_name=getattr(callback_context, "agent_name", None),
    )
    return None


def after_model_callback(callback_context: Any, llm_response: Any):
    """Log streaming model timing once per logical model request.

    ADK invokes after_model_callback for progressive LlmResponse chunks. Intermediate
    chunks have partial=True; only partial=False is the final aggregated response.
    """
    session_id, turn_id = _context_ids(callback_context)
    turn_key = turn_id or "unknown"
    partial = bool(getattr(llm_response, "partial", False))

    with _timing_lock:
        call_id = _model_active.get(turn_key)
        started = _model_starts.get(call_id) if call_id is not None else None
        first_chunk = call_id is not None and call_id not in _model_first_chunk_seen
        if first_chunk:
            _model_first_chunk_seen.add(call_id)

    duration_ms = round((time.perf_counter() - started) * 1000) if started else None
    if first_chunk:
        log_event(
            logger,
            logging.INFO,
            "First model chunk received",
            event_type="model_first_chunk",
            session_id=session_id,
            turn_id=turn_id,
            operation="agent_model",
            model_call_id=call_id,
            duration_ms=duration_ms,
            partial=partial,
        )

    if partial:
        return None

    with _timing_lock:
        if call_id is not None:
            _model_active.pop(turn_key, None)
            _model_starts.pop(call_id, None)
            _model_first_chunk_seen.discard(call_id)
    log_event(
        logger,
        logging.INFO,
        "Model request completed",
        event_type="model_request_complete",
        session_id=session_id,
        turn_id=turn_id,
        operation="agent_model",
        model_call_id=call_id,
        duration_ms=duration_ms,
        status="success",
        agent_name=getattr(callback_context, "agent_name", None),
    )
    return None


def on_model_error_callback(callback_context: Any, llm_request: Any, error: Exception):
    """Log model exceptions without suppressing or replacing them."""
    session_id, turn_id = _context_ids(callback_context)
    turn_key = turn_id or "unknown"
    with _timing_lock:
        call_id = _model_active.pop(turn_key, None)
        started = _model_starts.pop(call_id, None) if call_id is not None else None
        if call_id is not None:
            _model_first_chunk_seen.discard(call_id)
    duration_ms = round((time.perf_counter() - started) * 1000) if started else None
    log_event(
        logger,
        logging.ERROR,
        "Model request failed",
        event_type="model_error",
        session_id=session_id,
        turn_id=turn_id,
        operation="agent_model",
        model_call_id=call_id,
        duration_ms=duration_ms,
        status="error",
        error_type=type(error).__name__,
        error_message=str(error)[:1000],
        agent_name=getattr(callback_context, "agent_name", None),
    )
    return None


def before_tool_callback(tool: Any, args: dict[str, Any], tool_context: Any):
    session_id, turn_id = _context_ids(tool_context)
    name = getattr(tool, "name", tool.__class__.__name__)
    with _timing_lock:
        _tool_starts[_key(turn_id, name)] = time.perf_counter()
    log_event(
        logger,
        logging.INFO,
        "Tool call started",
        event_type="tool_start",
        session_id=session_id,
        turn_id=turn_id,
        tool_name=name,
        status="started",
        argument_keys=sorted(args.keys()),
    )
    return None


def after_tool_callback(tool: Any, args: dict[str, Any], tool_context: Any, tool_response: dict[str, Any]):
    session_id, turn_id = _context_ids(tool_context)
    name = getattr(tool, "name", tool.__class__.__name__)
    with _timing_lock:
        started = _tool_starts.pop(_key(turn_id, name), None)
    duration_ms = round((time.perf_counter() - started) * 1000) if started else None
    status = "success"
    error_type = None
    if isinstance(tool_response, dict):
        if tool_response.get("status") in {"error", "recapture_required", "manual_preferred"} or tool_response.get("valid") is False:
            status = str(tool_response.get("status") or "rejected")
            error_type = str(tool_response.get("error_type") or "tool_result")
    log_event(
        logger,
        logging.INFO if status == "success" else logging.WARNING,
        "Tool call completed",
        event_type="tool_complete",
        session_id=session_id,
        turn_id=turn_id,
        tool_name=name,
        duration_ms=duration_ms,
        status=status,
        error_type=error_type,
        **_tool_result_metadata(name, tool_response),
    )
    return None


def on_tool_error_callback(tool: Any, args: dict[str, Any], tool_context: Any, error: Exception):
    """Log tool exceptions without suppressing or replacing them."""
    session_id, turn_id = _context_ids(tool_context)
    name = getattr(tool, "name", tool.__class__.__name__)
    with _timing_lock:
        started = _tool_starts.pop(_key(turn_id, name), None)
    duration_ms = round((time.perf_counter() - started) * 1000) if started else None
    log_event(
        logger,
        logging.ERROR,
        "Tool call failed",
        event_type="tool_error",
        session_id=session_id,
        turn_id=turn_id,
        tool_name=name,
        duration_ms=duration_ms,
        status="error",
        error_type=type(error).__name__,
        error_message=str(error)[:1000],
        argument_keys=sorted(args.keys()),
    )
    return None
