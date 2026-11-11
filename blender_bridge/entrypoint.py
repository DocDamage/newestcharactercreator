"""Blender-only job entrypoint, isolated from the desktop process.

This is real bpy integration code, NOT yet validated with Blender 5.3 + MPFB.
Only these explicit operations are permitted: inspect_environment, inspect_character,
create_human. Other operations fail without executing arbitrary user code.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import traceback

import bpy

PROTOCOL_VERSION = 1
OPERATIONS = {"inspect_environment", "inspect_character", "create_human"}


def arguments() -> argparse.Namespace:
    extra = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    return parser.parse_args(extra)


def member(root: Path, path: str) -> Path:
    if not isinstance(path, str) or not path or "\\" in path or ":" in path or path.startswith("/"):
        raise ValueError("Only project-relative paths are accepted")
    if any(part in ("..", ".", "") for part in path.split("/")):
        raise ValueError("Unsafe project-relative path")
    resolved = (root / path).resolve(strict=False)
    if not resolved.is_relative_to(root.resolve(strict=True)):
        raise ValueError("Path escapes isolated job workspace")
    return resolved


def mpfb_status() -> dict:
    try:
        operator = bpy.ops.mpfb.create_human
        operator.get_rna_type()
        return {"registered": True, "poll": bool(operator.poll())}
    except Exception as exc:
        return {"registered": False, "error": f"{type(exc).__name__}: {exc}"}


def inspect_environment(_: dict, __: Path) -> dict:
    return {"blender_version": bpy.app.version_string,
            "blender_version_tuple": list(bpy.app.version), "mpfb_operator": mpfb_status()}


def inspect_character(job: dict, root: Path) -> dict:
    source = member(root, job["input_project"])
    if not source.is_file() or source.suffix.lower() != ".blend":
        raise ValueError("Staged input .blend not found")
    bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if not meshes or sum(len(o.data.vertices) for o in meshes) <= 100:
        raise RuntimeError("Insufficient 3D mesh geometry")
    return {"blender_version": bpy.app.version_string,
            "mesh_count": len(meshes), "vertex_count": sum(len(o.data.vertices) for o in meshes),
            "armatures": [{"name": a.name, "bone_count": len(a.data.bones)}
                          for a in bpy.data.objects if a.type == "ARMATURE"],
            "shape_keys": {m.name: ([key.name for key in m.data.shape_keys.key_blocks]
                                    if m.data.shape_keys else []) for m in meshes}}


def create_human(_: dict, root: Path) -> dict:
    # MPFB supports a create_human operator in its API documentation. Its
    # background context and Blender 5.3 compatibility MUST be tested on PC.
    status = mpfb_status()
    if not status.get("registered"):
        raise RuntimeError(f"MPFB operator unavailable: {status.get('error')}")
    if not status.get("poll"):
        raise RuntimeError("MPFB create_human.poll() is false in this Blender context")
    existing = {obj.as_pointer() for obj in bpy.data.objects if obj.type == "MESH"}
    operation = bpy.ops.mpfb.create_human()
    if "FINISHED" not in operation:
        raise RuntimeError(f"MPFB create_human returned {operation}, not FINISHED")
    created = [o for o in bpy.data.objects if o.type == "MESH" and o.as_pointer() not in existing]
    if not created or max(len(o.data.vertices) for o in created) <= 100:
        raise RuntimeError("MPFB did not produce a substantial new human mesh")
    path = member(root, "generated_human.blend")
    bpy.ops.wm.save_as_mainfile(filepath=str(path))
    if not path.is_file() or path.stat().st_size < 16:
        raise RuntimeError("Generated project was not saved")
    return {"blender_version": bpy.app.version_string,
            "staged_blend": "generated_human.blend", "bytes": path.stat().st_size,
            "created_meshes": [{"name": o.name, "vertex_count": len(o.data.vertices)} for o in created],
            "armatures": [o.name for o in bpy.data.objects if o.type == "ARMATURE"],
            "verified_reopen": False}


def main() -> int:
    args = arguments()
    root = args.workspace.resolve(strict=True)
    request = args.request.resolve(strict=True)
    result = args.result.resolve(strict=False)
    if not request.is_relative_to(root) or not result.is_relative_to(root):
        raise SystemExit("Job paths must remain in isolated workspace")
    data = json.loads(request.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"protocol_version", "job_id", "operation", "input_project", "options"}:
        raise SystemExit("Invalid request schema")
    if type(data["protocol_version"]) is not int or data["protocol_version"] != PROTOCOL_VERSION:
        raise SystemExit("Unsupported request version")
    import uuid
    uuid.UUID(data["job_id"])
    operation = data["operation"]
    if operation not in OPERATIONS:
        raise SystemExit("Unknown operation")
    reply = {"protocol_version": PROTOCOL_VERSION, "job_id": data["job_id"],
             "operation": operation, "status": "error", "details": {}, "error": "Unknown error"}
    try:
        action = {"inspect_environment": inspect_environment,
                  "inspect_character": inspect_character,
                  "create_human": create_human}[operation]
        reply["details"] = action(data, root)
        reply["status"] = "ok"
        reply["error"] = None
    except Exception as exc:
        reply["error"] = f"{type(exc).__name__}: {exc}"
        reply["details"] = {"traceback_tail": traceback.format_exc()[-5000:]}
    result.write_text(json.dumps(reply, indent=2), encoding="utf-8")
    return 0 if reply["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
