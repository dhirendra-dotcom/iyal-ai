"""Measurement plan accepts common method names and explains rejections; no photo is not an error."""
from types import SimpleNamespace

from app.tools import measurement
from app.tools.measurement_plan import present_measurement_plan


def _plan(context, **item):
    base = {"dimension": "interface_width_mm", "label": "Handle width", "instruction": "Place the spoon on A4."}
    return present_measurement_plan("spoon", "handle", "grip_sleeve", [{**base, **item}], context)


def test_method_aliases_are_normalized():
    context = SimpleNamespace(state={})
    result = _plan(context, preferred_method="calibrated_photo", fallback_method="Ruler")
    assert result["status"] == "ready"
    item = result["measurements"][0]
    assert (item["preferred_method"], item["fallback_method"]) == ("calibrated_top_photo", "manual_measurement")
    assert result["photo_dimensions"] == ["interface_width_mm"]


def test_invalid_method_error_lists_allowed_values():
    result = _plan(SimpleNamespace(state={}), preferred_method="laser_scan")
    assert result["status"] == "error"
    assert "laser_scan" in result["error"] and "manual_measurement" in result["error"]


def test_awkward_pose_is_still_rejected_with_guidance():
    result = _plan(SimpleNamespace(state={}), preferred_method="manual", instruction="Balance the spoon on its edge.")
    assert result["status"] == "error"
    assert "ruler" in result["error"]


def test_measuring_without_an_uploaded_photo_asks_for_one():
    result = measurement._compute_capture_measurement("", "spoon", "handle", ["interface_width_mm"], "a4")
    assert result["status"] == "photo_required"


def test_thickness_only_still_prefers_manual_measurement_without_photo():
    result = measurement._compute_capture_measurement("", "spoon", "handle", ["interface_depth_mm"], "a4")
    assert result["status"] == "manual_preferred"
