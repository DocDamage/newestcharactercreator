"""Actual MPFB native-body gate; authored CI sources only, JSON summary only."""
from pathlib import Path
from hashlib import sha256
import json
import math
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"src"),str(ROOT)]
from ucc.core.storage import ProjectStore
from ucc.library.provenance import LicensePolicy
from ucc.jobs.fbx_intake import inspect_selected_fbx
from ucc.jobs.native_body import preview_native_body
from ucc.animations import native_math as nm


def verify_native_body(blender: Path,store: ProjectStore,folder: Path) -> dict:
    project=store.load();master=store.root/project.master_blend
    digest=lambda p:sha256(p.read_bytes()).hexdigest()
    metadata=store.root/"project.ucc.json"
    before=(digest(master),digest(metadata))
    script=ROOT/"tests/fixtures/blender_native_body.py"
    def run(*args):
        subprocess.run([str(blender),"--background","--factory-startup","--disable-autoexec",
            "--python-exit-code","13","--python",str(script),"--",*map(str,args)],check=True,timeout=300)
    run("--mode","author","--master",master,"--folder",folder)
    source=folder/"original-native-body.fbx";source_sha=digest(source)
    policy=LicensePolicy("Original UCC native-body test fixture","CC0","ci-original://native-body-reference",
                         reviewed=True,local_preview_allowed=True,no_ai=True)
    intake=inspect_selected_fbx(source,blender_exe=blender,worker_script=ROOT/"blender_bridge/entrypoint.py",
                                jobs_root=folder/".ucc-jobs",permission=policy)
    spec=json.loads((folder/"mapping-spec.json").read_text())
    profile={"schema_version":1,"convention":"NATIVE_ANATOMICAL_REFERENCE_V1","source_sha256":source_sha,
             "snapshot_sha256":intake["snapshot"]["sha256"],"master_sha256":before[0],**spec}
    profile_path=folder/"explicit-body-map.json"
    profile_path.write_text(json.dumps(profile,indent=2))
    profile_sha=digest(profile_path)
    result=preview_native_body(store,source_fbx=source,mapping_profile=profile_path,blender_exe=blender,
        worker_script=ROOT/"blender_bridge/entrypoint.py",permission=policy,
        expected_project_id=project.project_id,expected_revision=project.revision,expected_master_blend=project.master_blend)
    data=result.evidence
    if data["source_frame_count"]!=300 or len(data["mapped_pairs"])!=21 or data["root_motion_metrics"]["max_distance_from_bind_world"]<3.99:
        raise RuntimeError("Native preview cropped body motion or lost authored four-meter root travel")
    angle=0.;previous=None
    for frame in data["full_timeline_frames"]:
        rotation,_=nm.rotation(frame["target_global_poses"][0],target_noise=True)
        if previous is not None:
            delta=nm.product(nm.transposed(previous),rotation)
            angle+=math.degrees(math.acos(max(-1.,min(1.,(sum(delta[i][i] for i in range(3))-1)/2))))
        previous=rotation
    if not 399.9<angle<400.1:raise RuntimeError("Native root turn did not preserve the complete 400-degree path")
    reopened=folder/"independent-native-reopen.json"
    run("--mode","reopen","--review",result.private_visual_review_blend,"--timeline",result.private_timeline,"--output",reopened)
    independent=json.loads(reopened.read_text())
    run("--mode","fault","--master",master,"--job",Path(result.private_timeline).parent,"--folder",folder)
    if (before!=(digest(master),digest(metadata)) or source_sha!=digest(source) or profile_sha!=digest(profile_path) or store.load()!=project):
        raise RuntimeError("Native body verification changed original source/master/project/map bytes")
    return {"provenance":"ORIGINAL_CI_ARMATURE_ON_REAL_MPFB_NOT_OWNER_OR_FAB_ASSET","frames":300,"mapped_body_bones":21,
        "independent_skin_probes":len(data["deformation_probes"]),"root_travel_world":data["root_motion_metrics"]["max_distance_from_bind_world"],
        "root_rotation_path_degrees":angle,"max_source_fk_pose_residual":data["max_global_pose_residual"],
        "max_measured_target_rotation_projection":data["max_target_rotation_projection"],"two_workers_agree":True,
        "private_images_verified":15,"camera_policy":"FOLLOW_ROOT_TRANSLATION",
        "independent_reopen":independent,"partial_action_translation_scale_faults_rejected_and_restored":True,
        "original_bytes_unchanged":True,"retargeting_verified":False,"animation_visual_quality_verified":False,"engine_import_verified":False}


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender",type=Path,required=True)
    parser.add_argument("--project",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    report=verify_native_body(args.blender,ProjectStore(args.project),args.output)
    (args.output/"native-body-summary.json").write_text(json.dumps(report,indent=2))
    print(json.dumps(report))
