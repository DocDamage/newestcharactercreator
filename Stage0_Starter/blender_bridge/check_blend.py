"""Run inside Blender on a .blend, verifying saved data after a fresh load."""
import json
import sys
from pathlib import Path
import bpy

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if not args:
    raise SystemExit("Expected -- result.json")
output = Path(args[0])
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
report = {
    "status": "ok" if meshes and sum(len(o.data.vertices) for o in meshes) > 100 else "error",
    "blender_version": bpy.app.version_string,
    "blend_file": bpy.data.filepath,
    "mesh_count": len(meshes),
    "vertex_count": sum(len(o.data.vertices) for o in meshes),
    "armature_count": len([o for o in bpy.data.objects if o.type == "ARMATURE"]),
}
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, indent=2), encoding="utf-8")
if report["status"] != "ok":
    raise SystemExit(2)
