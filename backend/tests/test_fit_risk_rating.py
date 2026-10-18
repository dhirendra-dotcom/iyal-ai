"""Scenario 3: Gemini rates fit risk after the design; evidence sets a floor; RED leads to a required visit."""
from types import SimpleNamespace

from app import support_booking
from app.tools import measurement
from app.tools.support import offer_product_support
from app.tools.support_assessment import assess_support_need


PLAN = {"measurements": [
    {"dimension": "interface_width_mm", "required": True},
    {"dimension": "interface_depth_mm", "required": True},
]}


def _context(measurements, rejected=None, risk="GREEN"):
    return SimpleNamespace(state={
        "risk_level": risk,
        "current_design": {"profile": "oval"},
        "usage_preview_attempted": True,
        "measurement_plan": PLAN,
        "object_geometry": {"measurements": measurements, "rejected_readings": rejected or {}, "quality_score": 0.95},
    })


TYPED = {"value_mm": 15.0, "source": "user_measurement", "confidence": None}


def test_green_with_strong_evidence_hides_reasons():
    context = _context({"interface_width_mm": TYPED, "interface_depth_mm": TYPED})
    result = assess_support_need(context, fit_risk_rating="GREEN")
    assert result["fit_risk_rating"] == "GREEN"
    assert result["show_reasons"] is False
    offer = offer_product_support("optional", "Fit evidence is strong.", context)
    assert offer["review_priority"] == "optional" and offer["show_reasons"] is False


def test_gemini_red_rating_requires_a_professional_visit_with_booking():
    context = _context({"interface_width_mm": TYPED, "interface_depth_mm": TYPED})
    result = assess_support_need(context, fit_risk_rating="red", gemini_concerns=["Grip strength changes through the day", " "])
    assert result["fit_risk_rating"] == "RED"
    assert result["gemini_concerns"] == ["Grip strength changes through the day"]
    offer = offer_product_support("optional", "High fit uncertainty.", context)
    assert offer["status"] == "ready"
    assert offer["review_priority"] == "professional_visit_required"
    assert offer["visit_types"][0] == "in_person"
    assert offer["available_dates"]


def test_low_evidence_raises_a_green_rating_to_amber():
    approx = {**TYPED, "approximate": True}
    context = _context({"interface_width_mm": approx, "interface_depth_mm": approx})
    result = assess_support_need(context, fit_risk_rating="GREEN")
    assert result["evidence_quality"] == "low"
    assert result["fit_risk_rating"] == "AMBER"
    assert "Raised from GREEN" in result["rating_note"]
    offer = offer_product_support("optional", "", context)
    assert offer["review_priority"] == "recommended"


def test_rejected_photo_reading_is_explained():
    context = _context(
        {"interface_width_mm": TYPED, "interface_depth_mm": TYPED},
        rejected={"interface_width_mm": {"value_mm": 1.6, "reason": "too small"}},
    )
    result = assess_support_need(context, fit_risk_rating="AMBER")
    assert result["show_reasons"] is True
    assert any("1.6 mm" in reason and "ruler value" in reason for reason in result["evidence_reasons"])


def test_red_before_any_design_still_gets_no_booking():
    context = SimpleNamespace(state={"risk_level": "RED"})
    offer = offer_product_support("optional", "Outside scope.", context)
    assert offer["status"] == "professional_required"
    assert "available_dates" not in offer


def test_implausible_photo_width_is_rejected_not_recorded():
    context = SimpleNamespace(state={})
    result = {
        "status": "ok", "photo_dimensions": ["interface_width_mm", "available_length_mm"],
        "manual_required_dimensions": [], "quality_score": 0.96, "reference_type": "a4",
        "target_minor_mm": 1.6, "target_major_mm": 108.4,
    }
    out = measurement._apply_capture_measurement(result, "gs://b/p.jpg", "handle", context, 0.0)
    geometry = context.state["object_geometry"]
    assert "interface_width_mm" not in geometry["measurements"]
    assert geometry["measurements"]["available_length_mm"]["value_mm"] == 108.4
    assert out["rejected_readings"]["interface_width_mm"]["value_mm"] == 1.6
    assert "interface_width_mm" in out["next_action"]["dimensions"]


def test_approximate_typed_value_is_recorded():
    context = SimpleNamespace(state={})
    out = measurement.register_manual_measurement("interface_depth_mm", 3.0, context, approximate=True)
    assert out["approximate"] is True
    assert context.state["object_geometry"]["measurements"]["interface_depth_mm"]["approximate"] is True


def test_confirmed_visit_is_shared_with_gemini(monkeypatch):
    monkeypatch.setattr(support_booking, "_BOOKINGS", {"ART-1": {
        "booking_id": "ART-1", "session_id": "ses-1", "date": "2026-10-19", "time_slot": "10:00 AM",
        "visit_type": "in_person", "created_at": "2026-10-18T00:00:00+00:00",
    }})
    context = support_booking.booking_context("ses-1")
    assert "ART-1" in context and "2026-10-19" in context and "in person" in context
    assert support_booking.booking_context("ses-2") == ""
