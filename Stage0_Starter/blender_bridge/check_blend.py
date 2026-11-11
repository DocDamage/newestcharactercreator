"""Separate Blender-process check of the *saved* MPFB human and armature."""
import json
import sys
from pathlib import Path
import bpy

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if not args:
    raise SystemExit("Expected -- result.json")
output = Path(args[0])
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
rigs = [o for o in bpy.data.objects if o.type == "ARMATURE"]
vertices = sum(len(o.data.vertices) for o in meshes)
bones = sum(len(o.data.bones) for o in rigs)
report = {
    "status": "ok" if meshes and vertices > 100 and rigs and bones >= 5 else "error",
    "blender_version": bpy.app.version_string,
    "blend_file": bpy.data.filepath,
    "mesh_count": len(meshes),
    "vertex_count": vertices,
    "armature_count": len(rigs),
    "bone_count": bones,
    "armatures": [{"name": o.name, "bone_count": len(o.data.bones)} for o in rigs],
}
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, indent=2), encoding="utf-8")
if report["status"] != "ok":
    raise SystemExit(2)
