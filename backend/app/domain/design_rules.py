from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


CONFIG_DIR = Path(__file__).resolve().parents[1] / "runtime_config"
CONSTRAINTS = json.loads((CONFIG_DIR / "grip_sleeve_v1.json").read_text(encoding="utf-8"))
CAPABILITY = json.loads((CONFIG_DIR / "grip_sleeve_capability_v1.json").read_text(encoding="utf-8"))


@dataclass(frozen=True)
class ValidatedDesign:
    template: str
    adaptation_family: str
    profile: str
    texture: str
    palm_flare: bool
    measurement_source: str
    outer_width_mm: float
    outer_depth_mm: float
    grip_length_mm: float
    inner_width_mm: float
    inner_depth_mm: float
    interface_width_mm: float
    interface_depth_mm: float
    clearance_per_side_mm: float
    angle_deg: float
    ribbed: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _in_range(name: str, value: float, limits: dict, violations: list[dict]) -> None:
    low = float(limits["min"])
    high = float(limits["max"])
    if not low <= value <= high:
        violations.append(
            {
                "parameter": name,
                "value": value,
                "allowed_min": low,
                "allowed_max": high,
                "message": f"{name} must be between {low} and {high} mm.",
            }
        )


def validate_numeric_design(
    *,
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
) -> tuple[ValidatedDesign | None, list[dict]]:
    geometry = CONSTRAINTS["geometry"]
    fit = CONSTRAINTS["fit"]
    violations: list[dict] = []

    profile = profile.strip().lower()
    texture = texture.strip().lower()
    measurement_source = measurement_source.strip().lower()

    if profile not in set(CONSTRAINTS["allowed_profiles"]):
        violations.append({
            "parameter": "profile",
            "value": profile,
            "allowed_values": CONSTRAINTS["allowed_profiles"],
            "message": "Unsupported grip profile.",
        })
    if texture not in set(CONSTRAINTS["allowed_textures"]):
        violations.append({
            "parameter": "texture",
            "value": texture,
            "allowed_values": CONSTRAINTS["allowed_textures"],
            "message": "Unsupported grip texture.",
        })
    if measurement_source not in {"calibrated_capture", "user_provided", "mixed"}:
        violations.append({
            "parameter": "measurement_source",
            "value": measurement_source,
            "allowed_values": ["calibrated_capture", "user_provided", "mixed"],
            "message": "Unknown measurement source.",
        })

    _in_range("outer_width_mm", float(outer_width_mm), geometry["outer_width_mm"], violations)
    _in_range("outer_depth_mm", float(outer_depth_mm), geometry["outer_depth_mm"], violations)
    _in_range("grip_length_mm", float(grip_length_mm), geometry["adapter_length_mm"], violations)
    _in_range("angle_deg", float(angle_deg), geometry["angle_deg"], violations)
    _in_range(
        "clearance_per_side_mm",
        float(clearance_per_side_mm),
        fit["clearance_per_side_mm"],
        violations,
    )

    if interface_width_mm <= 0 or interface_depth_mm <= 0:
        violations.append({
            "parameter": "interface_geometry",
            "message": "Interface width and depth must be positive.",
        })

    inner_width = float(interface_width_mm) + 2.0 * float(clearance_per_side_mm)
    inner_depth = float(interface_depth_mm) + 2.0 * float(clearance_per_side_mm)
    min_wall = float(geometry["minimum_wall_mm"])

    wall_x = (float(outer_width_mm) - inner_width) / 2.0
    wall_y = (float(outer_depth_mm) - inner_depth) / 2.0
    if wall_x < min_wall:
        violations.append({
            "parameter": "outer_width_mm",
            "value": float(outer_width_mm),
            "required_min_wall_mm": min_wall,
            "actual_wall_mm": round(wall_x, 3),
            "message": "Outer width leaves insufficient wall around the measured object.",
        })
    if wall_y < min_wall:
        violations.append({
            "parameter": "outer_depth_mm",
            "value": float(outer_depth_mm),
            "required_min_wall_mm": min_wall,
            "actual_wall_mm": round(wall_y, 3),
            "message": "Outer depth leaves insufficient wall around the measured object.",
        })

    if violations:
        return None, violations

    design = ValidatedDesign(
        template=CAPABILITY["cad_family_id"],
        adaptation_family="grip_sleeve",
        profile=profile,
        texture=texture,
        palm_flare=bool(palm_flare),
        measurement_source=measurement_source,
        outer_width_mm=float(outer_width_mm),
        outer_depth_mm=float(outer_depth_mm),
        grip_length_mm=float(grip_length_mm),
        inner_width_mm=inner_width,
        inner_depth_mm=inner_depth,
        interface_width_mm=float(interface_width_mm),
        interface_depth_mm=float(interface_depth_mm),
        clearance_per_side_mm=float(clearance_per_side_mm),
        angle_deg=float(angle_deg),
        ribbed=texture == "ribbed",
    )
    return design, []
