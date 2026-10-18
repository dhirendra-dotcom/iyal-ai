from __future__ import annotations

import re
import uuid


_AGENT_PLATFORM_SESSION_ID = re.compile(r"^[a-z][a-z0-9-]{0,61}[a-z0-9]$")


def new_user_id() -> str:
    """Return an opaque stable-identity fallback within Agent Platform's 128-char user limit."""
    return f"usr-{uuid.uuid4().hex[:16]}"


def new_session_id() -> str:
    """Return a valid custom Agent Platform Session ID (lowercase alphanumeric + hyphen)."""
    return f"ses-{uuid.uuid4().hex}"


def is_valid_custom_session_id(value: str) -> bool:
    return bool(_AGENT_PLATFORM_SESSION_ID.fullmatch(value))
