from __future__ import annotations

import asyncio
import logging
from typing import Any

import agentplatform

from app.config import settings
from app.logging_config import get_logger, log_event

logger = get_logger("iyal.memory_writer")


def _memory_bank_name() -> str:
    value = settings.vertex_memory_bank_id.strip()
    if value.startswith("projects/"):
        return value
    return (
        f"projects/{settings.google_cloud_project}/locations/"
        f"{settings.context_service_location}/reasoningEngines/{value}"
    )



def _write_direct_memory_sync(*, user_id: str, fact: str, category: str) -> dict[str, object]:
    client = agentplatform.Client(
        project=settings.google_cloud_project,
        location=settings.context_service_location,
    )
    operation = client.memory_banks.memories.generate(
        name=_memory_bank_name(),
        direct_memories_source={"direct_memories": [{"fact": fact}]},
        scope={"user_id": user_id, "app_name": settings.app_name},
        config={
            "wait_for_completion": False,
            "metadata": {
                "source": {"string_value": "iyal"},
                "category": {"string_value": category},
            },
        },
    )
    return {
        "operation_name": str(getattr(operation, "name", "") or ""),
        "done": getattr(operation, "done", None),
    }


async def write_direct_memory(*, user_id: str, fact: str, category: str, session_id: str | None = None) -> None:
    if not settings.managed_memory_enabled:
        return
    log_event(
        logger,
        logging.INFO,
        "Memory Bank write requested",
        event_type="memory_write_started",
        session_id=session_id,
        status="started",
        category=category,
    )
    try:
        result = await asyncio.to_thread(
            _write_direct_memory_sync,
            user_id=user_id,
            fact=fact,
            category=category,
        )
        log_event(
            logger,
            logging.INFO,
            "Memory Bank generation request accepted",
            event_type="memory_write_accepted",
            session_id=session_id,
            status="accepted",
            category=category,
            operation_name=result.get("operation_name"),
            operation_done=result.get("done"),
        )
    except Exception as exc:
        log_event(
            logger,
            logging.WARNING,
            "Memory Bank write failed",
            event_type="memory_write_failed",
            session_id=session_id,
            status="error",
            category=category,
            error_type=type(exc).__name__,
            error_message=str(exc)[:1000],
        )
