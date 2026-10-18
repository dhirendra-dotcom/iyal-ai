from __future__ import annotations

from google.adk.tools import ToolContext

from app.domain.design_rules import validate_numeric_design


def validate_design(
    outer_width_mm: float,
    outer_depth_mm: float,
    grip_length_mm: float,
    interface_width_mm: float,
    interface_depth_mm: float,
    clearance_per_side_mm: float,
    angle_deg: float,
    profile: str,
    texture: str,
    palm_flare: bool,
    measurement_source: str,
    tool_context: ToolContext,
) -> dict:
    """Run deterministic design checks for a proposed GRIP_SLEEVE design.

    Internal validation means numeric/design constraints passed. It never means
    physical fit, comfort, benefit or manufacturing safety has been verified.
    """
    adaptation = tool_context.state.get("adaptation_options") or {}
    if (
        adaptation.get("recommended_strategy") == "custom_cad"
        and not bool(adaptation.get("custom_design_requested"))
        and not bool(tool_context.state.get("market_check_completed"))
    ):
        return {
            "valid": False,
            "violations": [
                {
                    "field": "market_check",
                    "message": "A live market check must be attempted before custom CAD unless the user explicitly requested custom design.",
                }
            ],
            "instruction": "Call search_existing_products before validating the custom design.",
        }

    if bool(tool_context.state.get("usage_evidence_required")) and not bool(tool_context.state.get("usage_video_received")):
        return {
            "valid": False,
            "violations": [
                {
                    "field": "usage_video",
                    "message": "This adaptation needs interaction evidence before Iyal.ai can finalize the personalized design.",
                }
            ],
            "instruction": "Ask naturally for a short usage video showing how the object is normally used, then call register_usage_video before validating again.",
        }

    design, violations = validate_numeric_design(
        outer_width_mm=outer_width_mm,
        outer_depth_mm=outer_depth_mm,
        grip_length_mm=grip_length_mm,
        interface_width_mm=interface_width_mm,
        interface_depth_mm=interface_depth_mm,
        clearance_per_side_mm=clearance_per_side_mm,
        angle_deg=angle_deg,
        profile=profile,
        texture=texture,
        palm_flare=palm_flare,
        measurement_source=measurement_source,
    )

    if design is None:
        return {
            "valid": False,
            "violations": violations,
            "instruction": "Revise the DesignSpec and call validate_design again.",
        }

    current_version = int(tool_context.state.get("current_design_version", 0))
    pending_version = current_version + 1
    params = design.to_dict()
    tool_context.state["validated_design"] = params
    tool_context.state["pending_design_version"] = pending_version
    tool_context.state["design_checks_passed"] = True

    return {
        "valid": True,
        "check_status": "passed",
        "physical_fit_verified": False,
        "user_facing_status": "Design checks passed. Physical fit remains unverified.",
        "template": params["template"],
        "design_version": pending_version,
        "design": params,
        "parameters": {
            "outer_width_mm": params["outer_width_mm"],
            "outer_depth_mm": params["outer_depth_mm"],
            "grip_length_mm": params["grip_length_mm"],
            "inner_width_mm": params["inner_width_mm"],
            "inner_depth_mm": params["inner_depth_mm"],
            "angle_deg": params["angle_deg"],
            "ribbed": params["ribbed"],
        },
        "measurement_source": params["measurement_source"],
    }
