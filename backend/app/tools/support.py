from __future__ import annotations

from google.adk.tools import ToolContext

from app.support_booking import get_available_slots
from app.tools.support_assessment import RECOMMENDATION_LEVELS


_LEVEL_RANK = {"optional": 0, "recommended": 1, "strongly_recommended": 2, "professional_visit_required": 3}


def offer_product_support(
    recommendation_level: str,
    reason: str,
    tool_context: ToolContext,
) -> dict:
    """Offer post-design fit support at the strength selected by Gemini.

    The evidence summary and fit-risk rating must be created first with
    assess_support_need(). The rating sets a floor on the offer: GREEN optional,
    AMBER at least recommended, RED a required professional fit-review visit
    before the prototype is used. A request that was RED before any design
    (outside the low-risk scope) gets no booking and no design.
    """
    risk_level = str(tool_context.state.get("risk_level", "GREEN") or "GREEN").upper()
    adaptation = tool_context.state.get("adaptation_options") or {}
    risk_reason = str(adaptation.get("risk_reason", "")).strip()

    if risk_level == "RED" and not tool_context.state.get("current_design"):
        return {
            "status": "professional_required",
            "risk_level": "RED",
            "message": (
                "This request is outside the low-risk implementation scope. "
                "An appropriate qualified professional should assess it before any change is made."
            ),
            "reason": reason.strip() or risk_reason,
        }

    if not tool_context.state.get("current_design"):
        return {
            "status": "error",
            "error": "Generate the custom design before offering a fit-review visit.",
        }
    if not bool(tool_context.state.get("usage_preview_attempted")):
        return {
            "status": "error",
            "error": "Attempt the illustrative usage preview before offering a fit-review visit.",
        }

    assessment = tool_context.state.get("support_need_assessment") or {}
    if assessment.get("status") != "ready":
        return {
            "status": "error",
            "error": "Call assess_support_need before offering professional support.",
        }

    level = recommendation_level.strip().lower()
    if level not in RECOMMENDATION_LEVELS:
        return {
            "status": "error",
            "error": "recommendation_level must be optional, recommended, or strongly_recommended.",
        }

    minimum = str(assessment.get("minimum_recommendation_level", "optional"))
    if minimum in _LEVEL_RANK and _LEVEL_RANK[level] < _LEVEL_RANK[minimum]:
        level = minimum
    rating = str(assessment.get("fit_risk_rating") or "GREEN")

    copy = {
        "optional": (
            "Would you like an optional fit review?",
            "A trained adaptation-support professional can help review prototype fit and practical setup before final use. This is not a medical consultation.",
        ),
        "recommended": (
            "A fit review is recommended",
            "Some fit evidence or implementation details would benefit from a trained adaptation-support review before you rely on the final prototype. This is not a medical consultation.",
        ),
        "strongly_recommended": (
            "I strongly recommend a fit review",
            "The available fit evidence has meaningful uncertainty. A trained adaptation-support professional should review the prototype fit and practical setup before final use. This is not a medical consultation.",
        ),
        "professional_visit_required": (
            "A professional fit-review visit is needed before use",
            "The fit uncertainty is high. Please don't rely on this prototype until a trained adaptation-support professional has checked its fit and setup with you, ideally in person. This is not a medical consultation.",
        ),
    }
    title, description = copy[level]
    slots = get_available_slots()
    result = {
        "status": "ready",
        "risk_level": risk_level,
        "fit_risk_rating": rating,
        "review_priority": level,
        "title": title,
        "description": description,
        "reason": reason.strip() or risk_reason,
        "gemini_concerns": assessment.get("gemini_concerns") or [],
        "evidence_reasons": assessment.get("evidence_reasons") or [],
        "show_reasons": bool(assessment.get("show_reasons")) or level != "optional",
        "rating_note": assessment.get("rating_note"),
        "evidence_quality": assessment.get("evidence_quality"),
        "data_completeness": assessment.get("data_completeness"),
        "measurement_confidence": assessment.get("measurement_confidence"),
        "image_quality": assessment.get("image_quality"),
        "visit_types": ["in_person", "video_review"] if level == "professional_visit_required" else ["video_review", "in_person"],
        "available_dates": slots,
    }
    tool_context.state["support_offer_shown"] = True
    tool_context.state["support_recommendation_level"] = level
    tool_context.state["support_offer"] = result
    return result
