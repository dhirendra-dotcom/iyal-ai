from __future__ import annotations

from google.adk.tools import ToolContext


def register_usage_video(
    video_uri: str,
    tool_context: ToolContext,
) -> dict:
    """Record optional interaction evidence for this session.

    The agent can directly inspect the multimodal video in its conversation
    context. This tool records provenance so validation can require video only
    for adaptation paths where interaction evidence materially matters.
    """
    uri = video_uri.strip()
    if not uri.startswith("gs://"):
        return {
            "status": "error",
            "error": "The usage video must reference an uploaded gs:// artifact.",
        }

    tool_context.state["usage_video_received"] = True
    tool_context.state["usage_video_uri"] = uri
    return {
        "status": "registered",
        "usage_video_received": True,
    }
