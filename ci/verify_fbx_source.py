"""Actual Blender native FBX intake gate using original non-shipping fixtures."""
from hashlib import sha256
from pathlib import Path
import json
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from ucc.jobs.fbx_intake import inspect_selected_fbx
from ucc.jobs.runner import WorkerFailure
from ucc.library.provenance import LicensePolicy


def verify_fbx_source(blender: Path, folder: Path) -> dict:
    subprocess.run([str(blender),"--background","--factory-startup","--disable-autoexec",
                    "--python-exit-code","13","--python",str(ROOT/"tests/fixtures/blender_fbx_contract.py"),
                    "--",str(folder)],check=True,timeout=180)
    source=folder/"original-synthetic.fbx"
    digest=sha256(source.read_bytes()).hexdigest()
    policy=LicensePolicy("Original UCC synthetic test fixture","CC0","ci-original://native-fbx-contract",
                         reviewed=True,local_preview_allowed=True,no_ai=True)
    options={"blender_exe":blender,"worker_script":ROOT/"blender_bridge/entrypoint.py",
             "jobs_root":folder/".ucc-jobs","permission":policy}
    result=inspect_selected_fbx(source,**options)
    data=json.loads(Path(result["private_snapshot"]).read_text(encoding="utf-8"))
    if result["frame_count"]!=300 or result["root_count"]!=2 or result["bone_count"]!=3:
        raise RuntimeError("Native FBX intake dropped roots/bones or truncated the complete Action")
    def world_origin(row):
        world,pose=row["armature_world"],row["poses"][0]
        return [sum(world[i*4+j]*pose[j*4+3] for j in range(3))+world[i*4+3] for i in range(3)]
    a,b=world_origin(data["frames"][0]),world_origin(data["frames"][-1])
    distance=sum((x-y)**2 for x,y in zip(a,b))**.5
    if abs(distance-.897) > 1e-4 or result["fps"]!=30.:
        raise RuntimeError("FBX native root displacement/timing was not preserved")
    bad=folder/"ambiguous-synthetic.fbx"
    bad_hash=sha256(bad.read_bytes()).hexdigest()
    try:
        inspect_selected_fbx(bad,**options)
    except WorkerFailure as exc:
        if "unambiguous bound Action" not in str(exc):raise
    else:
        raise RuntimeError("Ambiguous FBX takes were silently selected")
    image_source=folder/"image-reference-synthetic.fbx"
    image_source_hash=sha256(image_source.read_bytes()).hexdigest()
    try:
        inspect_selected_fbx(image_source,**options)
    except WorkerFailure as exc:
        if "image resources" not in str(exc):raise
    else:
        raise RuntimeError("FBX image resource loading was not denied")
    if (sha256(source.read_bytes()).hexdigest()!=digest or sha256(bad.read_bytes()).hexdigest()!=bad_hash or
            sha256(image_source.read_bytes()).hexdigest()!=image_source_hash):
        raise RuntimeError("FBX source originals changed during successful/failed intake")
    return {"provenance":"ORIGINAL_SYNTHETIC_NOT_HUMANOID_NOT_FAB","frame_count":300,"root_count":2,"bone_count":3,
            "fps":30.,"root_world_displacement":distance,"two_workers_agree":True,"original_bytes_unchanged":True,
            "ambiguous_takes_rejected":True,"image_resources_rejected":True,
            "retargeting_verified":False,"animation_visual_quality_verified":False}


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(verify_fbx_source(args.blender,args.output)))
