from __future__ import annotations

from statistics import mean

from google.adk.tools import ToolContext


RECOMMENDATION_LEVELS = ["optional", "recommended", "strongly_recommended"]
FIT_RATINGS = ["GREEN", "AMBER", "RED"]
_RATING_RANK = {rating: index for index, rating in enumerate(FIT_RATINGS)}
MIN_LEVEL_FOR_RATING = {"GREEN": "optional", "AMBER": "recommended", "RED": "professional_visit_required"}

DIMENSION_LABELS = {
    "interface_width_mm": "handle width",
    "interface_depth_mm": "handle thickness",
    "available_length_mm": "available length",
    "object_length_mm": "object length",
}


def _label(dimension: str) -> str:
    return DIMENSION_LABELS.get(dimension, dimension.replace("_mm", "").replace("_", " "))


def _required_dimensions(state: dict) -> list[str]:
    plan = state.get("measurement_plan") or {}
    dimensions: list[str] = []
    for item in plan.get("measurements") or []:
        if isinstance(item, dict) and bool(item.get("required", True)):
            dimension = str(item.get("dimension", "")).strip()
            if dimension:
                dimensions.append(dimension)
    return dimensions


def _max_rating(*ratings: str) -> str:
    return max(ratings, key=lambda rating: _RATING_RANK[rating])


def assess_support_need(
    tool_context: ToolContext,
    fit_risk_rating: str = "",
    gemini_concerns: list[str] | None = None,
) -> dict:
    """Rate the fit risk of the completed prototype and explain it.

    fit_risk_rating is Gemini's judgement from the whole conversation:
      GREEN - low fit uncertainty; an optional fit review is enough.
      AMBER - meaningful uncertainty; a fit review is recommended before relying on it.
      RED   - high uncertainty (for example grip that changes a lot, fingers that cannot
              close, several unverified or approximate measurements); the prototype should
              only be used after a professional fit-review visit.
    gemini_concerns are short, plain-language reasons taken from the conversation
    (no diagnoses), e.g. "Grip strength changes through the day".

    Observed evidence (missing, approximate or rejected measurements, low capture
    quality) sets a floor: the final rating is never lower than the evidence supports.
    This tool does not invent an accuracy percentage.
    """
    state = tool_context.state
    risk_level = str(state.get("risk_level", "GREEN") or "GREEN").upper()

    if risk_level != "RED" and not state.get("current_design"):
        return {
            "status": "error",
            "error": "Generate the design before assessing fit-review support.",
        }
    if risk_level != "RED" and not bool(state.get("usage_preview_attempted")):
        return {
            "status": "error",
            "error": "Attempt the illustrative usage preview before assessing fit-review support.",
        }

    geometry = state.get("object_geometry") or {}
    measurements = geometry.get("measurements") or {}
    required = _required_dimensions(state)
    present_required = [dimension for dimension in required if dimension in measurements]
    completeness = 1.0 if not required else len(present_required) / len(required)
    missing = [dimension for dimension in required if dimension not in measurements]

    calibrated_confidences: list[float] = []
    manual_count = 0
    estimated_dimensions: list[str] = []
    approximate_dimensions: list[str] = []
    source_counts: dict[str, int] = {}
    for dimension, item in measurements.items():
        if not isinstance(item, dict):
            continue
        source = str(item.get("source", "unknown") or "unknown")
        source_counts[source] = source_counts.get(source, 0) + 1
        if source == "user_measurement":
            manual_count += 1
            if item.get("approximate"):
                approximate_dimensions.append(str(dimension))
        confidence = item.get("confidence")
        if source == "calibrated_photo" and isinstance(confidence, (int, float)):
            calibrated_confidences.append(float(confidence))
        if source not in {"calibrated_photo", "user_measurement", "trusted_known_dimension"}:
            estimated_dimensions.append(str(dimension))
    rejected = dict(geometry.get("rejected_readings") or {})

    measurement_confidence = (
        round(mean(calibrated_confidences), 3) if calibrated_confidences else None
    )
    image_quality_raw = geometry.get("quality_score")
    image_quality = (
        round(float(image_quality_raw), 3)
        if isinstance(image_quality_raw, (int, float))
        else None
    )

    uncertain_inputs: list[str] = []
    evidence_reasons: list[str] = []
    if missing:
        uncertain_inputs.append("Missing required dimensions: " + ", ".join(missing))
        evidence_reasons.append("Missing measurement: " + ", ".join(_label(d) for d in missing))
    if estimated_dimensions:
        uncertain_inputs.append("Estimated/unverified dimensions: " + ", ".join(estimated_dimensions))
        evidence_reasons.append("Estimated, not measured: " + ", ".join(_label(d) for d in estimated_dimensions))
    if approximate_dimensions:
        uncertain_inputs.append("Approximate user measurements: " + ", ".join(approximate_dimensions))
        evidence_reasons.append("Given as approximate: " + ", ".join(_label(d) for d in approximate_dimensions))
    for dimension, item in rejected.items():
        value = item.get("value_mm") if isinstance(item, dict) else None
        replaced = dimension in measurements
        reading = f" ({float(value):.1f} mm)" if isinstance(value, (int, float)) else ""
        evidence_reasons.append(
            f"Photo reading for {_label(dimension)}{reading} was rejected as implausible"
            + ("; your ruler value is used instead" if replaced else "")
        )
    if image_quality is not None and image_quality < 0.75:
        uncertain_inputs.append("Calibrated image quality is below the preferred confidence range.")
        evidence_reasons.append("Photo calibration quality is below 0.75")
    if measurement_confidence is not None and measurement_confidence < 0.75:
        uncertain_inputs.append("Calibrated measurement confidence is below the preferred range.")
    if completeness < 1.0:
        uncertain_inputs.append("Required fit data is incomplete.")

    if completeness < 0.75 or (image_quality is not None and image_quality < 0.6) or len(approximate_dimensions) >= 2:
        evidence_quality = "low"
    elif uncertain_inputs or rejected or completeness < 1.0:
        evidence_quality = "moderate"
    else:
        evidence_quality = "high"

    # Floor from observed evidence and the earlier recommendation risk.
    evidence_floor = "AMBER" if evidence_quality == "low" else "GREEN"
    early_floor = risk_level if risk_level in _RATING_RANK else "GREEN"
    gemini_rating = str(fit_risk_rating or "").strip().upper()
    if gemini_rating not in _RATING_RANK:
        gemini_rating = ""
    final_rating = _max_rating(evidence_floor, early_floor, gemini_rating or "GREEN")

    concerns = [str(c).strip() for c in (gemini_concerns or []) if str(c).strip()][:6]
    minimum_level = MIN_LEVEL_FOR_RATING[final_rating]
    # Reasons are shown only when the rating or evidence crosses a threshold.
    show_reasons = final_rating != "GREEN" or evidence_quality != "high"

    result = {
        "status": "ready",
        "risk_level": risk_level,
        "fit_risk_rating": final_rating,
        "gemini_rating": gemini_rating or None,
        "evidence_floor": _max_rating(evidence_floor, early_floor),
        "gemini_concerns": concerns,
        "evidence_reasons": evidence_reasons,
        "show_reasons": show_reasons,
        "data_completeness": round(completeness, 3),
        "required_dimensions": required,
        "missing_dimensions": missing,
        "measurement_confidence": measurement_confidence,
        "image_quality": image_quality,
        "manual_measurement_count": manual_count,
        "measurement_sources": source_counts,
        "estimated_dimensions": estimated_dimensions,
        "approximate_dimensions": approximate_dimensions,
        "rejected_readings": sorted(rejected),
        "uncertain_inputs": uncertain_inputs,
        "evidence_quality": evidence_quality,
        "physical_fit_verified": False,
        "preview_status": str(state.get("usage_preview_status", "unknown")),
        "allowed_recommendation_levels": RECOMMENDATION_LEVELS,
        "minimum_recommendation_level": minimum_level,
        "guidance": (
            "Call offer_product_support next. For RED, the support offer becomes a required "
            "professional fit-review visit before the prototype is used. Do not invent a percentage accuracy."
        ),
    }
    if gemini_rating and final_rating != gemini_rating:
        result["rating_note"] = f"Raised from {gemini_rating} to {final_rating} by the observed evidence."
    state["support_need_assessment"] = result
    state["fit_risk_rating"] = final_rating
    return result
