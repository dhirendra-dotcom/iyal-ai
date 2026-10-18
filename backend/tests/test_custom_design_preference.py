from types import SimpleNamespace

import pytest

from app.tools.adaptation import present_adaptation_options
from app.tools.validation import validate_design


def _recommend(context, *, custom=True, strategy="custom_cad", review=False, usage=False):
    return present_adaptation_options(
        problem_summary="A spoon handle is difficult to hold.",
        context_type="object",
        user_goal="Use my spoon comfortably.",
        task="Eating",
        object_name="Spoon",
        functional_barrier="Small handle",
        decision_rationale="The user requested a custom grip.",
        risk_reason="Review requirements for the selected adaptation.",
        options=[{"strategy": strategy, "title": "Selected path"}],
        recommended_strategy=strategy,
        requires_measurement=True,
        professional_review_recommended=review,
        usage_evidence_required=usage,
        tool_context=context,
        custom_design_requested=custom,
    )


@pytest.mark.parametrize(
    ("strategy", "review", "expected_risk"),
    [("custom_cad", False, "GREEN"), ("custom_cad", True, "AMBER"), ("professional_help", False, "RED")],
)
def test_custom_preference_preserves_risk_and_fit_requirements(strategy, review, expected_risk):
    context = SimpleNamespace(state={})
    result = _recommend(context, strategy=strategy, review=review, usage=True)
    assert result["market_check_skipped"] is True
    assert result["requires_measurement"] is True
    assert result["risk_level"] == expected_risk
    assert context.state["usage_evidence_required"] is True
    assert context.state["professional_review_recommended"] is (expected_risk != "GREEN")


def test_buy_existing_requires_market_check():
    context = SimpleNamespace(state={})
    result = _recommend(context, custom=False, strategy="buy_existing")
    assert result["status"] == "error"
    assert result["required_tool"] == "search_existing_products"

    context.state.update({"market_check_completed": True, "market_check_status": "ready"})
    result = _recommend(context, custom=False, strategy="buy_existing")
    assert result["status"] == "ready"
    assert result["market_check_skipped"] is False
    assert context.state["custom_design_requested"] is False


@pytest.mark.parametrize("usage,source", [(True, "user_provided"), (False, "guessed")])
def test_custom_preference_does_not_bypass_validation(usage, source):
    context = SimpleNamespace(state={})
    _recommend(context, usage=usage)
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
        measurement_source=source,
        tool_context=context,
    )
    assert result["valid"] is False
    assert "validated_design" not in context.state
