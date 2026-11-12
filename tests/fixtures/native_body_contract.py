"""Non-shipping synthetic *boundary data*, never Blender/skin/asset evidence."""
from copy import deepcopy
from hashlib import sha256
import struct

from fixtures.fbx_snapshot_contract import IDENTITY
from blender_bridge.fbx_source import IMPORT_OPTIONS


def matrix(position):
    m=IDENTITY[:]
    for i,value in enumerate(position):m[i*4+3]=float(value)
    return m


def digest(world,poses):
    h=sha256()
    for m in [world,*poses]:h.update(struct.pack("<16q",*(round(x*1000000) for x in m)))
    return h.hexdigest()


def contract():
    names=[f"S{i:02}" for i in range(1,21)]
    positions=[[.1,0,1],[-.1,0,1],[0,0,1.7],[.6,0,1.2],[-.6,0,1.2],[.1,0,.05],[-.1,0,.05]]
    positions += [[.01*(i-6),0,1.05+.025*i] for i in range(13)]
    bones=[{"name":n,"parent":None,"head":p[:],"tail":[p[0],p[1]+.1,p[2]],"matrix":matrix(p)} for n,p in zip(names,positions)]
    for i in (5,6):
        bones[i]["tail"][1]=-.1
        bones[i]["matrix"][0]=bones[i]["matrix"][5]=-1.
    pairs=[{"source":"@ARMATURE","target":"T00","source_tip":None,"target_tip":None,"secondary":"BODY"}]
    pairs += [{"source":n,"target":f"T{i:02}","source_tip":None,"target_tip":None,"secondary":"UP"} for i,n in enumerate(names,1)]
    landmark_names=("left_hip","right_hip","head","left_hand","right_hand","left_foot","right_foot")
    landmarks={key:{"source":names[i],"target":f"T{i+1:02}"} for i,key in enumerate(landmark_names)}
    profile={"schema_version":1,"convention":"NATIVE_ANATOMICAL_REFERENCE_V1","source_sha256":"a"*64,
             "snapshot_sha256":"b"*64,"master_sha256":"c"*64,"pairs":pairs,"landmarks":landmarks}
    bindings={"source_sha256":"a"*64,"snapshot_sha256":"b"*64,"mapping_sha256":"d"*64,"master_sha256":"c"*64}
    source_frames=[];frames=[];bind=[]
    for frame in range(1,6):
        x=.01*(frame-1)
        w=matrix([x,0,0]);poses=[b["matrix"][:] for b in bones]
        source_frames.append({"frame":frame,"armature_world":w,"poses":poses,"pose_sha256":digest(w,poses)})
        actual=[matrix([x,0,1])]
        for bone in bones:
            pose=bone["matrix"][:];pose[3]+=x;actual.append(pose)
        frames.append({"frame":frame,"source_frame":frame,"evaluated_sha256":f"{frame:064x}",
            "deformation_sha256":f"{frame+20:064x}","evaluated_vertex_count":1000,"moved_vertices":0 if frame==1 else 50,
            "max_displacement_local":x,"max_bind_displacement_local":x,"adjacent_max_displacement_local":0. if frame==1 else .01,
            "min_edge_length_ratio":1.,"max_edge_stretch_ratio":1.,"target_global_poses":actual,
            "target_pose_sha256":digest(IDENTITY,actual),"global_pose_residual":0.,"root_world_head":[x,0.,1.],
            "root_speed_world":0. if frame==1 else .3})
        bind.append({"frame":frame,"min_edge_length_ratio":1.,"max_edge_stretch_ratio":1.})
    source={"schema_version":1,"convention":"BLENDER_FBX_ARMATURE_POSE_MATRICES_V1","source_sha256":"a"*64,
        "blender_version":"5.3.0","import_options":deepcopy(IMPORT_OPTIONS),"rest_import_options":{**IMPORT_OPTIONS,"use_anim":False},
        "armature_rest_world":IDENTITY[:],"action":"SYNTHETIC_BOUNDARY_ONLY_NOT_ANIMATION_PROOF","fps":30.,
        "first_frame":1,"last_frame":5,"bones":bones,"frames":source_frames,
        "retargeting_verified":False,"animation_visual_quality_verified":False,"engine_import_verified":False}
    rotation=[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]
    proofs=[]
    for index,pair in enumerate(pairs):
        row={"source":pair["source"],"target":pair["target"],"weighted_vertices":0 if index==0 else 100,
             "source_bind_rotation":deepcopy(rotation),"target_bind_rotation":deepcopy(rotation),"reference_rotation":deepcopy(rotation),
             "segment_alignment_residual":0.,"target_bind_projection":0.}
        if index:row.update(source_segment=[0.,.1,0.],target_segment=[0.,.1,0.],source_secondary=[0.,0.,1.],target_secondary=[0.,0.,1.])
        if index in (6,7):
            foot=[[-1.,0.,0.],[0.,-1.,0.],[0.,0.,1.]]
            row.update(source_bind_rotation=deepcopy(foot),target_bind_rotation=deepcopy(foot),reference_rotation=deepcopy(foot),
                       source_segment=[0.,-.1,0.],target_segment=[0.,-.1,0.])
        proofs.append(row)
    metrics=[{"bone":p["target"],"frames_measured":5,"max_swing_degrees":0.,"max_swing_frame":1,
              "max_twist_degrees":0.,"max_twist_frame":1,"max_step_degrees":0.,"max_step_frame":1} for p in pairs[1:]]
    mesh={"evaluated_edge_count":32,"measured_edge_count":32,"degenerate_baseline_edges_excluded":0,"evaluated_topology_sha256":"f"*64}
    action={"name":"review_motion.blend","bytes":12000,"sha256":"e"*64}
    data={"schema_version":1,"convention":profile["convention"],"bindings":bindings,"source_frame_count":5,"source_first_frame":1,
        "fps":30.,"mapped_pairs":pairs,"reference_proofs":proofs,"source_to_target_axes":rotation,"root_motion_scale":1.,
        "target_armature_world":IDENTITY[:],"target_root_bind_head":[0.,0.,1.],
        "neutral_bind_skin_sha256":"0"*64,"deformation_probes":[{"source":p["source"],"target":p["target"],"axis":"X","moved_vertices":50,"max_displacement_local":.1} for p in pairs[1:]],
        "target_anatomical_landmarks":{key:positions[i][:] for i,key in enumerate(landmark_names)},
        "max_global_pose_residual":0.,"max_source_translation_error_ratio":0.,"max_source_scale_error":0.,"max_target_rotation_projection":0.,
        "joint_motion_metrics":metrics,"max_bone_quaternion_step_degrees":{p["target"]:0. for p in pairs[1:]},
        "target_pose_environment_checked":True,"motion_quality_schema_version":1,"mesh_edge_strain":mesh,"bind_edge_strain":deepcopy(mesh),
        "bind_relative_frames":bind,"full_timeline_frames":frames,"model_baseline_diagonal_local":2.,"max_adjacent_mesh_step_local":.01,
        "deformation_reference":"ROOT_TRANSLATION_REMOVED","omitted_source_bones":[],"neutral_target_helpers":[],
        "root_motion_metrics":{"frames_measured":5,"max_speed_world":.3,"max_speed_frame":2,"max_step_distance_world":.01,
            "max_distance_from_bind_world":.04,"max_rotation_step_degrees":0.,"max_rotation_step_frame":1},
        "visual_review_blend":action,"visual_review_artifact_created":True,"animation_visual_quality_verified":False,
        "joint_twist_visual_quality_verified":False,"retargeting_verified":False,"engine_import_verified":False}
    report={"status":"REAL_NATIVE_FBX_BODY_MOTION_MEASURED","convention":profile["convention"],"bindings":bindings,
            "source_frame_count":5,"mapped_bone_count":len(pairs),"timeline":{"name":"target_timeline.json","bytes":1,"sha256":"0"*64},
            "visual_review_blend":action,"retargeting_verified":False,"animation_visual_quality_verified":False,"engine_import_verified":False}
    return data,report,source,profile,bindings
