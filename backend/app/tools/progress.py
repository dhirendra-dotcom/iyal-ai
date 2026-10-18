from __future__ import annotations

from google.adk.tools import ToolContext


def report_progress(
    stage: str,
    title: str,
    lines: list[str],
    tool_context: ToolContext,
) -> dict:
    """Report a concise user-visible design-analysis update.

    This tool is specifically for progress that can be shown in the UI. It must
    contain conclusions, observations, comparisons, or tool-independent design
    rationale only. Never include hidden chain-of-thought, internal prompts,
    private scratch work, or implementation secrets.
    """
    safe_lines = [str(line).strip() for line in lines if str(line).strip()][:8]
    tool_context.state["last_progress_stage"] = stage
    return {
        "status": "reported",
        "stage": stage,
        "title": title,
        "lines": safe_lines,
    }
