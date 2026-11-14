"""Every-frame native skin checks with rigid root travel measured separately."""
from hashlib import sha256
import math
import struct

from blender_bridge.pose_deformation import _evaluated_vertices, _movement
from blender_bridge.motion_quality import EdgeStrain
from blender_bridge.bvh_review_timeline import evaluated_edges
from blender_bridge.fbx_source import pose_digest


def evaluate_native_timeline(bpy,human,rig,source,expected,pairs,world,root_bind_head,
                             bind_points,rotation_reader,review_path,*,hip_anchor=None):
    from mathutils import Vector
    scene=bpy.context.scene
    prior=(scene.frame_start,scene.frame_end,rig.show_in_front,scene.frame_current)
    frames=len(expected)
    before=previous=None
    rows,bind_rows=[],[]
    bind_strain=EdgeStrain(bind_points,evaluated_edges(bpy,human))
    diagonal=sum((max(p[i] for p in bind_points)-min(p[i] for p in bind_points))**2 for i in range(3))**.5
    if not .01<diagonal<100000: raise ValueError("Invalid native target skin bounds")
    root_name=pairs[0]["target"]
    root_metrics={"frames_measured":frames,"max_speed_world":0.,"max_speed_frame":1,
                  "max_step_distance_world":0.,"max_distance_from_bind_world":0.}
    maximum_residual=0.
    previous_root=None
    first_strain=None
    max_hip_error=0.
    local_world_inverse=human.matrix_world.inverted().to_3x3()
    try:
        scene.frame_start,scene.frame_end=1,frames
        for frame,want in enumerate(expected,1):
            scene.frame_set(frame)
            points,digest=_evaluated_vertices(bpy,human)
            root_head=(world@rig.pose.bones[root_name].matrix).translation
            travel=root_head-Vector(root_bind_head)
            distance=(root_head-previous_root).length if previous_root is not None else 0.
            speed=distance*source["fps"]
            if speed>20: raise ValueError("Native rigid root exceeds generic 20 world-meters/second safety bound")
            root_metrics["max_step_distance_world"]=max(root_metrics["max_step_distance_world"],distance)
            root_metrics["max_distance_from_bind_world"]=max(root_metrics["max_distance_from_bind_world"],travel.length)
            if speed>root_metrics["max_speed_world"]: root_metrics["max_speed_world"],root_metrics["max_speed_frame"]=speed,frame
            previous_root=root_head.copy()
            offset=local_world_inverse@travel
            deformed=tuple(tuple(p[i]-offset[i] for i in range(3)) for p in points)
            edges=evaluated_edges(bpy,human)
            if before is None:
                before=deformed
                first_strain=EdgeStrain(points,edges)
            moving,maximum=_movement(before,deformed)
            adjacent=_movement(previous,deformed)[1] if previous is not None else 0.
            bind_maximum=_movement(bind_points,deformed)[1]
            if maximum>diagonal*1.5 or bind_maximum>diagonal*1.5 or adjacent>diagonal*.8:
                raise ValueError("Native skin has extreme/discontinuous deformation after separating root travel")
            matrices=[];residual=0.
            for row in pairs:
                name=row["target"]
                actual=world@rig.pose.bones[name].matrix
                rotation=rotation_reader(actual)
                residual=max(residual,max(abs(rotation[i][j]-want[name]["rotation"][i][j]) for i in range(3) for j in range(3)),
                             (actual.translation-Vector(want[name]["head"])).length)
                matrices.append([float(v) for line in actual for v in line])
            if residual>1e-4: raise ValueError("Actual native target FK differs from calibrated source pose")
            maximum_residual=max(maximum_residual,residual)
            deformation_hash=sha256()
            for point in deformed: deformation_hash.update(struct.pack("<qqq",*(round(v*1000000) for v in point)))
            rows.append({"frame":frame,"source_frame":source["first_frame"]+frame-1,
                "evaluated_sha256":digest,"evaluated_vertex_count":len(points),"deformation_sha256":deformation_hash.hexdigest(),
                "moved_vertices":moving,"max_displacement_local":maximum,"adjacent_max_displacement_local":adjacent,
                "max_bind_displacement_local":bind_maximum,**first_strain.measure(points,edges,frame),
                "root_world_head":list(root_head),"root_speed_world":speed,
                "target_global_poses":matrices,"target_pose_sha256":pose_digest([float(v) for line in world for v in line],matrices),
                "global_pose_residual":residual})
            if hip_anchor is not None:
                points_hip=[world@rig.pose.bones[name].matrix.translation for name in hip_anchor["targets"]]
                center=[sum(p[i] for p in points_hip)/2 for i in range(3)]
                error=math.dist(center,hip_anchor["expected"][frame-1])
                if error>1e-4:raise ValueError("Actual native hip trajectory differs from source joint heads")
                rows[-1]["hip_midpoint_world"]=center
                max_hip_error=max(max_hip_error,error)
            bind_rows.append({"frame":frame,**bind_strain.measure(points,edges,frame)})
            previous=deformed
        if len({r["deformation_sha256"] for r in rows})<3 or sum(r["moved_vertices"]>=16 for r in rows[1:])<2:
            raise ValueError("Native source did not measurably articulate the skin beyond rigid root travel")
        if review_path.name!="review_motion.blend" or review_path.is_symlink() or review_path.exists():
            raise ValueError("Refuse unsafe/occupied native Action review output")
        scene.frame_set(1);rig.show_in_front=True
        result=bpy.ops.wm.save_as_mainfile(filepath=str(review_path),compress=False,copy=True)
        if "FINISHED" not in result or not review_path.is_file() or not 10000<review_path.stat().st_size<=512*1024*1024:
            raise ValueError("Native private Action copy was not saved correctly")
        h=sha256()
        with review_path.open("rb") as stream:
            for chunk in iter(lambda:stream.read(1024*1024),b""):h.update(chunk)
        anchor_evidence={} if hip_anchor is None else {"root_motion_policy":"SOURCE_HIP_MIDPOINT_V1","hip_anchor":{
            "source_bones":hip_anchor["sources"],"target_bones":hip_anchor["targets"],
            "source_bind_midpoint_world":hip_anchor["source_bind_midpoint_world"],
            "target_bind_midpoint_world":hip_anchor["target_bind_midpoint_world"],
            "frames_measured":frames,"max_residual_world":max_hip_error}}
        return {**anchor_evidence,"motion_quality_schema_version":1,"mesh_edge_strain":first_strain.report(),
                "bind_edge_strain":bind_strain.report(),"bind_relative_frames":bind_rows,
                "full_timeline_frames":rows,"root_motion_metrics":root_metrics,
                "deformation_reference":"ROOT_TRANSLATION_REMOVED",
                "model_baseline_diagonal_local":diagonal,"max_global_pose_residual":maximum_residual,
                "max_adjacent_mesh_step_local":max(r["adjacent_max_displacement_local"] for r in rows),
                "visual_review_blend":{"name":review_path.name,"bytes":review_path.stat().st_size,"sha256":h.hexdigest()},
                "visual_review_artifact_created":True,"animation_visual_quality_verified":False,"joint_twist_visual_quality_verified":False}
    finally:
        scene.frame_start,scene.frame_end,rig.show_in_front=prior[:3]
        scene.frame_set(prior[3])
