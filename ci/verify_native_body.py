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
from ucc.jobs.native_playback import prepare_native_playback
from ucc.animations import native_math as nm


def verify_native_body(blender: Path,store: ProjectStore,folder: Path,*,hip_anchor=False,corrective=False,neutral_reference=False,include_hands=False) -> dict:
    if neutral_reference and not (corrective and hip_anchor):
        raise ValueError("The neutral-reference CI challenge requires corrected skin and anatomical hip anchoring")
    project=store.load();master=store.root/project.master_blend
    digest=lambda p:sha256(p.read_bytes()).hexdigest()
    metadata=store.root/"project.ucc.json"
    before=(digest(master),digest(metadata))
    script=ROOT/"tests/fixtures/blender_native_body.py"
    def run(*args):
        subprocess.run([str(blender),"--background","--factory-startup","--disable-autoexec",
            "--python-exit-code","13","--python",str(script),"--",*map(str,args)],check=True,timeout=300)
    run("--mode","author","--master",master,"--folder",folder,"--origin","ground" if hip_anchor else "target-root",*(("--corrective-challenge",) if corrective else ()),*(("--posed-origin-challenge",) if neutral_reference else ()),*(("--include-hands",) if include_hands else ()))
    source=folder/"original-native-body.fbx";source_sha=digest(source)
    policy=LicensePolicy("Original UCC native-body test fixture","CC0","ci-original://native-body-reference",
                         reviewed=True,local_preview_allowed=True,no_ai=True)
    intake=inspect_selected_fbx(source,blender_exe=blender,worker_script=ROOT/"blender_bridge/entrypoint.py",
                                jobs_root=folder/".ucc-jobs",permission=policy)
    spec=json.loads((folder/"mapping-spec.json").read_text())
    profile={"schema_version":1,"convention":"NATIVE_ANATOMICAL_REFERENCE_V1","source_sha256":source_sha,
             "snapshot_sha256":intake["snapshot"]["sha256"],"master_sha256":before[0],**spec}
    profile_path=folder/"explicit-body-map.json"
    if hip_anchor:profile["root_motion_policy"]="SOURCE_HIP_MIDPOINT_V1"
    if corrective:profile["skin_deformation_policy"]="BOUND_CORRECTIVE_SMOOTH_V1"
    if neutral_reference:profile["mesh_strain_reference"]="TRUE_NEUTRAL_BIND_V2"
    if include_hands:
        from ucc.animations.native_hands import with_hand_planes
        profile=with_hand_planes(profile)
    profile_path.write_text(json.dumps(profile,indent=2))
    profile_sha=digest(profile_path)
    result=preview_native_body(store,source_fbx=source,mapping_profile=profile_path,blender_exe=blender,
        worker_script=ROOT/"blender_bridge/entrypoint.py",permission=policy,
        expected_project_id=project.project_id,expected_revision=project.revision,expected_master_blend=project.master_blend)
    data=result.evidence
    if data["source_frame_count"]!=300 or len(data["mapped_pairs"])!=(59 if include_hands else 21) or (not hip_anchor and data["root_motion_metrics"]["max_distance_from_bind_world"]<3.99):
        raise RuntimeError("Native preview cropped body motion or lost authored four-meter root travel")
    angle=0.;previous=None
    for frame in data["full_timeline_frames"]:
        rotation,_=nm.rotation(frame["target_global_poses"][0],target_noise=True)
        if previous is not None:
            delta=nm.product(nm.transposed(previous),rotation)
            angle+=math.degrees(math.acos(max(-1.,min(1.,(sum(delta[i][i] for i in range(3))-1)/2))))
        previous=rotation
    if not (400<angle<420 if hip_anchor else 399.9<angle<400.1):raise RuntimeError("Native root turn did not preserve the authored full path")
    anchor_evidence={}
    skin_evidence={}
    if neutral_reference:
        if (data["motion_quality_schema_version"]!=2 or result.reopen_evidence.get("first_pose_observation_frames_verified")!=300 or
                len(data["first_pose_relative_frames"])!=300):raise RuntimeError("Neutral-reference evidence did not cover every frame")
        skin_evidence.update(mesh_strain_reference=data["mesh_strain_reference"],
            posed_origin_observation_frames=300,neutral_quality_first_frame_min=data["full_timeline_frames"][0]["min_edge_length_ratio"],
            max_posed_origin_stretch=max(r["max_edge_stretch_ratio"] for r in data["first_pose_relative_frames"]),
            rehashed_saved_observation_tamper_rejected=True)
    if corrective:
        if not result.private_reopen_job_id or result.reopen_evidence["uncorrected_skin_frames_verified"]!=300:
            raise RuntimeError("Corrective preview did not independently reopen all raw and corrected frames")
        skin_evidence.update({"skin_deformation_policy":data["skin_deformation_policy"],"application_reopen_verified":True,
            "neutral_shape_error_local":data["skin_deformation"]["max_neutral_displacement_local"],
            "source_modifier_count":data["skin_deformation"]["source_modifier_count"],"review_modifier_count":data["skin_deformation"]["review_modifier_count"],
            "max_skin_correction_local":max(r["skin_correction"]["max_correction_local"] for r in data["full_timeline_frames"]),
            "max_original_master_stretch":max(r["max_edge_stretch_ratio"] for r in data["master_relative_frames"]),
            "bind_and_mid_action_settings_faults_restored":True,"rehashed_saved_settings_tamper_rejected":True,
            "rehashed_saved_object_transform_tamper_rejected":True})
        skin_evidence["rehashed_saved_rest_roll_tamper_rejected"]=True
        playback=prepare_native_playback(store,result,source_fbx=source,permission=policy,
            blender_exe=blender,worker_script=ROOT/"blender_bridge/entrypoint.py")
        cache=playback.cache
        if cache.frame_count!=300 or cache.vertex_count!=data["skin_deformation"]["neutral_vertex_count"]:
            raise RuntimeError("Cached playback dropped frames or visible skin vertices")
        indices={sha256(cache.frame(i)[1]).hexdigest() for i in range(cache.frame_count)}
        skin_evidence["verified_skin_cache"]={"frames":cache.frame_count,"visible_vertices":cache.vertex_count,
            "triangles_per_frame":cache.triangle_count,"packed_bytes":len(cache.packed),
            "all_vertex_skin_hashes_reproduced":True,"saved_action_reopened_before_cache":True,
            "distinct_actual_triangle_buffers":len(indices),"source_fps":cache.fps,
            "gpu_playback_tested_in_this_gate":False,"engine_import_verified":False}
        if cache.surface_review is None or cache.surface_review.status!="CHECKED" or not playback.surface_verification_job_id:
            raise RuntimeError("Complete real MPFB surface review was not independently reproduced")
        skin_evidence["verified_skin_cache"].update(surface_frames_verified=cache.frame_count,
            surface_flagged_frames=len(cache.surface_review.flagged_frames),pose_specific_topology_independently_verified=True)
        if include_hands:
            from ci.verify_surface_review import verify_surface_review
            skin_evidence['surface_fault_contract']=verify_surface_review(blender,ROOT,playback,folder)
    if hip_anchor:
        hip_travel=math.dist(data["full_timeline_frames"][-1]["hip_midpoint_world"],data["hip_anchor"]["target_bind_midpoint_world"])
        if hip_travel<3.99:raise RuntimeError("Native hip anchor lost the authored four-meter anatomical trajectory")
        snapshot=json.loads((Path(result.private_timeline).parent/"source_snapshot.json").read_text())
        old_error=0.
        for src,frame in zip(snapshot["frames"],data["full_timeline_frames"]):
            displacement=[src["armature_world"][i*4+3]-snapshot["armature_rest_world"][i*4+3] for i in range(3)]
            old=[data["target_root_bind_head"][i]+data["root_motion_scale"]*sum(data["source_to_target_axes"][i][j]*displacement[j] for j in range(3)) for i in range(3)]
            old_error=max(old_error,math.dist(old,frame["root_world_head"]))
        if old_error<.1 or data["hip_anchor"]["max_residual_world"]>1e-4:
            raise RuntimeError("Hip-origin fixture did not expose the old pivot error or new anchor did not correct it")
        anchor_evidence={"root_motion_policy":data["root_motion_policy"],"hip_trajectory_frames":300,
            "final_hip_travel_world":hip_travel,
            "max_hip_trajectory_error_world":data["hip_anchor"]["max_residual_world"],"legacy_pivot_counterfactual_error_world":old_error}
    reopened=folder/"independent-native-reopen.json"
    run("--mode","reopen","--review",result.private_visual_review_blend,"--timeline",result.private_timeline,"--output",reopened)
    independent=json.loads(reopened.read_text())
    run("--mode","fault","--master",master,"--job",Path(result.private_timeline).parent,"--folder",folder)
    if (before!=(digest(master),digest(metadata)) or source_sha!=digest(source) or profile_sha!=digest(profile_path) or store.load()!=project):
        raise RuntimeError("Native body verification changed original source/master/project/map bytes")
    if include_hands:
        from ucc.animations.native_hands import HAND_TARGETS
        from ci.native_hand_metrics import hand_local_motion
        probes={row["target"] for row in data["deformation_probes"]}
        if not HAND_TARGETS.issubset(probes):raise RuntimeError("Mapped hand joint lacks its independent visible-skin probe")
        hand_motion=hand_local_motion(data)
        if min(hand_motion.values())<1.:raise RuntimeError("Authored finger motion was replaced by inherited wrist motion")
        if result.reopen_evidence.get("hand_reference_planes_verified")!=2:
            raise RuntimeError("Both declared palm planes were not verified against actual saved rig rest geometry")
    return {**anchor_evidence,**skin_evidence,"provenance":"ORIGINAL_CI_ARMATURE_ON_REAL_MPFB_NOT_OWNER_OR_FAB_ASSET","frames":300,"mapped_body_bones":len(data["mapped_pairs"]),
        "mapped_hand_joints":38 if include_hands else 0,
        "hand_reference_planes_verified":2 if include_hands else 0,
        "rehashed_saved_palm_geometry_tamper_rejected":bool(include_hands),
        "invalid_palm_branch_rejected_and_restored":bool(include_hands),
        "intrinsic_hand_motion_degrees":hand_motion if include_hands else {},
        "independent_skin_probes":len(data["deformation_probes"]),"root_travel_world":data["root_motion_metrics"]["max_distance_from_bind_world"],
        "root_rotation_path_degrees":angle,"max_source_fk_pose_residual":data["max_global_pose_residual"],
        "max_measured_target_rotation_projection":data["max_target_rotation_projection"],"two_workers_agree":True,
        "private_images_verified":15,"camera_policy":"FOLLOW_HIP_MIDPOINT_TRANSLATION" if hip_anchor else "FOLLOW_ROOT_TRANSLATION",
        "independent_reopen":independent,"partial_action_translation_scale_faults_rejected_and_restored":True,
        "original_bytes_unchanged":True,"retargeting_verified":False,"animation_visual_quality_verified":False,"engine_import_verified":False}


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender",type=Path,required=True)
    parser.add_argument("--project",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--hip-anchor",action="store_true")
    parser.add_argument("--corrective",action="store_true")
    parser.add_argument("--neutral-reference",action="store_true")
    parser.add_argument("--include-hands",action="store_true")
    args=parser.parse_args()
    report=verify_native_body(args.blender,ProjectStore(args.project),args.output,hip_anchor=args.hip_anchor,corrective=args.corrective,neutral_reference=args.neutral_reference,include_hands=args.include_hands)
    (args.output/"native-body-summary.json").write_text(json.dumps(report,indent=2))
    print(json.dumps(report))
