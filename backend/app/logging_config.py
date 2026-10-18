from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


_STANDARD = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName", "processName",
    "process", "message", "asctime",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "severity": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD or key.startswith("_"):
                continue
            try:
                json.dumps(value)
                payload[key] = value
            except TypeError:
                payload[key] = str(value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


class PrettyFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        parts = [record.levelname]
        for key in ("session_id", "turn_id", "event_type", "tool_name", "operation"):
            value = getattr(record, key, None)
            if value not in (None, ""):
                parts.append(f"{key}={value}")
        parts.append(record.getMessage())
        duration = getattr(record, "duration_ms", None)
        if duration is not None:
            parts.append(f"duration_ms={duration}")
        return " | ".join(parts)


def configure_logging(level: str = "INFO", fmt: str = "auto") -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    if fmt == "auto":
        fmt = "json" if os.getenv("K_SERVICE") else "pretty"

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if fmt == "json" else PrettyFormatter())
    root.addHandler(handler)


def get_logger(name: str = "arthistics") -> logging.Logger:
    return logging.getLogger(name)


def log_event(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    event_type: str,
    session_id: str | None = None,
    turn_id: str | None = None,
    tool_name: str | None = None,
    operation: str | None = None,
    duration_ms: int | float | None = None,
    status: str | None = None,
    error_type: str | None = None,
    **fields: Any,
) -> None:
    extra = {
        "event_type": event_type,
        "session_id": session_id,
        "turn_id": turn_id,
        "tool_name": tool_name,
        "operation": operation,
        "duration_ms": duration_ms,
        "status": status,
        "error_type": error_type,
        **fields,
    }
    logger.log(level, message, extra={k: v for k, v in extra.items() if v is not None})
