"""Native full-body FK experiment on private copies, with explicit bind alignment."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from blender_bridge.native_inputs import read_json, validate_source, validate_profile
from blender_bridge.native_reference import (
    CONVENTION, body_frame, target_reference, transport_global, check_mapping_hierarchy, RootRotation,
)
from blender_bridge.rest_calibration import multiply, transpose, validate_rotation, project_near_rotation
from blender_bridge.refit_revision import rig_fingerprint
from blender_bridge.pose_environment import validate_pose_environment
from blender_bridge.pose_deformation import _evaluated_vertices
from blender_bridge.motion_quality import JointMotion
from blender_bridge.native_timeline import evaluate_native_timeline
from blender_bridge.native_skin import probe_targets
from blender_bridge.native_anchor import POLICY as HIP_ANCHOR, midpoint, root_position, validate_target_chain
from blender_bridge.private_review_render import render_private_review


def _digest(path):
    h=sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()


def _rotation(matrix, target_projections=None):
    columns=[tuple(float(matrix[i][j]) for i in range(3)) for j in range(3)]
    scales=[sum(x*x for x in col)**.5 for col in columns]
    if min(scales)<1e-7 or max(scales)/min(scales)>1.0001:
        raise ValueError("Native retargeting does not drop nonuniform source scales")
    result=tuple(tuple(columns[j][i]/scales[j] for j in range(3)) for i in range(3))
    if target_projections is not None:
        result,_,correction=project_near_rotation(result)
        target_projections.append(correction)
    else:
        validate_rotation(result)
    return result, sum(scales)/3


def _record(path):
    return {"name":path.name,"bytes":path.stat().st_size,"sha256":_digest(path)}


def retarget_native(bpy: Any, root: Path, options: dict) -> dict:
    from mathutils import Matrix, Vector
    master=root/"candidate.blend"
    source_path,profile_path=root/"source_snapshot.json",root/"native_mapping.json"
    if master.is_symlink() or not master.is_file() or _digest(master)!=options["master_sha256"]:
        raise ValueError("Native target master SHA-256 differs")
    source=validate_source(read_json(source_path,options["snapshot_sha256"],64*1024*1024),options["source_sha256"])
    profile=validate_profile(read_json(profile_path,options["mapping_sha256"],64*1024),
                             options["source_sha256"],options["snapshot_sha256"],options["master_sha256"])
    pairs=profile["pairs"]
    def mat(values): return Matrix([values[i:i+4] for i in range(0,16,4)])
    bpy.ops.wm.open_mainfile(filepath=str(master),load_ui=False)
    humans=[o for o in bpy.data.objects if o.type=="MESH" and len(o.data.vertices)>100]
    rigs=[o for o in bpy.data.objects if o.type=="ARMATURE"]
    if len(humans)!=1 or len(rigs)!=1:
        raise ValueError("Native body target needs exactly one substantial human/armature")
    human,rig=humans[0],rigs[0]
    frames=len(source["frames"])
    if len(rig.data.bones)*frames>100000 or len(human.data.vertices)*frames>20000000:
        raise ValueError("Complete native target timeline exceeds bounded evaluation workload; no cropping")
    if rig.animation_data and (rig.animation_data.action or len(rig.animation_data.nla_tracks)):
        raise ValueError("Refuse to replace a target Action/NLA")
    for data in (human,human.data.shape_keys):
        animation=getattr(data,"animation_data",None)
        if animation and (animation.action or len(animation.nla_tracks) or len(animation.drivers)):
            raise ValueError("Animated target geometry is incompatible with native FK verification")
    validate_pose_environment(rig,human,[b.name for b in rig.pose.bones])
    before=rig_fingerprint(bpy,human)
    parents={b["name"]:b["parent"] or "@ARMATURE" for b in source["bones"]}
    parents["@ARMATURE"]=None
    target_parents={b.name:b.parent.name if b.parent else None for b in rig.data.bones}
    ordered=check_mapping_hierarchy(pairs,parents,target_parents)
    sw,tw=mat(source["armature_rest_world"]),rig.matrix_world.copy()
    tw_rotation,_=_rotation(tw)
    sw_rotation,sw_scale=_rotation(sw)
    rest={b["name"]:mat(b["matrix"]) for b in source["bones"]}
    indices={b["name"]:i for i,b in enumerate(source["bones"])}
    source_points={b["name"]:sw@Vector(b["head"]) for b in source["bones"]}
    target_points={b.name:tw@b.head_local for b in rig.data.bones}
    landmarks=profile["landmarks"]
    hip_anchor=profile.get("root_motion_policy")==HIP_ANCHOR
    source_hip_mid=midpoint([source_points[landmarks[k]["source"]] for k in ("left_hip","right_hip")])
    target_hip_mid=midpoint([target_points[landmarks[k]["target"]] for k in ("left_hip","right_hip")])
    if hip_anchor: validate_target_chain(rig,pairs,landmarks)
    def landmark(side,key): return (source_points if side=="source" else target_points)[landmarks[key][side]]
    sb,source_height=body_frame(*(tuple(landmark("source",k)) for k in ("left_hip","right_hip","head")))
    tb,target_height=body_frame(*(tuple(landmark("target",k)) for k in ("left_hip","right_hip","head")))
    axes=multiply(tb,transpose(sb));scale=target_height/source_height
    if not .25<=scale<=4:
        raise ValueError("Source/target body proportions are incompatible")
    for side,basis,height in (("source",sb,source_height),("target",tb,target_height)):
        middle=(landmark(side,"left_hip")+landmark(side,"right_hip"))/2
        x,z=Vector(tuple(row[0] for row in basis)),Vector(tuple(row[2] for row in basis))
        if (any((landmark(side,k)-middle).dot(x)*sign <= .02*height for k,sign in (("left_hand",1),("right_hand",-1),("left_foot",1),("right_foot",-1))) or
                any(not -2*height<(landmark(side,k)-middle).dot(z)<-.1*height for k in ("left_foot","right_foot")) or
                any(not -.5*height<(landmark(side,k)-middle).dot(z)<1.5*height for k in ("left_hand","right_hand"))):
            raise ValueError("Native anatomical landmark sides/heights are incompatible")
    references,source_rest,proofs={},{},[]
    target_projections=[]
    weighted={b.name:0 for b in rig.data.bones}
    groups={g.index:g.name for g in human.vertex_groups}
    for vertex in human.data.vertices:
        for group in vertex.groups:
            if group.weight>1e-5 and groups[group.group] in weighted: weighted[groups[group.group]]+=1
    for row in pairs:
        name,target=row["source"],row["target"]
        bind_rotation,_=_rotation(tw@rig.data.bones[target].matrix_local,target_projections)
        if name=="@ARMATURE":
            reference,residual,source_rotation=bind_rotation,0.,sw_rotation
            vectors={}
        else:
            if weighted[target]<16: raise ValueError("Mapped native target has too little real skin weight: "+target)
            source_tip=(source_points[row["source_tip"]] if row["source_tip"] else sw@Vector(source["bones"][indices[name]]["tail"]))
            target_tip=(target_points[row["target_tip"]] if row["target_tip"] else tw@rig.data.bones[target].tail_local)
            column=2 if row["secondary"]=="UP" else 1
            sign=1 if column==2 else -1
            source_secondary=tuple(sign*b[column] for b in sb)
            target_secondary=tuple(sign*b[column] for b in tb)
            if name in {landmarks[k]["source"] for k in ("left_foot","right_foot")}:
                for segment,basis in ((source_tip-source_points[name],sb),(target_tip-target_points[target],tb)):
                    forward=Vector(tuple(-b[1] for b in basis))
                    if segment.normalized().dot(forward)<.2:
                        raise ValueError("Foot anatomical tips face against the declared body forward axis")
            reference,residual=target_reference(tuple(source_tip-source_points[name]),tuple(target_tip-target_points[target]),
                                                source_secondary,target_secondary,axes,bind_rotation)
            vectors={"source_segment":list(source_tip-source_points[name]),"target_segment":list(target_tip-target_points[target]),
                     "source_secondary":source_secondary,"target_secondary":target_secondary}
            source_rotation,_=_rotation(sw@rest[name])
        references[target],source_rest[target]=reference,source_rotation
        proofs.append({"source":name,"target":target,"weighted_vertices":weighted[target],
                       "source_bind_rotation":source_rotation,"target_bind_rotation":bind_rotation,
                       "target_bind_projection":target_projections[-1],
                       "reference_rotation":reference,"segment_alignment_residual":residual,**vectors})
    preserved=[(b,b.matrix_basis.copy(),b.rotation_mode) for b in rig.pose.bones]
    scene=bpy.context.scene
    old=(scene.frame_current,scene.render.fps,scene.render.fps_base,rig.data.pose_position)
    action=None
    try:
        rig.data.pose_position="POSE"
        bind_points,bind_sha=_evaluated_vertices(bpy,human)
        probes=probe_targets(bpy,human,rig,pairs,bind_points,bind_sha)
        rig.animation_data_create()
        action=bpy.data.actions.new("UCC_PRIVATE_NATIVE_BODY_UNAPPROVED")
        rig.animation_data.action=action
        metrics={row["target"]:JointMotion(row["target"]) for row in pairs[1:]}
        root_rotation=RootRotation()
        by_target={row["target"]:row for row in pairs}
        scene.render.fps=round(source["fps"])
        scene.render.fps_base=scene.render.fps/source["fps"]
        expected=[]
        expected_hips=[]
        max_translation,max_scale=0.,0.
        for frame,row in enumerate(source["frames"],1):
            world=mat(row["armature_world"])
            _,world_scale=_rotation(world)
            max_scale=max(max_scale,abs(world_scale/sw_scale-1))
            computed,want={},{}
            poses={name:mat(row["poses"][i]) for name,i in indices.items()}
            for name in ordered:
                bone=rig.data.bones[name]
                kw={"parent_matrix":computed[bone.parent.name],"parent_matrix_local":bone.parent.matrix_local} if bone.parent else {}
                neutral=bone.convert_local_to_pose(Matrix.Identity(4),bone.matrix_local,**kw)
                if name not in by_target:
                    computed[name]=neutral
                    continue
                source_name=by_target[name]["source"]
                if source_name=="@ARMATURE": current=world
                else:
                    local_pose,local_rest=poses[source_name],rest[source_name]
                    parent=parents[source_name]
                    if parent!="@ARMATURE":
                        local_pose=poses[parent].inverted()@local_pose
                        local_rest=rest[parent].inverted()@local_rest
                    max_translation=max(max_translation,(local_pose.translation-local_rest.translation).length/(source_height/sw_scale))
                    max_scale=max(max_scale,max(abs(a/b-1) for a,b in zip(local_pose.to_scale(),local_rest.to_scale())))
                    current=world@poses[source_name]
                if max_translation>1e-5 or max_scale>1e-4:
                    raise ValueError("Native source has unsupported animated joint translation/scale")
                current_rotation,_=_rotation(current)
                desired=transport_global(source_rest[name],current_rotation,axes,references[name])
                local_rotation=Matrix(multiply(transpose(tw_rotation),desired)).to_quaternion()
                location=neutral.translation
                if source_name=="@ARMATURE":
                    location=tw.inverted()@((tw@bone.head_local)+Matrix(axes)@(world.translation-sw.translation)*scale)
                    if hip_anchor:
                        source_hip=midpoint([world@poses[landmarks[k]["source"]].translation for k in ("left_hip","right_hip")])
                        head,expected_hip=root_position(source_hip_mid,source_hip,target_hip_mid,tuple(tw@bone.head_local),
                            axes,scale,references[name],desired)
                        location=tw.inverted()@Vector(head)
                        expected_hips.append(expected_hip)
                pose=Matrix.LocRotScale(location,local_rotation,Vector((1,1,1)))
                basis=bone.convert_local_to_pose(pose,bone.matrix_local,invert=True,**kw)
                if max(abs(v-1) for v in basis.to_scale())>1e-4 or (source_name!="@ARMATURE" and basis.translation.length>1e-5):
                    raise ValueError("Target hierarchy compensation introduced translation/scale")
                pb=rig.pose.bones[name]
                pb.rotation_mode="QUATERNION"
                tracker=root_rotation if source_name=="@ARMATURE" else metrics[name]
                pb.rotation_quaternion=tracker.add(tuple(basis.to_quaternion()),frame)
                pb.location=basis.translation if source_name=="@ARMATURE" else (0,0,0)
                pb.keyframe_insert("rotation_quaternion",frame=frame)
                if source_name=="@ARMATURE": pb.keyframe_insert("location",frame=frame)
                computed[name]=pose
                want[name]={"rotation":desired,"head":list(tw@pose.translation)}
            expected.append(want)
        curves=[]
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    curves.extend(bag.fcurves)
        if len(curves)!=len(pairs)*4+3:
            raise ValueError("Native Action did not retain exactly the keyed rotation/root channels")
        for curve in curves:
            if len(curve.keyframe_points)!=frames:
                raise ValueError("Native Action has incomplete baked keyframes")
            for point in curve.keyframe_points: point.interpolation="LINEAR"
        root_bind_head=list(tw@rig.data.bones[pairs[0]["target"]].head_local)
        anchor={"source_bind_midpoint_world":list(source_hip_mid),"target_bind_midpoint_world":list(target_hip_mid),
                "sources":[landmarks[k]["source"] for k in ("left_hip","right_hip")],
                "targets":[landmarks[k]["target"] for k in ("left_hip","right_hip")],"expected":expected_hips} if hip_anchor else None
        review=evaluate_native_timeline(bpy,human,rig,source,expected,pairs,tw,root_bind_head,bind_points,
            lambda matrix:_rotation(matrix,target_projections)[0],root/"review_motion.blend",hip_anchor=anchor)
        review["root_motion_metrics"].update(max_rotation_step_degrees=root_rotation.maximum_step,
            max_rotation_step_frame=root_rotation.maximum_frame)
        timeline={**review,"schema_version":1,"convention":CONVENTION,
                  "bindings":{k:options[k] for k in ("source_sha256","snapshot_sha256","mapping_sha256","master_sha256")},
                  "source_frame_count":frames,"source_first_frame":source["first_frame"],"fps":source["fps"],
                  "mapped_pairs":pairs,"reference_proofs":proofs,"source_to_target_axes":axes,"root_motion_scale":scale,
                  "target_armature_world":[float(v) for line in tw for v in line],
                  "target_root_bind_head":root_bind_head,
                  "neutral_bind_skin_sha256":bind_sha,"deformation_probes":probes,
                  "target_anatomical_landmarks":{key:list(target_points[row["target"]]) for key,row in landmarks.items()},
                  "max_source_translation_error_ratio":max_translation,"max_source_scale_error":max_scale,
                  "max_target_rotation_projection":max(target_projections),
                  "joint_motion_metrics":[metrics[row["target"]].report() for row in pairs[1:]],
                  "max_bone_quaternion_step_degrees":{name:m.report()["max_step_degrees"] for name,m in metrics.items()},
                  "target_pose_environment_checked":True,
                  "omitted_source_bones":[b["name"] for b in source["bones"] if b["name"] not in {p["source"] for p in pairs}],
                  "neutral_target_helpers":[n for n in ordered if n not in by_target],
                  "retargeting_verified":False,"engine_import_verified":False}
        path=root/"target_timeline.json"
        payload=json.dumps(timeline,ensure_ascii=False,allow_nan=False,separators=(",",":")).encode()
        if len(payload)>64*1024*1024 or path.exists() or path.is_symlink(): raise ValueError("Invalid/occupied native timeline output")
        with path.open("xb") as stream: stream.write(payload)
        result={"status":"REAL_NATIVE_FBX_BODY_MOTION_MEASURED","convention":CONVENTION,
                "bindings":timeline["bindings"],"source_frame_count":frames,"mapped_bone_count":len(pairs),
                "timeline":_record(path),"visual_review_blend":review["visual_review_blend"],
                "retargeting_verified":False,"animation_visual_quality_verified":False,"engine_import_verified":False}
        if options["render_private_frames"]:
            result["private_review_renders"]=render_private_review(bpy,human,frames,root/"review_motion.blend",
                {**timeline["bindings"],"review_action_sha256":review["visual_review_blend"]["sha256"],
                 "timeline_sha256":result["timeline"]["sha256"],"conversion_convention":CONVENTION,
                 "source_first_frame":source["first_frame"],"camera_translation_policy":"FOLLOW_HIP_MIDPOINT_TRANSLATION" if hip_anchor else "FOLLOW_ROOT_TRANSLATION"},
                root_positions={r["frame"]:r["hip_midpoint_world" if hip_anchor else "root_world_head"] for r in review["full_timeline_frames"]})
        if rig_fingerprint(bpy,human)!=before or _digest(master)!=options["master_sha256"]:
            raise ValueError("Native diagnostics changed target rest/skin/master")
        if _digest(source_path)!=options["snapshot_sha256"] or _digest(profile_path)!=options["mapping_sha256"]:
            raise ValueError("Native source/profile changed during target evaluation")
        return result
    finally:
        partial=rig.animation_data.action if rig.animation_data else None
        if rig.animation_data and (action or partial):
            rig.animation_data_clear()
            bpy.data.actions.remove(action or partial,do_unlink=True)
        for bone,basis,mode in preserved:
            bone.rotation_mode=mode;bone.matrix_basis=basis
        scene.render.fps,scene.render.fps_base,rig.data.pose_position=old[1:]
        scene.frame_set(old[0]);bpy.context.view_layer.update()
