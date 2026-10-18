from app.domain.design_rules import validate_numeric_design


def test_valid_grip_sleeve_design():
    design, violations = validate_numeric_design(
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
    )
    assert violations == []
    assert design is not None
    assert design.inner_width_mm == 8.0
    assert design.inner_depth_mm == 4.3


def test_rejects_insufficient_wall():
    design, violations = validate_numeric_design(
        outer_width_mm=18,
        outer_depth_mm=15,
        grip_length_mm=82,
        interface_width_mm=16,
        interface_depth_mm=12,
        clearance_per_side_mm=0.8,
        angle_deg=5,
        profile="oval",
        texture="smooth",
        palm_flare=False,
        measurement_source="user_provided",
    )
    assert design is None
    assert any("insufficient wall" in v["message"].lower() for v in violations)


def test_rejects_unknown_profile():
    design, violations = validate_numeric_design(
        outer_width_mm=28,
        outer_depth_mm=22,
        grip_length_mm=82,
        interface_width_mm=7.2,
        interface_depth_mm=3.5,
        clearance_per_side_mm=0.4,
        angle_deg=5,
        profile="square",
        texture="ribbed",
        palm_flare=False,
        measurement_source="user_provided",
    )
    assert design is None
    assert any(v.get("parameter") == "profile" for v in violations)


def test_rejects_prototype_fallback_measurement_source():
    design, violations = validate_numeric_design(
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
        measurement_source="prototype_fallback",
    )
    assert design is None
    assert any(v.get("parameter") == "measurement_source" for v in violations)
