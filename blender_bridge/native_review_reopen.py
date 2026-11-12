"""Fresh-process actual bound-skin review verification, without rebaking or saving."""
from __future__ import annotations
from hashlib import sha256
import math
from pathlib import Path
from typing import Any

from blender_bridge.native_inputs import read_json, validate_source, validate_profile
from blender_bridge.native_corrective import SETTINGS, NAME, POLICY
from blender_bridge.native_skin_stack import source_stack
from blender_bridge.pose_environment import validate_pose_environment
from blender_bridge.pose_deformation import _evaluated_vertices, _movement
from blender_bridge.bvh_review_timeline import evaluated_edges
from blender_bridge.motion_quality import EdgeStrain
from blender_bridge.fbx_source import pose_digest
from blender_bridge.refit_revision import rig_fingerprint


def digest(path: Path) -> str:
    h=sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()


def bound_scene(path: Path, expected: str) -> None:
    if path.is_symlink() or not path.is_file() or not 10000<path.stat().st_size<=512*1024*1024 or digest(path)!=expected:
        raise ValueError("Native reopen scene is missing, redirected, oversized or SHA-mismatched")
    with path.open("rb") as stream:
        if stream.read(7)!=b"BLENDER":raise ValueError("Native reopen needs an uncompressed trusted scene copy")


def scene_objects(bpy: Any):
    humans=[o for o in bpy.data.objects if o.type=="MESH" and len(o.data.vertices)>100]
    rigs=[o for o in bpy.data.objects if o.type=="ARMATURE"]
    if len(humans)!=1 or len(rigs)!=1:raise ValueError("Native reopen needs exactly one actual human and rig")
    return humans[0],rigs[0]


def same_world(obj: Any, expected: list) -> bool:
    return all(math.isfinite(float(obj.matrix_world[i][j])) and abs(float(obj.matrix_world[i][j])-expected[i*4+j])<=1e-6 for i in range(4) for j in range(4))


def same_strain(measured: dict, expected: Any, frame: int) -> bool:
    return (type(expected) is dict and set(expected)=={"frame",*measured} and
            type(expected.get("frame")) is int and expected["frame"]==frame and
            all(type(expected.get(k)) in (int,float) and math.isfinite(expected[k]) and abs(v-expected[k])<=1e-6
                for k,v in measured.items()))


def reopen_native(bpy: Any, root: Path, options: dict) -> dict:
    from mathutils import Matrix
    paths={"candidate.blend":"master_sha256","review_motion.blend":"review_sha256",
           "source_snapshot.json":"snapshot_sha256","native_mapping.json":"mapping_sha256","target_timeline.json":"timeline_sha256"}
    bound_scene(root/"candidate.blend",options["master_sha256"])
    bound_scene(root/"review_motion.blend",options["review_sha256"])
    source=validate_source(read_json(root/"source_snapshot.json",options["snapshot_sha256"],64*1024*1024),options["source_sha256"])
    profile=validate_profile(read_json(root/"native_mapping.json",options["mapping_sha256"],64*1024),options["source_sha256"],options["snapshot_sha256"],options["master_sha256"])
    data=read_json(root/"target_timeline.json",options["timeline_sha256"],64*1024*1024)
    reference=profile.get("mesh_strain_reference","FIRST_POSE_AND_NEUTRAL_V1")
    if data.get("mesh_strain_reference","FIRST_POSE_AND_NEUTRAL_V1")!=reference:
        raise ValueError("Native reopened strain reference differs from its bound map")
    neutral_reference=reference=="TRUE_NEUTRAL_BIND_V2"
    observations=data.get("first_pose_relative_frames")
    rows=data.get("full_timeline_frames");bind_rows=data.get("bind_relative_frames");master_rows=data.get("master_relative_frames")
    count=len(source["frames"])
    if neutral_reference and (type(observations) is not list or len(observations)!=count or
            type(data.get("motion_quality_schema_version")) is not int or data["motion_quality_schema_version"]!=2):
        raise ValueError("Native reopened neutral-reference observations are incomplete")
    if not neutral_reference and (observations is not None or "first_pose_edge_strain" in data or
            type(data.get("motion_quality_schema_version")) is not int or data["motion_quality_schema_version"]!=1):
        raise ValueError("Native reopened legacy strain contains cross-policy observations")
    if (profile.get("skin_deformation_policy")!=POLICY or data.get("skin_deformation_policy")!=POLICY or
            data.get("mapped_pairs")!=profile["pairs"] or data.get("source_frame_count")!=count or
            data.get("bindings")!={k:options[k] for k in ("master_sha256","source_sha256","snapshot_sha256","mapping_sha256")} or
            any(type(v) is not list or len(v)!=count for v in (rows,bind_rows,master_rows)) or
            any(data.get(k) is not False for k in ("retargeting_verified","animation_visual_quality_verified","engine_import_verified"))):
        raise ValueError("Native reopen timeline policy, identity, approvals or coverage differs")
    proof=data.get("skin_deformation")
    if type(proof) is not dict or proof.get("policy")!=POLICY:raise ValueError("Native reopen has no bound skin proof")
    record=data.get("visual_review_blend")
    if (type(record) is not dict or set(record)!={"name","bytes","sha256"} or record["name"]!="review_motion.blend" or
            type(record["bytes"]) is not int or record["bytes"]!=(root/"review_motion.blend").stat().st_size or record["sha256"]!=options["review_sha256"]):
        raise ValueError("Native reopen saved-copy binding differs from its timeline")
    bpy.ops.wm.open_mainfile(filepath=str(root/"candidate.blend"),load_ui=False)
    human,rig=scene_objects(bpy)
    validate_pose_environment(rig,human,[b.name for b in rig.pose.bones])
    original,original_sha=_evaluated_vertices(bpy,human)
    original_stack=source_stack(human,rig)
    fingerprint=rig_fingerprint(bpy,human)
    original_world=[float(v) for line in rig.matrix_world for v in line]
    original_mesh_world=[float(v) for line in human.matrix_world for v in line]
    if original_sha!=proof.get("source_neutral_sha256") or original_stack!=proof.get("source_modifiers"):
        raise ValueError("Native reopen original skin or source modifier/mask proof differs")
    master_strain=EdgeStrain(original,evaluated_edges(bpy,human))
    bpy.ops.wm.open_mainfile(filepath=str(root/"review_motion.blend"),load_ui=False)
    human,rig=scene_objects(bpy)
    if not same_world(human,original_mesh_world) or not same_world(rig,original_world):
        raise ValueError("Native reopened object transforms differ from the original master")
    mods=tuple(human.modifiers)
    if len(mods)!=len(original_stack)+1:raise ValueError("Native reopen added or removed source modifiers")
    mod=mods[-1]
    if (mod.name!=NAME or mod.type!="CORRECTIVE_SMOOTH" or not mod.is_bind or
            any(type(getattr(mod,k)) is not type(v) or getattr(mod,k)!=v for k,v in SETTINGS.items()) or
            source_stack(human,rig,modifiers=mods[:-1])!=original_stack or rig_fingerprint(bpy,human)!=fingerprint or
            [float(v) for line in rig.matrix_world for v in line]!=original_world):
        raise ValueError("Native reopened corrective binding, settings, source weights or rig differ")
    action=rig.animation_data.action if rig.animation_data else None
    if action is None or list(action.frame_range)!=[1.,float(count)] or len(rig.animation_data.nla_tracks):
        raise ValueError("Native reopened Action range or NLA differs")
    for block in (human,human.data.shape_keys):
        animation=getattr(block,"animation_data",None)
        if animation and (animation.action or len(animation.drivers) or len(animation.nla_tracks)):
            raise ValueError("Native reopened mesh has unsupported animation or drivers")
    scene=bpy.context.scene
    if abs(scene.render.fps/scene.render.fps_base-source["fps"])>1e-6:
        raise ValueError("Native reopened playback frame rate differs")
    curves=[c for layer in action.layers for strip in layer.strips for bag in strip.channelbags for c in bag.fcurves]
    allowed={(rig.pose.bones[p["target"]].path_from_id("rotation_quaternion"),i) for p in profile["pairs"] for i in range(4)}
    allowed|={(rig.pose.bones[profile["pairs"][0]["target"]].path_from_id("location"),i) for i in range(3)}
    if len(curves)!=len(allowed) or {(c.data_path,c.array_index) for c in curves}!=allowed:
        raise ValueError("Native reopened Action has unexpected or missing channels")
    for curve in curves:
        if len(curve.keyframe_points)!=count or any(p.interpolation!="LINEAR" or abs(p.co.x-i)>1e-6 for i,p in enumerate(curve.keyframe_points,1)):
            raise ValueError("Native reopened Action is not a complete linear bake")
    helpers=set(rig.pose.bones.keys())-{p["target"] for p in profile["pairs"]}
    for name in helpers:
        if any(abs(rig.pose.bones[name].matrix_basis[i][j]-(i==j))>1e-5 for i in range(4) for j in range(4)):
            raise ValueError("Native reopened helper has an unkeyed pose")
    slot=rig.animation_data.action_slot
    rig.animation_data.action=None
    for bone in rig.pose.bones:bone.matrix_basis=Matrix.Identity(4)
    validate_pose_environment(rig,human,[b.name for b in rig.pose.bones])
    neutral,neutral_sha=_evaluated_vertices(bpy,human)
    if neutral_sha!=proof.get("bound_neutral_sha256") or neutral_sha!=data.get("neutral_bind_skin_sha256") or len(neutral)!=len(original):
        raise ValueError("Native reopened neutral skin differs")
    if max(math.dist(a,b) for a,b in zip(original,neutral))>1e-6:
        raise ValueError("Native reopened bound neutral changed the original shape")
    bind=EdgeStrain(neutral,evaluated_edges(bpy,human))
    if neutral_reference and (data.get("mesh_edge_strain")!=bind.report() or data.get("bind_edge_strain")!=bind.report()):
        raise ValueError("Native reopened quality does not describe neutral-bind topology")
    rig.animation_data.action=action;rig.animation_data.action_slot=slot
    first_strain=None
    for frame,(row,expect_bind,expect_master) in enumerate(zip(rows,bind_rows,master_rows),1):
        if type(row) is not dict or type(row.get("frame")) is not int or row["frame"]!=frame:
            raise ValueError("Native reopened timeline frames differ")
        bpy.context.scene.frame_set(frame)
        if not same_world(human,original_mesh_world) or not same_world(rig,original_world):
            raise ValueError("Native reopened object transforms are driven outside the bone Action")
        points,skin_sha=_evaluated_vertices(bpy,human)
        edges=evaluated_edges(bpy,human)
        if neutral_reference:
            if first_strain is None:first_strain=EdgeStrain(points,edges)
            measured=first_strain.observe(points,edges,frame);expected=observations[frame-1]
            if not same_strain(measured,expected,frame):
                raise ValueError("Native reopened first-pose observations differ")
            if first_strain.report()!=data.get("first_pose_edge_strain"):
                raise ValueError("Native reopened first-pose topology differs")
        poses=[[float(v) for line in rig.matrix_world@rig.pose.bones[p["target"]].matrix for v in line] for p in profile["pairs"]]
        if skin_sha!=row.get("evaluated_sha256") or pose_digest(original_world,poses)!=row.get("target_pose_sha256"):
            raise ValueError("Native saved Action does not reproduce actual skin/poses on frame "+str(frame))
        actual_bind=bind.measure(points,edges,frame)
        for measured,expected in ((actual_bind,expect_bind),(master_strain.measure(points,edges,frame),expect_master)):
            if not same_strain(measured,expected,frame):
                raise ValueError("Native reopened original/bound edge strain differs")
        quality={"frame":frame,**{k:row.get(k) for k in actual_bind}}
        if neutral_reference and not same_strain(actual_bind,quality,frame):
            raise ValueError("Native reopened main quality is not neutral-bound")
        mod.show_viewport=False
        try:raw,raw_sha=_evaluated_vertices(bpy,human)
        finally:mod.show_viewport=True
        correction=row.get("skin_correction",{})
        moved,maximum=_movement(raw,points)
        if (raw_sha!=correction.get("uncorrected_sha256") or moved!=correction.get("corrected_vertices") or
                abs(maximum-correction.get("max_correction_local",math.inf))>1e-8):
            raise ValueError("Native reopened uncorrected/corrected geometry differs")
        if "hip_anchor" in data:
            actual=[(rig.matrix_world@rig.pose.bones[n].matrix).translation for n in data["hip_anchor"]["target_bones"]]
            if math.dist([sum(p[i] for p in actual)/2 for i in range(3)],row.get("hip_midpoint_world",[]))>1e-6:
                raise ValueError("Native reopened hip trajectory differs")
    if source_stack(human,rig,modifiers=mods[:-1])!=original_stack:
        raise ValueError("Native reopen changed original source masks or weights")
    for name,key in paths.items():
        path=root/name
        if path.is_symlink() or not path.is_file() or digest(path)!=options[key]:raise ValueError("Native reopen changed staged input bytes")
    reference_evidence={"mesh_strain_reference":reference,"first_pose_observation_frames_verified":count} if neutral_reference else {}
    return {**reference_evidence,"status":"REAL_NATIVE_BODY_REVIEW_REOPENED","bindings":dict(options),"frames_verified":count,
            "uncorrected_skin_frames_verified":count,"master_strain_frames_verified":count,
            "hip_frames_verified":count if "hip_anchor" in data else 0,"skin_deformation_policy":POLICY,
            "original_master_unchanged":True,"review_unchanged":True,
            "retargeting_verified":False,"animation_visual_quality_verified":False,"engine_import_verified":False}
