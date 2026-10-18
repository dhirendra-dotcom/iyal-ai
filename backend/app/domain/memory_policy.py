from __future__ import annotations

_ALLOWED_CATEGORIES = {"design_preference", "fit_feedback", "adaptation_outcome"}
_SENSITIVE_MARKERS = {
    "diagnos",
    "medicat",
    "treatment",
    "arthritis",
    "tremor",
    "pain",
    "injury",
    "disease",
    "condition",
    "symptom",
}


def normalize_memory_candidate(category: str, summary: str) -> dict:
    category = category.strip().lower()
    clean = " ".join(summary.split()).strip()[:500]
    if category not in _ALLOWED_CATEGORIES:
        return {"status": "error", "error": "Unsupported memory category."}
    if not clean:
        return {"status": "error", "error": "Memory summary is required."}
    lowered = clean.lower()
    if any(marker in lowered for marker in _SENSITIVE_MARKERS):
        return {
            "status": "rejected",
            "error": "Long-term memory must contain adaptation preferences/outcomes only, not health or symptom details.",
        }
    return {"status": "ready", "category": category, "summary": clean}


def outcome_memory_fact(outcome: str, *, design_state: dict | None = None) -> str:
    labels = {
        "much_easier": "made the task much easier",
        "slightly_easier": "made the task a little easier",
        "no_change": "did not make the task easier",
        "harder": "made the task harder",
    }
    result = labels.get(outcome, "had an unknown outcome")
    state = design_state or {}
    design = state.get("current_design") or {}
    profile = str(design.get("profile", "") or "").strip().lower()
    texture = str(design.get("texture", "") or "").strip().lower()
    feature_bits: list[str] = []
    if profile:
        feature_bits.append(f"{profile} profile")
    if texture:
        feature_bits.append(f"{texture} texture")
    feature_text = f" using a {' and '.join(feature_bits)}" if feature_bits else ""
    return f"One previous Iyal.ai adaptation{feature_text} {result} for me."
