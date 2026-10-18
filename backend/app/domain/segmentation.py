from __future__ import annotations

import base64
import logging
import threading
import time

import cv2
import numpy as np
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, Field

from app.config import settings
from app.logging_config import get_logger, log_event


logger = get_logger("arthistics.segmentation")


class TargetSegmentation(BaseModel):
    """Structured target-region localization returned by Gemini Vision."""

    label: str = Field(description="Short label for the requested target region.")
    box_2d: list[int] = Field(
        min_length=4,
        max_length=4,
        description=(
            "Bounding box [ymin, xmin, ymax, xmax], normalized from 0 to 1000 "
            "relative to the complete image."
        ),
    )
    mask: list[list[int]] = Field(
        default_factory=list,
        description=(
            "Polygon contour for the target inside the bounding box. Each [x,y] "
            "coordinate is normalized from 0 to 1000 relative to the bounding box."
        ),
    )
    fully_visible: bool = Field(
        description="True only when the complete requested target region is visible."
    )
    capture_quality: str = Field(
        description="One of: good, usable, poor. Judge visibility/occlusion, not physical dimensions."
    )
    issues: list[str] = Field(
        default_factory=list,
        description="Short visible issues such as glare, occlusion, blur, or cropped target.",
    )


_client_instance: genai.Client | None = None
_client_lock = threading.Lock()


def _client(force_new: bool = False) -> genai.Client:
    global _client_instance
    with _client_lock:
        if force_new or _client_instance is None:
            _client_instance = genai.Client()
        return _client_instance


TRANSIENT_STATUS_CODES = {429, 499, 500, 502, 503, 504}


def _downscale_for_localization(data: bytes, mime_type: str) -> tuple[bytes, str]:
    """Shrink the photo sent to Gemini; full-resolution bytes stay with OpenCV.

    Gemini returns 0-1000 normalized coordinates, so a smaller copy localizes the
    same target. Decoding with OpenCV also gives Gemini exactly the orientation
    that the metric measurement step decodes.
    """
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return data, mime_type
    height, width = image.shape[:2]
    scale = settings.segmentation_max_image_px / max(height, width)
    if scale < 1.0:
        image = cv2.resize(image, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return (encoded.tobytes(), "image/jpeg") if ok else (data, mime_type)


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, genai_errors.APIError):
        return getattr(exc, "code", None) in TRANSIENT_STATUS_CODES
    return "timeout" in type(exc).__name__.lower()


def _generate_segmentation(*, data: bytes, mime_type: str, prompt: str) -> str:
    """Fast path: low thinking, a per-attempt deadline and one retry on transient stalls.

    Live logs showed a single unbounded segmentation call taking 125 s; the bounded
    attempts keep a stalled request from holding the whole measurement turn.
    """
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=TargetSegmentation,
        temperature=0.0,
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW, include_thoughts=False),
        http_options=types.HttpOptions(timeout=settings.segmentation_attempt_timeout_seconds * 1000),
    )
    contents = [types.Part.from_text(text=prompt), types.Part.from_bytes(data=data, mime_type=mime_type)]
    model = settings.gemini_segmentation_model or settings.gemini_model
    attempts = max(1, settings.segmentation_max_attempts)
    for attempt in range(1, attempts + 1):
        started = time.perf_counter()
        try:
            response = _client().models.generate_content(model=model, contents=contents, config=config)
        except Exception as exc:
            if attempt >= attempts or not _is_transient(exc):
                raise
            log_event(
                logger,
                logging.WARNING,
                "Target segmentation attempt failed; retrying",
                event_type="model_call_retry",
                operation="target_segmentation",
                status="retry",
                attempt=attempt,
                error_type=type(exc).__name__,
            )
            continue
        log_event(
            logger,
            logging.INFO,
            "Target segmentation completed",
            event_type="model_call_complete",
            operation="target_segmentation",
            duration_ms=round((time.perf_counter() - started) * 1000),
            status="success",
            model=model,
            attempt=attempt,
            image_bytes=len(data),
        )
        return str(getattr(response, "text", "") or "")
    raise RuntimeError("unreachable")


def _create_interaction(*, data: bytes, mime_type: str, prompt: str):
    """Use the Gemini Interactions API for the one-shot segmentation helper.

    We intentionally do not set a thinking level here. Google documents the
    Interactions API as the current segmentation pattern, and omitting the
    optional thinking configuration avoids model/version-specific level errors.
    """
    encoded = base64.b64encode(data).decode("utf-8")
    request = {
        "model": settings.gemini_segmentation_model or settings.gemini_model,
        "input": [
            {"type": "text", "text": prompt},
            {"type": "image", "data": encoded, "mime_type": mime_type},
        ],
        "response_format": {
            "type": "text",
            "mime_type": "application/json",
            "schema": TargetSegmentation.model_json_schema(),
        },
        # This is a stateless one-shot helper; no server-side interaction history is needed.
        "store": False,
    }

    started = time.perf_counter()
    try:
        interaction = _client().interactions.create(**request)
    except RuntimeError as exc:
        if "closed" not in str(exc).lower():
            raise
        interaction = _client(force_new=True).interactions.create(**request)
    duration_ms = round((time.perf_counter() - started) * 1000)
    log_event(
        logger,
        logging.INFO,
        "Target segmentation completed",
        event_type="model_call_complete",
        operation="target_segmentation",
        duration_ms=duration_ms,
        status="success",
        model=request["model"],
    )
    return interaction


def segment_target_region_bytes(
    data: bytes,
    mime_type: str,
    target_region: str,
    object_name: str = "object",
) -> TargetSegmentation:
    """Locate one physical target region in image coordinates only.

    Gemini returns the semantic target geometry. It never estimates physical
    millimetres; OpenCV/reference calibration performs metric measurement.
    """
    prompt = f"""
Locate exactly the physical region requested below in the supplied image.

Object: {object_name}
Target region: {target_region}

Return one target only. The target should be the physical part that would mate
with or be enclosed by an adaptation. Return:
- label: short descriptive label;
- box_2d: [ymin, xmin, ymax, xmax], normalized 0-1000 for the whole image;
- mask: a tight polygon of at most 24 points following the visible target
  boundary, with [x,y] normalized 0-1000 inside that bounding box;
- fully_visible=false if cropped or materially occluded;
- capture_quality as exactly good, usable, or poor;
- visible capture issues only.

Do not estimate real-world millimetres. Do not include the A4/reference surface,
hands, or unrelated objects in the target. Do not diagnose a medical condition.
""".strip()

    small_data, small_mime = _downscale_for_localization(data, mime_type)
    try:
        output_text = _generate_segmentation(data=small_data, mime_type=small_mime, prompt=prompt)
    except Exception as exc:
        # Keep the previous Interactions API path as a fallback so a fast-path
        # failure degrades to the slower call instead of failing the measurement.
        log_event(
            logger,
            logging.WARNING,
            "Fast target segmentation failed; using Interactions fallback",
            event_type="model_call_error",
            operation="target_segmentation",
            status="fallback",
            error_type=type(exc).__name__,
        )
        output_text = ""
    if not output_text:
        try:
            interaction = _create_interaction(data=small_data, mime_type=small_mime, prompt=prompt)
        except Exception as exc:
            log_event(
                logger,
                logging.ERROR,
                "Target segmentation failed",
                event_type="model_call_error",
                operation="target_segmentation",
                status="error",
                error_type=type(exc).__name__,
            )
            raise
        output_text = getattr(interaction, "output_text", None)
    if not output_text:
        raise RuntimeError("Gemini did not return a target-region segmentation.")
    return TargetSegmentation.model_validate_json(output_text)
