from __future__ import annotations

import asyncio
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

import trimesh
from google.adk.tools import ToolContext
from google.genai import types

from app.config import settings


BACKEND_ROOT = Path(__file__).resolve().parents[2]
CAD_TEMPLATE = BACKEND_ROOT / "cad" / "utensil_grip.scad"


def _bool_scad(value: bool) -> str:
    return "true" if value else "false"


def _resolve_openscad_binary() -> str | None:
    configured = settings.openscad_binary.strip().strip('"')
    configured_path = Path(configured)
    if configured_path.is_file():
        return str(configured_path)
    return shutil.which(configured)


def _run_openscad(params: dict, output_path: Path) -> dict:
    shift_mm = math.tan(math.radians(float(params["angle_deg"]))) * float(
        params["grip_length_mm"]
    )

    openscad_binary = _resolve_openscad_binary()
    if not openscad_binary:
        return {
            "status": "error",
            "error": f"OpenSCAD executable '{settings.openscad_binary}' was not found.",
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        openscad_binary,
        "-o",
        str(output_path),
        "-D",
        f'profile="{params["profile"]}"',
        "-D",
        f'outer_width={float(params["outer_width_mm"])}',
        "-D",
        f'outer_depth={float(params["outer_depth_mm"])}',
        "-D",
        f'grip_length={float(params["grip_length_mm"])}',
        "-D",
        f'inner_width={float(params["inner_width_mm"])}',
        "-D",
        f'inner_depth={float(params["inner_depth_mm"])}',
        "-D",
        f'path_shift={shift_mm}',
        "-D",
        f'ribbed={_bool_scad(bool(params["ribbed"]))}',
        "-D",
        f'palm_support={_bool_scad(bool(params.get("palm_flare", False)))}',
        str(CAD_TEMPLATE),
    ]

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        return {
            "status": "error",
            "error": f"OpenSCAD executable '{openscad_binary}' was not found.",
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "error": "OpenSCAD generation timed out."}

    if completed.returncode != 0 or not output_path.exists():
        diagnostic = (completed.stderr or completed.stdout or "").strip()[-2000:]
        return {
            "status": "error",
            "error": (
                "OpenSCAD failed to generate the model."
                + (f" Details: {diagnostic}" if diagnostic else "")
            ),
            "returncode": completed.returncode,
            "stderr": completed.stderr[-2000:],
            "stdout": completed.stdout[-2000:],
            "command": command,
        }

    try:
        mesh = trimesh.load_mesh(output_path, force="mesh")
        extents = [round(float(x), 2) for x in mesh.extents]
        mesh_info = {
            "watertight": bool(mesh.is_watertight),
            "vertices": int(len(mesh.vertices)),
            "faces": int(len(mesh.faces)),
            "extents_mm": extents,
        }
    except Exception as exc:  # mesh inspection should not destroy an otherwise usable STL
        mesh_info = {"inspection_warning": str(exc)}

    return {
        "status": "success",
        "path": str(output_path),
        "mesh": mesh_info,
        "openscad_stderr": completed.stderr[-1000:],
    }


async def generate_3d_design(tool_context: ToolContext) -> dict:
    """Generate the currently validated utensil-grip design as an STL artifact.

    This tool reads the deterministic parameters created by validate_design(),
    invokes OpenSCAD, inspects the mesh, stores the STL through the configured
    ADK artifact service, and updates the current design in session state.
    """
    params = tool_context.state.get("validated_design")
    if not params:
        return {
            "status": "error",
            "error": "No validated design is available. Call validate_design first.",
        }

    design_version = int(tool_context.state.get("pending_design_version", 1))
    session_id = tool_context.session.id
    temp_dir = Path(tempfile.gettempdir()) / "arthistics"
    temp_dir.mkdir(parents=True, exist_ok=True)
    output_path = temp_dir / f"arthistics-{session_id}-v{design_version}.stl"

    result = await asyncio.to_thread(_run_openscad, params, output_path)
    if result.get("status") != "success":
        return result

    stl_bytes = output_path.read_bytes()
    artifact_key = f"designs/grip-sleeve-v{design_version}.stl"
    artifact_version = await tool_context.save_artifact(
        artifact_key,
        types.Part.from_bytes(data=stl_bytes, mime_type="model/stl"),
    )

    tool_context.state["current_design_version"] = design_version
    tool_context.state["current_design"] = params
    tool_context.state["current_design_artifact_key"] = artifact_key
    tool_context.state["current_design_artifact_version"] = artifact_version

    try:
        output_path.unlink(missing_ok=True)
    except OSError:
        pass

    return {
        "status": "success",
        "design_version": design_version,
        "artifact_key": artifact_key,
        "artifact_version": artifact_version,
        "design": params,
        "mesh": result.get("mesh", {}),
    }
