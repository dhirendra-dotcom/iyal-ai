from __future__ import annotations

from google.adk.tools import ToolContext


ALLOWED_METHODS = {
    "calibrated_top_photo",
    "manual_measurement",
    "trusted_known_dimension",
    "assisted_capture",
}
# Names Gemini has used for the same methods. Normalizing them avoids a loop of
# rejected plans (one live turn retried the plan 8 times).
METHOD_ALIASES = {
    "calibrated_photo": "calibrated_top_photo",
    "top_photo": "calibrated_top_photo",
    "a4_photo": "calibrated_top_photo",
    "photo": "calibrated_top_photo",
    "calibrated_capture": "calibrated_top_photo",
    "manual": "manual_measurement",
    "ruler": "manual_measurement",
    "user_measurement": "manual_measurement",
    "user_entered": "manual_measurement",
    "typed": "manual_measurement",
    "known_dimension": "trusted_known_dimension",
}
AWKWARD_POSE_PHRASES = ("edge view", "balance", "stand it on")


def _method(value: object) -> str:
    method = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return METHOD_ALIASES.get(method, method)


def _allowed_methods_text() -> str:
    return ", ".join(sorted(ALLOWED_METHODS))


def present_measurement_plan(
    object_name: str,
    target_region: str,
    adaptation_family: str,
    measurements: list[dict],
    tool_context: ToolContext,
) -> dict:
    """Present the minimum, easiest reliable measurement plan for the current design.

    Each measurement item should include:
      dimension: stable machine name such as interface_width_mm
      label: short user-facing name
      required: boolean
      preferred_method: calibrated_top_photo, manual_measurement,
        trusted_known_dimension or assisted_capture
      fallback_method: optional, one of the same methods
      instruction: simple user-facing instruction (never ask for an edge view,
        balancing the object or standing it on its side)

    The plan is dimension-first, not photo-first. Multiple dimensions may share
    one calibrated top photo. Avoid awkward object poses when a simple manual
    measurement is easier and more reliable.
    """
    cleaned: list[dict] = []
    for item in measurements:
        dimension = str(item.get("dimension", "")).strip()
        label = str(item.get("label", dimension)).strip()
        preferred = _method(item.get("preferred_method"))
        fallback = _method(item.get("fallback_method"))
        instruction = str(item.get("instruction", "")).strip()
        required = bool(item.get("required", True))
        if not dimension:
            return {"status": "error", "error": "Each measurement plan item needs a dimension such as interface_width_mm."}
        if preferred not in ALLOWED_METHODS:
            return {
                "status": "error",
                "error": (
                    f"Invalid preferred_method '{item.get('preferred_method')}' for '{dimension}'. "
                    f"Use one of: {_allowed_methods_text()}."
                ),
            }
        if fallback and fallback not in ALLOWED_METHODS:
            return {
                "status": "error",
                "error": f"Unsupported fallback_method '{item.get('fallback_method')}'. Use one of: {_allowed_methods_text()}, or omit it.",
            }
        lowered = instruction.lower()
        if any(phrase in lowered for phrase in AWKWARD_POSE_PHRASES):
            return {
                "status": "error",
                "error": (
                    f"The instruction for '{dimension}' must not require an awkward object pose "
                    "(edge view, balancing or standing it on its side). Use a natural top photo on A4 "
                    "or ask the user to measure it with a ruler."
                ),
            }
        cleaned.append(
            {
                "dimension": dimension,
                "label": label,
                "required": required,
                "preferred_method": preferred,
                "fallback_method": fallback or None,
                "instruction": instruction,
            }
        )

    if not cleaned:
        return {"status": "error", "error": "At least one required dimension is needed."}

    photo_dimensions = [x["dimension"] for x in cleaned if x["preferred_method"] == "calibrated_top_photo"]
    manual_dimensions = [x["dimension"] for x in cleaned if x["preferred_method"] == "manual_measurement"]
    plan = {
        "status": "ready",
        "object_name": object_name.strip(),
        "target_region": target_region.strip(),
        "adaptation_family": adaptation_family.strip(),
        "measurements": cleaned,
        "photo_count": 1 if photo_dimensions else 0,
        "photo_dimensions": photo_dimensions,
        "manual_dimensions": manual_dimensions,
        "reference_type": "a4" if photo_dimensions else None,
        "common_instructions": [
            "Only measurements needed for the selected adaptation are requested.",
            "For calibrated photos, place the target naturally and flat on a plain A4 sheet with all four corners visible.",
            "If a dimension is easier to measure directly with a ruler or caliper, enter that value instead of taking an awkward photo.",
            "Iyal.ai will not guess a missing physical dimension.",
        ],
    }
    tool_context.state["measurement_plan"] = plan
    return plan
