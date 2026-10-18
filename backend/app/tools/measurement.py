from __future__ import annotations

import logging
import mimetypes
import time
from urllib.parse import urlparse

from google.adk.tools import ToolContext
from google.cloud import storage

from app.config import settings
from app.domain.measurement_core import _measure_segmented_target_bytes
from app.domain.segmentation import segment_target_region_bytes
from app.logging_config import get_logger, log_event


logger = get_logger("arthistics.measurement")

SUPPORTED_DIMENSIONS = {
    "interface_width_mm",
    "available_length_mm",
    "interface_depth_mm",
    "object_length_mm",
}


def _download_gcs(uri: str) -> tuple[bytes, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "gs" or not parsed.netloc or not parsed.path:
        raise ValueError("Physical measurement currently requires a gs:// image URI.")
    bucket_name = parsed.netloc
    blob_name = parsed.path.lstrip("/")
    client = storage.Client(project=settings.google_cloud_project)
    blob = client.bucket(bucket_name).blob(blob_name)
    data = blob.download_as_bytes()
    try:
        blob.reload()
        mime_type = blob.content_type or ""
    except Exception:
        mime_type = ""
    if not mime_type:
        mime_type = mimetypes.guess_type(blob_name)[0] or "image/jpeg"
    return data, mime_type


def _record_measurement(
    geometry: dict,
    *,
    dimension: str,
    value_mm: float,
    source: str,
    confidence: float | None,
    image_uri: str | None = None,
) -> None:
    geometry[dimension] = round(float(value_mm), 3)
    measurements = dict(geometry.get("measurements") or {})
    measurements[dimension] = {
        "value_mm": round(float(value_mm), 3),
        "source": source,
        "confidence": None if confidence is None else round(float(confidence), 3),
        "image_uri": image_uri,
    }
    geometry["measurements"] = measurements


def _measurement_source_summary(geometry: dict) -> str:
    sources = {
        item.get("source")
        for item in (geometry.get("measurements") or {}).values()
        if isinstance(item, dict) and item.get("source")
    }
    if not sources:
        return "missing"
    if sources == {"calibrated_photo"}:
        return "calibrated_capture"
    if sources == {"user_measurement"}:
        return "user_provided"
    return "mixed"


def _compute_capture_measurement(
    image_uri: str,
    object_name: str,
    target_region: str,
    dimensions: list[str],
    reference_type: str,
) -> dict:
    """Measure one or more dimensions from one natural calibrated photo.

    The normal path is a single top photo on A4. Gemini localizes the semantic
    target; OpenCV detects the reference, rectifies perspective, and converts
    image geometry to millimetres. The tool maps the target minor dimension to
    interface width and target major dimension to usable/object length.

    Interface depth/thickness should normally come from direct user measurement
    unless a separate easy, reliable capture method is available.
    """
    requested = [d.strip() for d in dimensions if d and d.strip()]
    unknown = [d for d in requested if d not in SUPPORTED_DIMENSIONS]
    if not requested:
        return {"status": "error", "error": "At least one dimension must be requested."}
    if unknown:
        return {"status": "error", "error": f"Unsupported dimensions: {unknown}"}
    manual_required = [d for d in requested if d == "interface_depth_mm"]
    photo_requested = [d for d in requested if d != "interface_depth_mm"]
    if not photo_requested:
        return {
            "status": "manual_preferred",
            "reason": (
                "Thickness/depth is normally easier and more reliable to measure directly "
                "than by asking the user to place the object in an awkward pose."
            ),
            "dimensions": manual_required,
            "instruction": "Measure the target thickness with a ruler or caliper and enter the value in millimetres.",
        }
    if not str(image_uri or "").startswith("gs://"):
        # Gemini sometimes calls this before any photo was shared; that is a missing
        # input, not a failed measurement.
        return {
            "status": "photo_required",
            "reason": "No photo has been shared yet in this conversation.",
            "instruction": (
                "Ask the user for one natural top photo of the object on a plain A4 sheet with all four "
                "corners visible, or for ruler measurements in millimetres. Do not call this tool until "
                "an uploaded image URI is available."
            ),
        }

    try:
        data, mime_type = _download_gcs(image_uri)
        segmentation = segment_target_region_bytes(
            data=data,
            mime_type=mime_type,
            target_region=target_region,
            object_name=object_name,
        )
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "Measurement segmentation failed",
            event_type="measurement_error",
            tool_name="measure_object_from_capture",
            operation="segmentation",
            status="error",
            error_type=type(exc).__name__,
        )
        return {
            "status": "error",
            "error_type": "SEGMENTATION_FAILED",
            "error": f"Target-region segmentation failed: {exc}",
        }

    if not segmentation.fully_visible or segmentation.capture_quality.lower() == "poor":
        issues = segmentation.issues or ["The requested target region is not fully measurable in this photo."]
        return {
            "status": "recapture_required",
            "reason": issues[0],
            "segmentation": segmentation.model_dump(),
            "instructions": [
                "Keep the complete target region visible and naturally flat on the A4 sheet.",
                "Keep all four A4 corners visible.",
                "Do not cover the target with a hand or another object.",
                "Retake the photo with good lighting and sharp focus.",
            ],
        }

    try:
        result = _measure_segmented_target_bytes(
            data=data,
            box_2d=segmentation.box_2d,
            mask=segmentation.mask,
            reference_type=reference_type,
        )
    except Exception as exc:
        return {
            "status": "error",
            "error_type": "REFERENCE_MEASUREMENT_FAILED",
            "error": str(exc),
        }

    result["object_name"] = object_name
    result["target_region"] = target_region
    result["requested_dimensions"] = requested
    result["photo_dimensions"] = photo_requested
    result["manual_required_dimensions"] = manual_required
    result["segmentation"] = segmentation.model_dump()

    if result.get("status") != "ok":
        return result

    semantic_factor = 1.0 if segmentation.capture_quality.lower() == "good" else 0.86
    quality = round(
        max(0.0, min(1.0, float(result.get("quality_score", 0.0)) * semantic_factor)),
        3,
    )
    result["quality_score"] = quality

    return result


def _apply_capture_measurement(
    result: dict,
    image_uri: str,
    target_region: str,
    tool_context: ToolContext,
    started: float,
    *,
    preserve_manual: bool = False,
) -> dict:
    """Merge computed measurements into current state without yielding."""
    if result.get("status") != "ok":
        return result
    photo_requested = result["photo_dimensions"]
    manual_required = result["manual_required_dimensions"]
    quality = result["quality_score"]
    geometry = dict(tool_context.state.get("object_geometry") or {})
    geometry["reference_type"] = result.get("reference_type")
    geometry["target_region"] = target_region
    geometry["quality_score"] = quality
    geometry["top_capture_uri"] = image_uri

    measured: dict[str, float] = {}
    rejected: dict[str, dict] = {}
    rejected_readings = dict(geometry.get("rejected_readings") or {})
    for dimension in photo_requested:
        existing = (geometry.get("measurements") or {}).get(dimension) or {}
        if preserve_manual and existing.get("source") == "user_measurement":
            result[dimension] = geometry[dimension]
            continue
        if dimension == "interface_width_mm":
            value = float(result.get("target_minor_mm"))
        elif dimension in {"available_length_mm", "object_length_mm"}:
            value = float(result.get("target_major_mm"))
        else:
            continue
        reason = _implausible_reading(dimension, value, result)
        if reason:
            rejected[dimension] = {"value_mm": round(value, 3), "reason": reason, "image_uri": image_uri}
            rejected_readings[dimension] = rejected[dimension]
            continue
        rejected_readings.pop(dimension, None)
        _record_measurement(
            geometry,
            dimension=dimension,
            value_mm=value,
            source="calibrated_photo",
            confidence=quality,
            image_uri=image_uri,
        )
        measured[dimension] = round(value, 3)
        result[dimension] = round(value, 3)

    captures = list(geometry.get("captures") or [])
    captures.append(
        {
            "capture_type": "calibrated_top_photo",
            "image_uri": image_uri,
            "reference_type": result.get("reference_type"),
            "target_major_mm": result.get("target_major_mm"),
            "target_minor_mm": result.get("target_minor_mm"),
            "quality_score": quality,
            "dimensions": list(measured.keys()),
        }
    )
    geometry["captures"] = captures[-6:]
    geometry["rejected_readings"] = rejected_readings
    geometry["measurement_source"] = _measurement_source_summary(geometry)
    geometry["ready_for_cad_fit"] = bool(
        geometry.get("interface_width_mm") and geometry.get("interface_depth_mm")
    )
    tool_context.state["object_geometry"] = geometry

    duration_ms = round((time.perf_counter() - started) * 1000)
    log_event(
        logger,
        logging.INFO,
        "Calibrated measurement completed",
        event_type="measurement_complete",
        tool_name="measure_object_from_capture",
        operation="a4_calibration",
        duration_ms=duration_ms,
        status="success",
        reference_type=result.get("reference_type"),
        quality_score=quality,
        measured_dimensions=list(measured.keys()),
    )

    result["measurements"] = {
        key: geometry["measurements"][key] for key in measured if key in geometry.get("measurements", {})
    }
    result["object_geometry"] = geometry
    result["ready_for_cad_fit"] = geometry["ready_for_cad_fit"]
    # quality_score describes how well the A4 reference was detected, not the target reading.
    result["quality_basis"] = "a4_reference_detection"
    if rejected:
        result["rejected_readings"] = rejected
    manual_next = [*rejected, *manual_required]
    if manual_next:
        result["next_action"] = {
            "type": "manual_measurement",
            "dimensions": manual_next,
            "instruction": (
                "Ask the user to measure these with a ruler or caliper and enter the values in millimetres. "
                "Rejected photo readings are implausible and must not be used."
                if rejected
                else "Measure the remaining thickness/depth with a ruler or caliper and enter the value in millimetres."
            ),
        }
    return result


# Plausible ranges for handheld objects the grip-sleeve CAD supports. A reading outside
# them (for example a 1.6 mm spoon-handle width caused by shadows) is rejected instead of
# being recorded as a calibrated measurement.
PLAUSIBLE_MM = {
    "interface_width_mm": (4.0, 40.0),
    "available_length_mm": (20.0, 300.0),
    "object_length_mm": (20.0, 400.0),
}


def _implausible_reading(dimension: str, value: float, result: dict) -> str | None:
    low, high = PLAUSIBLE_MM.get(dimension, (0.0, float("inf")))
    if not low <= value <= high:
        return f"{value:.1f} mm is outside the plausible {low:.0f}-{high:.0f} mm range for this object."
    major = result.get("target_major_mm")
    if dimension == "interface_width_mm" and isinstance(major, (int, float)) and value >= float(major):
        return "The width reading is not smaller than the length, so the outline was not located correctly."
    return None


def measure_object_from_capture(
    image_uri: str,
    object_name: str,
    target_region: str,
    dimensions: list[str],
    reference_type: str,
    tool_context: ToolContext,
) -> dict:
    """Measure dimensions from a calibrated photo and record their provenance."""
    started = time.perf_counter()
    result = _compute_capture_measurement(
        image_uri, object_name, target_region, dimensions, reference_type
    )
    return _apply_capture_measurement(
        result, image_uri, target_region, tool_context, started
    )


def register_manual_measurement(
    dimension: str,
    value_mm: float,
    tool_context: ToolContext,
    approximate: bool = False,
) -> dict:
    """Record an explicit user-provided physical dimension with provenance.

    Set approximate=true when the user signals uncertainty ("about", "maybe",
    "around", "I'm not sure"); the fit assessment then treats it as unverified.
    """
    dimension = dimension.strip()
    if dimension not in SUPPORTED_DIMENSIONS:
        return {"status": "error", "error": f"Unsupported dimension: {dimension}"}
    if value_mm <= 0 or value_mm > 5000:
        return {"status": "error", "error": "Measurement must be a positive millimetre value."}

    geometry = dict(tool_context.state.get("object_geometry") or {})
    _record_measurement(
        geometry,
        dimension=dimension,
        value_mm=value_mm,
        source="user_measurement",
        confidence=None,
    )
    geometry["measurements"][dimension]["approximate"] = bool(approximate)
    geometry["measurement_source"] = _measurement_source_summary(geometry)
    geometry["ready_for_cad_fit"] = bool(
        geometry.get("interface_width_mm") and geometry.get("interface_depth_mm")
    )
    tool_context.state["object_geometry"] = geometry

    return {
        "status": "ok",
        "dimension": dimension,
        "value_mm": round(float(value_mm), 3),
        "source": "user_measurement",
        "approximate": bool(approximate),
        "object_geometry": geometry,
        "ready_for_cad_fit": geometry["ready_for_cad_fit"],
    }



# v0.8.0 cleanup: `measure_calibrated_image` was an unregistered legacy ArUco
# ADK tool with no runtime call sites. It is intentionally commented out of the
# active tool surface; the lower-level ArUco measurement core remains available
# for tests/fallback research without being exposed to the agent.
