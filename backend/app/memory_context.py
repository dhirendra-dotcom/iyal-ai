from __future__ import annotations

from google.adk.agents.callback_context import CallbackContext
from google.adk.tools import ToolContext

from app.config import settings
from app.domain.memory_policy import normalize_memory_candidate
from app.logging_config import get_logger, log_event


logger = get_logger("iyal.memory")

def remember_adaptation_preference(
    category: str,
    summary: str,
    tool_context: ToolContext,
) -> dict:
    """Queue explicit durable adaptation feedback for Memory Bank generation.

    Use only for user-stated design preferences, real-world fit feedback, or
    adaptation outcomes. Do not use this tool to persist diagnoses, symptoms,
    contact details, or object-specific measurements.
    """
    candidate = normalize_memory_candidate(category, summary)
    if candidate.get("status") != "ready":
        return candidate
    if not settings.managed_memory_enabled:
        return {"status": "disabled", "message": "Memory Bank is not configured."}

    tool_context.state["memory_write_pending"] = True
    tool_context.state["memory_candidate"] = {
        "category": candidate["category"],
        "summary": candidate["summary"],
    }
    return {"status": "queued", "category": candidate["category"]}


async def generate_memories_callback(callback_context: CallbackContext):
    """Generate Memory Bank entries only when a memory candidate was queued."""
    if not settings.managed_memory_enabled:
        return None
    if not bool(callback_context.state.get("memory_write_pending")):
        return None

    events = list(callback_context.session.events or [])
    if not events:
        callback_context.state["memory_write_pending"] = False
        return None

    # Incremental generation keeps re-processing bounded. The tool call carrying
    # the normalized preference/outcome is part of these recent session events.
    candidate = callback_context.state.get("memory_candidate") or {}
    try:
        await callback_context.add_events_to_memory(events=events[-6:])
        log_event(
            logger,
            20,
            "Durable adaptation memory generation requested",
            event_type="memory_generation",
            session_id=getattr(callback_context.session, "id", None),
            status="success",
            category=candidate.get("category"),
        )
    except Exception as exc:
        # Memory is personalization infrastructure, not a blocker for the live
        # adaptation response. Surface the failure through structured logs.
        log_event(
            logger,
            30,
            "Durable adaptation memory generation failed",
            event_type="memory_generation",
            session_id=getattr(callback_context.session, "id", None),
            status="error",
            category=candidate.get("category"),
            error_type=type(exc).__name__,
        )
    finally:
        callback_context.state["memory_write_pending"] = False
    return None
