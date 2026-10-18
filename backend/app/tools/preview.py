from __future__ import annotations

import asyncio
import base64
from copy import deepcopy
import mimetypes
import threading
from types import SimpleNamespace
from urllib.parse import urlparse

from google import genai
from google.adk.tools import ToolContext
from google.cloud import storage
from google.genai import types

from app.config import settings


_client_instance: genai.Client | None = None
_client_lock = threading.Lock()


def _client(force_new: bool = False) -> genai.Client:
    global _client_instance
    with _client_lock:
        if force_new or _client_instance is None:
            _client_instance = genai.Client()
        return _client_instance


def _download_reference(uri: str) -> tuple[bytes, str] | None:
    if not uri.strip():
        return None
    parsed = urlparse(uri)
    if parsed.scheme != "gs" or not parsed.netloc or not parsed.path:
        return None
    blob_name = parsed.path.lstrip("/")
    blob = storage.Client(project=settings.google_cloud_project).bucket(parsed.netloc).blob(blob_name)
    data = blob.download_as_bytes()
    try:
        blob.reload()
        mime_type = blob.content_type or ""
    except Exception:
        mime_type = ""
    return data, mime_type or mimetypes.guess_type(blob_name)[0] or "image/jpeg"


def _image_parts(response: object) -> list[object]:
    parts = getattr(response, "parts", None)
    if parts:
        return list(parts)
    candidates = getattr(response, "candidates", None) or []
    if candidates and getattr(candidates[0], "content", None):
        return list(getattr(candidates[0].content, "parts", None) or [])
    return []


def _generate_usage_preview_bytes(
    object_name: str,
    usage_context: str,
    reference_image_uri: str,
    tool_context: ToolContext,
) -> dict:
    """Generate an illustrative in-use preview after a validated 3D design.

    The image is explicitly a concept visualization, not a prediction of final
    fit, clinical outcome, or manufacturing performance.
    """
    design = tool_context.state.get("current_design")
    if not design:
        return {
            "status": "error",
            "error": "Generate the validated 3D design before creating an in-use preview.",
        }

    design_version = int(tool_context.state.get("current_design_version", 1))
    prompt = f"""
Create a realistic illustrative product-use preview for an everyday adaptive-design concept.

Object: {object_name}
Usage context: {usage_context or 'normal everyday use'}
Adaptation: an ergonomic grip sleeve fitted to the object's handle.
Design parameters:
- outer width: {design.get('outer_width_mm')} mm
- outer depth: {design.get('outer_depth_mm')} mm
- grip length: {design.get('grip_length_mm')} mm
- profile: {design.get('profile')}
- texture: {design.get('texture')}
- palm flare: {design.get('palm_flare')}

Show a generic adult person naturally holding and using the adapted object. Make the new grip sleeve clearly visible and plausible, with a close enough framing to understand hand-to-object interaction. Keep the scene ordinary, respectful, photorealistic, and free of medical labels, diagnosis, treatment claims, text overlays, logos, or exaggerated disability cues. Do not imply that the image proves fit or clinical benefit.
""".strip()

    contents: list[object] = [prompt]
    reference = _download_reference(reference_image_uri)
    if reference is not None:
        data, mime_type = reference
        contents.append(types.Part.from_bytes(data=data, mime_type=mime_type))
        contents.append(
            "Use the supplied object photo only as a visual reference for the object's appearance. "
            "Do not copy or infer a person's identity from it."
        )

    config = types.GenerateContentConfig(
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        response_modalities=["IMAGE"],
    )

    try:
        response = _client().models.generate_content(
            model=settings.gemini_image_model,
            contents=contents,
            config=config,
        )
    except RuntimeError as exc:
        if "closed" not in str(exc).lower():
            raise
        response = _client(force_new=True).models.generate_content(
            model=settings.gemini_image_model,
            contents=contents,
            config=config,
        )
    except Exception as exc:
        return {"status": "error", "error": f"Illustrative preview generation failed: {exc}"}

    image_data: bytes | None = None
    mime_type = "image/png"
    for part in _image_parts(response):
        inline = getattr(part, "inline_data", None)
        if inline is not None and getattr(inline, "data", None):
            image_data = inline.data
            if isinstance(image_data, str):
                image_data = base64.b64decode(image_data)
            mime_type = getattr(inline, "mime_type", None) or mime_type
            break

    if not image_data:
        return {
            "status": "error",
            "error": "The image model did not return an image preview.",
        }

    extension = ".jpg" if "jpeg" in mime_type else ".png"
    artifact_key = f"previews/usage-preview-v{design_version}{extension}"
    # Return the generated bytes to the async ADK tool wrapper below.
    return {
        "status": "generated_bytes",
        "artifact_key": artifact_key,
        "mime_type": mime_type,
        "image_bytes": image_data,
        "label": "Illustrative in-use preview",
        "disclaimer": "Concept visualization only. Final fit, comfort and manufacturability must be checked before ordering or use.",
    }


async def generate_usage_preview(
    object_name: str,
    usage_context: str,
    reference_image_uri: str,
    tool_context: ToolContext,
) -> dict:
    """Async ADK tool wrapper that stores the generated preview as an artifact."""
    tool_context.state["usage_preview_attempted"] = True
    tool_context.state["usage_preview_status"] = "started"
    # Network/image work must not block parallel tools or SSE heartbeats. Workers
    # receive a snapshot; ADK artifact and state writes stay on the event loop.
    snapshot = SimpleNamespace(state={
        "current_design": deepcopy(tool_context.state.get("current_design")),
        "current_design_version": tool_context.state.get("current_design_version", 1),
    })
    result = await asyncio.to_thread(
        _generate_usage_preview_bytes,
        object_name=object_name,
        usage_context=usage_context,
        reference_image_uri=reference_image_uri,
        tool_context=snapshot,
    )
    if result.get("status") != "generated_bytes":
        tool_context.state["usage_preview_status"] = str(result.get("status", "error"))
        return result

    image_data = result.pop("image_bytes")
    artifact_key = result["artifact_key"]
    mime_type = result["mime_type"]
    artifact_version = await tool_context.save_artifact(
        artifact_key,
        types.Part.from_bytes(data=image_data, mime_type=mime_type),
    )
    result["status"] = "success"
    result["artifact_version"] = artifact_version
    tool_context.state["usage_preview_artifact_key"] = artifact_key
    tool_context.state["usage_preview_artifact_version"] = artifact_version
    tool_context.state["usage_preview_status"] = "success"
    return result


def _generate_environment_preview_bytes(
    reference_image_uri: str,
    changes: list[str],
    tool_context: ToolContext,
) -> dict:
    """Generate an illustrative low-risk environment redesign preview."""
    if bool(tool_context.state.get("usage_evidence_required")) and not bool(tool_context.state.get("usage_video_received")):
        return {
            "status": "error",
            "error": "This environment recommendation needs interaction evidence before a personalized preview can be generated.",
        }
    reference = _download_reference(reference_image_uri)
    if reference is None:
        return {"status": "error", "error": "A room/environment reference image is required."}

    data, mime_type = reference
    change_lines = "\n".join(f"- {item}" for item in changes if item.strip())
    if not change_lines:
        return {"status": "error", "error": "At least one environment change is required."}

    prompt = f"""
Create a realistic illustrative preview of the supplied everyday environment after these low-risk changes:
{change_lines}

Preserve the room's identity and overall layout unless a listed change requires moving an item. Clearly visualize the safer/easier arrangement while keeping the image plausible and ordinary. Do not show structural construction, electrical work, medical equipment, text overlays, logos, or claims of guaranteed safety. This is only a concept preview for discussion.
""".strip()

    config = types.GenerateContentConfig(
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        response_modalities=["IMAGE"],
    )
    contents: list[object] = [prompt, types.Part.from_bytes(data=data, mime_type=mime_type)]

    try:
        response = _client().models.generate_content(
            model=settings.gemini_image_model,
            contents=contents,
            config=config,
        )
    except RuntimeError as exc:
        if "closed" not in str(exc).lower():
            raise
        response = _client(force_new=True).models.generate_content(
            model=settings.gemini_image_model,
            contents=contents,
            config=config,
        )
    except Exception as exc:
        return {"status": "error", "error": f"Environment preview generation failed: {exc}"}

    image_data: bytes | None = None
    out_mime = "image/png"
    for part in _image_parts(response):
        inline = getattr(part, "inline_data", None)
        if inline is not None and getattr(inline, "data", None):
            image_data = inline.data
            if isinstance(image_data, str):
                image_data = base64.b64decode(image_data)
            out_mime = getattr(inline, "mime_type", None) or out_mime
            break
    if not image_data:
        return {"status": "error", "error": "The image model did not return an environment preview."}

    extension = ".jpg" if "jpeg" in out_mime else ".png"
    artifact_key = f"previews/environment-preview-{tool_context.session.id[-8:]}{extension}"
    return {
        "status": "generated_bytes",
        "artifact_key": artifact_key,
        "mime_type": out_mime,
        "image_bytes": image_data,
        "label": "Illustrative environment preview",
        "disclaimer": "Concept visualization only. Confirm clearances and any physical changes before implementation.",
    }


async def generate_environment_preview(
    reference_image_uri: str,
    changes: list[str],
    tool_context: ToolContext,
) -> dict:
    """Create and store a low-risk environment redesign concept image."""
    snapshot = SimpleNamespace(
        state={
            "usage_evidence_required": tool_context.state.get("usage_evidence_required"),
            "usage_video_received": tool_context.state.get("usage_video_received"),
        },
        session=SimpleNamespace(id=tool_context.session.id),
    )
    result = await asyncio.to_thread(
        _generate_environment_preview_bytes,
        reference_image_uri=reference_image_uri,
        changes=changes,
        tool_context=snapshot,
    )
    if result.get("status") != "generated_bytes":
        return result
    image_data = result.pop("image_bytes")
    artifact_version = await tool_context.save_artifact(
        result["artifact_key"],
        types.Part.from_bytes(data=image_data, mime_type=result["mime_type"]),
    )
    result["status"] = "success"
    result["artifact_version"] = artifact_version
    return result
