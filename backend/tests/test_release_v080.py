from types import SimpleNamespace

from app.tools.adaptation import present_adaptation_options
from app.tools.support import offer_product_support
from app.tools.support_assessment import assess_support_need
from app.tools.validation import validate_design


def _custom_kwargs(context, *, custom_requested=False, review=False):
    return dict(
        problem_summary="A spoon twists during use.",
        context_type="object",
        user_goal="Use the spoon with less twisting.",
        task="Eating",
        object_name="Spoon",
        functional_barrier="The handle rotates in the hand.",
        decision_rationale="An oval ribbed sleeve can improve rotational control.",
        risk_reason="Low-risk handheld adaptation.",
        options=[{"strategy": "custom_cad", "title": "Custom grip sleeve"}],
        recommended_strategy="custom_cad",
        requires_measurement=True,
        professional_review_recommended=review,
        usage_evidence_required=False,
        tool_context=context,
        custom_design_requested=custom_requested,
        design_features=[
            {"feature": "Profile", "value": "oval", "reason": "resists rotation"},
            {"feature": "Texture", "value": "ribbed", "reason": "improves surface grip"},
        ],
    )


def test_custom_cad_requires_market_check_when_not_explicitly_requested():
    context = SimpleNamespace(state={})
    result = present_adaptation_options(**_custom_kwargs(context))
    assert result["status"] == "error"
    assert "market check" in result["error"].lower()


def test_custom_cad_exposes_design_features_after_market_check():
    context = SimpleNamespace(state={"market_check_completed": True, "market_check_status": "ready"})
    result = present_adaptation_options(**_custom_kwargs(context))
    assert result["status"] == "ready"
    assert result["market_check_completed"] is True
    assert result["design_features"][0]["feature"] == "Profile"


def test_validation_has_backup_market_check_gate():
    context = SimpleNamespace(
        state={"adaptation_options": {"recommended_strategy": "custom_cad", "custom_design_requested": False}}
    )
    result = validate_design(
        outer_width_mm=28,
        outer_depth_mm=22,
        grip_length_mm=82,
        interface_width_mm=7.2,
        interface_depth_mm=3.5,
        clearance_per_side_mm=0.4,
        angle_deg=5,
        profile="oval",
        texture="ribbed",
        palm_flare=False,
        measurement_source="user_provided",
        tool_context=context,
    )
    assert result["valid"] is False
    assert result["violations"][0]["field"] == "market_check"


def test_support_assessment_uses_real_completeness_and_capture_confidence():
    context = SimpleNamespace(
        state={
            "risk_level": "GREEN",
            "current_design": {"template": "GRIP_SLEEVE_V1"},
            "usage_preview_attempted": True,
            "usage_preview_status": "success",
            "measurement_plan": {
                "measurements": [
                    {"dimension": "interface_width_mm", "required": True},
                    {"dimension": "interface_depth_mm", "required": True},
                    {"dimension": "available_length_mm", "required": True},
                ]
            },
            "object_geometry": {
                "quality_score": 0.68,
                "measurements": {
                    "interface_width_mm": {"source": "calibrated_photo", "confidence": 0.68},
                    "interface_depth_mm": {"source": "user_measurement", "confidence": None},
                },
            },
        }
    )
    result = assess_support_need(context)
    assert result["status"] == "ready"
    assert result["data_completeness"] == 0.667
    assert result["measurement_confidence"] == 0.68
    assert result["evidence_quality"] == "low"
    assert "available_length_mm" in result["missing_dimensions"]


def test_green_custom_design_can_offer_optional_review():
    context = SimpleNamespace(
        state={
            "risk_level": "GREEN",
            "current_design": {"template": "GRIP_SLEEVE_V1"},
            "usage_preview_attempted": True,
            "support_need_assessment": {
                "status": "ready",
                "minimum_recommendation_level": "optional",
                "evidence_quality": "high",
                "data_completeness": 1.0,
                "measurement_confidence": 0.91,
                "image_quality": 0.91,
            },
        }
    )
    result = offer_product_support("optional", "Fit evidence is strong; review is optional.", context)
    assert result["status"] == "ready"
    assert result["review_priority"] == "optional"


def test_amber_support_floor_upgrades_optional_to_recommended():
    context = SimpleNamespace(
        state={
            "risk_level": "AMBER",
            "current_design": {"template": "GRIP_SLEEVE_V1"},
            "usage_preview_attempted": True,
            "support_need_assessment": {
                "status": "ready",
                "minimum_recommendation_level": "recommended",
                "evidence_quality": "moderate",
                "data_completeness": 1.0,
            },
        }
    )
    result = offer_product_support("optional", "Review is appropriate for this design.", context)
    assert result["status"] == "ready"
    assert result["review_priority"] == "recommended"
