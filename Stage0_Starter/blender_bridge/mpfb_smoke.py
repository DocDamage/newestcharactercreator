"""Create a *real* MPFB human and built-in rig inside Blender, then save it.

The official MPFB HumanService is used instead of the UI operator because the
latter may have a false poll() in Blender background mode. This does NOT enable
or install the extension. It must be tested on a machine with Blender + MPFB.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

import bpy

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from blender_bridge.mpfb_service import create_human_with_rig, locate_human_service


def parse_args() -> argparse.Namespace:
    raw = sys.argv
    script_args = raw[raw.index("--") + 1:] if "--" in raw else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--blend", required=True)
    return parser.parse_args(script_args)


def create_human(blend_path: Path) -> dict:
    service, module = locate_human_service()
    details = create_human_with_rig(bpy, service, "default")
    blend_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    if not blend_path.is_file() or blend_path.stat().st_size < 16:
        raise RuntimeError("MPFB human and rig were created but .blend was not saved")
    return {**details, "mpfb_service_module": module,
            "output_blend": str(blend_path), "output_bytes": blend_path.stat().st_size}


def main() -> None:
    args = parse_args()
    result_path = Path(args.output)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result = {"status": "error", "blender_version": bpy.app.version_string}
    try:
        result.update(create_human(Path(args.blend)))
        result["status"] = "ok"
    except Exception as error:
        result["error_type"] = type(error).__name__
        result["error"] = str(error)
        result["traceback"] = traceback.format_exc()[-6000:]
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("UCC_SMOKE_RESULT=" + json.dumps({"status": result["status"],
                                         "output": str(result_path),
                                         "error": result.get("error")}))
    if result["status"] != "ok":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
