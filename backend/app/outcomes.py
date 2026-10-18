from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


_OUTCOMES: dict[str, dict[str, Any]] = {}
ALLOWED_OUTCOMES = {"much_easier", "slightly_easier", "no_change", "harder"}


def record_outcome(
    *,
    session_id: str,
    user_id: str,
    outcome: str,
    comment: str = "",
    design_version: int | None = None,
) -> dict[str, Any]:
    if outcome not in ALLOWED_OUTCOMES:
        raise ValueError("Unsupported outcome value.")
    record = {
        "outcome_id": f"OUT-{uuid.uuid4().hex[:8].upper()}",
        "session_id": session_id,
        "user_id": user_id,
        "outcome": outcome,
        "comment": comment.strip()[:1000],
        "design_version": design_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _OUTCOMES[record["outcome_id"]] = record
    return record
