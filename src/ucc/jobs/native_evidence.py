"""Independent native target-pose/skin/root evidence validation; no Blender/Qt."""
from hashlib import sha256
import json
import math
from pathlib import Path
import struct

from ucc.core.errors import ValidationError
from ucc.animations.source_rest_frames import is_sha256
from ucc.animations.native_profile import CONVENTION, LANDMARKS
from ucc.animations import native_math as nm
from ucc.animations.native_palms import PALM_AXES, palm_evidence
from .motion_quality_evidence import validate_motion_quality
from .native_anchor_evidence import anchor_context, check_anchor_frame, finish_anchor
from .native_skin_evidence import validate_skin
from .native_strain_evidence import validate_strain_reference


def number(v,low,high): return type(v) in (int,float) and math.isfinite(v) and low<=v<=high


def vector(v):
    if type(v) is not list or len(v)!=3 or any(not number(x,-1e6,1e6) for x in v):
        raise ValidationError("Invalid native world-space evidence vector")
    return v


def bound_file(folder: Path,record,name,maximum,*,cancel_check=lambda:None):
    path=folder/name
    if (type(record) is not dict or set(record)!={"name","bytes","sha256"} or record["name"]!=name or
            type(record["bytes"]) is not int or not 0<record["bytes"]<=maximum or not is_sha256(record["sha256"]) or
            path.is_symlink() or not path.is_file() or path.resolve().parent!=folder.resolve() or path.stat().st_size!=record["bytes"]):
        raise ValidationError("Missing/redirected native evidence artifact")
    h=sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):
            cancel_check();h.update(chunk)
    if h.hexdigest()!=record["sha256"]: raise ValidationError("Native evidence artifact SHA differs")
    return path


def _difference(a,b): return max(abs(x-y) for ra,rb in zip(a,b) for x,y in zip(ra,rb))


def validate_native_timeline(data,report,source,profile,bindings,*,cancel_check=lambda:None):
    if (type(report) is not dict or report.get("status")!="REAL_NATIVE_FBX_BODY_MOTION_MEASURED" or
            report.get("convention")!=CONVENTION or report.get("bindings")!=bindings or
            type(report.get("source_frame_count")) is not int or report["source_frame_count"]!=len(source["frames"]) or
            type(report.get("mapped_bone_count")) is not int or report["mapped_bone_count"]!=len(profile["pairs"]) or
            any(report.get(k) is not False for k in ("retargeting_verified","animation_visual_quality_verified","engine_import_verified"))):
        raise ValidationError("Native body summary identity/count/approval differs")
    if (type(data) is not dict or type(data.get("schema_version")) is not int or data["schema_version"]!=1 or
            data.get("convention")!=CONVENTION or data.get("bindings")!=bindings or
            data.get("source_frame_count")!=len(source["frames"]) or type(data.get("source_frame_count")) is not int or
            data.get("source_first_frame")!=source["first_frame"] or type(data.get("source_first_frame")) is not int or
            data.get("fps")!=source["fps"] or type(data.get("fps")) not in (int,float) or
            data.get("mapped_pairs")!=profile["pairs"] or data.get("deformation_reference")!="ROOT_TRANSLATION_REMOVED" or
            any(data.get(k) is not False for k in ("retargeting_verified","animation_visual_quality_verified","engine_import_verified","joint_twist_visual_quality_verified")) or
            data.get("visual_review_artifact_created") is not True or data.get("visual_review_blend")!=report["visual_review_blend"]):
        raise ValidationError("Native complete timeline convention/bindings/flags differ")
    pairs=profile["pairs"];count=len(source["frames"])
    source_bones={b["name"]:b for b in source["bones"]}
    if {p["source"] for p in pairs}-{*source_bones,"@ARMATURE"}:
        raise ValidationError("Mapped native source bone is absent")
    world=nm.rows(source["armature_rest_world"])
    source_points={n:nm.point(world,b["head"]) for n,b in source_bones.items()}
    landmarks=profile["landmarks"]
    target_points=data.get("target_anatomical_landmarks")
    if type(target_points) is not dict or set(target_points)!=LANDMARKS:
        raise ValidationError("Missing measured target anatomical landmarks")
    for p in target_points.values(): vector(p)
    sb,sh=nm.body(*(source_points[landmarks[k]["source"]] for k in ("left_hip","right_hip","head")))
    tb,th=nm.body(*(target_points[k] for k in ("left_hip","right_hip","head")))
    palm_axes=palm_evidence(data,profile,source_points,{b["name"]:b["parent"] for b in source["bones"]},target_points,sh,th)
    for points,basis,height in (({k:source_points[r["source"]] for k,r in landmarks.items()},sb,sh),(target_points,tb,th)):
        middle=[(points["left_hip"][i]+points["right_hip"][i])/2 for i in range(3)]
        for key,sign in (("left_hand",1),("right_hand",-1),("left_foot",1),("right_foot",-1)):
            delta=[points[key][i]-middle[i] for i in range(3)]
            if sum(delta[i]*basis[i][0] for i in range(3))*sign<=.02*height:
                raise ValidationError("Native anatomical evidence crosses body sides")
            vertical=sum(delta[i]*basis[i][2] for i in range(3))
            if not ((-2*height<vertical<-.1*height) if "foot" in key else (-.5*height<vertical<1.5*height)):
                raise ValidationError("Native anatomical evidence has incompatible body heights")
    axes=data.get("source_to_target_axes");nm.check_rotation(axes)
    if _difference(axes,nm.product(tb,nm.transposed(sb)))>1e-5 or not number(data.get("root_motion_scale"),.25,4) or abs(data["root_motion_scale"]-th/sh)>1e-5:
        raise ValidationError("Native body orientation/root scale differs from measured landmarks")
    proofs=data.get("reference_proofs")
    if type(proofs) is not list or len(proofs)!=len(pairs): raise ValidationError("Incomplete native bind/reference proof")
    source_rest={};references={}
    for index,(pair,proof) in enumerate(zip(pairs,proofs)):
        name,target=pair["source"],pair["target"]
        if (type(proof) is not dict or proof.get("source")!=name or proof.get("target")!=target or
                type(proof.get("weighted_vertices")) is not int or not (0 if index==0 else 16)<=proof["weighted_vertices"]<=250000 or
                not number(proof.get("target_bind_projection"),0,5e-4) or not number(proof.get("segment_alignment_residual"),0,1e-5)):
            raise ValidationError("Invalid native weighted bind/reference evidence")
        for key in ("source_bind_rotation","target_bind_rotation","reference_rotation"):nm.check_rotation(proof.get(key))
        bind=world if name=="@ARMATURE" else nm.product(world,nm.rows(source_bones[name]["matrix"]))
        rotation,_=nm.rotation([v for r in bind for v in r])
        if _difference(rotation,proof["source_bind_rotation"])>1e-5:
            raise ValidationError("Native source bind axes differ from original snapshot")
        if index==0:
            expected=proof["target_bind_rotation"]
        else:
            for key in ("source_segment","target_segment","source_secondary","target_secondary"):vector(proof.get(key))
            tip=source_points[pair["source_tip"]] if pair["source_tip"] is not None else nm.point(world,source_bones[name]["tail"])
            if max(abs(proof["source_segment"][i]-(tip[i]-source_points[name][i])) for i in range(3))>1e-5:
                raise ValidationError("Native anatomical source segment differs")
            column=2 if pair["secondary"]=="UP" else 1;sign=1 if column==2 else -1
            expected_source=[sign*sb[i][column] for i in range(3)]
            expected_target=[sign*tb[i][column] for i in range(3)]
            if pair["secondary"] in PALM_AXES:
                expected_source,expected_target=palm_axes[PALM_AXES[pair["secondary"]]]
            if (max(abs(proof["source_secondary"][i]-expected_source[i]) for i in range(3))>1e-5 or
                    max(abs(proof["target_secondary"][i]-expected_target[i]) for i in range(3))>1e-5):
                raise ValidationError("Native secondary anatomical axes differ")
            alignment=nm.product(nm.product(axes,nm.anatomy(proof["source_segment"],proof["source_secondary"])),
                                 nm.transposed(nm.anatomy(proof["target_segment"],proof["target_secondary"])))
            expected=nm.product(alignment,proof["target_bind_rotation"])
            if name in {landmarks[k]["source"] for k in ("left_foot","right_foot")}:
                for key,basis in (("source_segment",sb),("target_segment",tb)):
                    segment=nm.unit(proof[key])
                    if sum(segment[i]*-basis[i][1] for i in range(3))<.2:
                        raise ValidationError("Native anatomical feet face against the measured body forward")
        if _difference(expected,proof["reference_rotation"])>1e-5: raise ValidationError("Common native reference is not the declared anatomical alignment")
        source_rest[name]=rotation;references[name]=proof["reference_rotation"]
    actual_omissions=[b["name"] for b in source["bones"] if b["name"] not in {p["source"] for p in pairs}]
    helpers=data.get("neutral_target_helpers")
    if data.get("omitted_source_bones")!=actual_omissions or type(helpers) is not list or len(helpers)>256 or any(type(n) is not str or not 0<len(n)<=128 or not n.isprintable() or n in {p["target"] for p in pairs} for n in helpers) or len(set(helpers))!=len(helpers):
        raise ValidationError("Native omissions/neutral helper evidence differs")
    rows=data.get("full_timeline_frames");bind_rows=data.get("bind_relative_frames")
    if type(rows) is not list or len(rows)!=count or type(bind_rows) is not list or len(bind_rows)!=count:
        raise ValidationError("Incomplete native target skin timeline")
    diagonal=data.get("model_baseline_diagonal_local")
    if not number(diagonal,.01,100000):raise ValidationError("Invalid native model bounds")
    probes=data.get("deformation_probes")
    if not is_sha256(data.get("neutral_bind_skin_sha256")) or type(probes) is not list or len(probes)!=len(pairs)-1:
        raise ValidationError("Missing independent native target skin response")
    for row,pair in zip(probes,pairs[1:]):
        if (type(row) is not dict or row.get("source")!=pair["source"] or row.get("target")!=pair["target"] or
                row.get("axis") not in {"X","Y","Z"} or type(row.get("moved_vertices")) is not int or
                not 16<=row["moved_vertices"]<=250000 or not number(row.get("max_displacement_local"),1e-6,diagonal*1.5)):
            raise ValidationError("Mapped native target lacks actual weighted skin deformation")
    for key,limit in (("max_global_pose_residual",1e-4),("max_target_rotation_projection",5e-4),("max_source_translation_error_ratio",1e-5),("max_source_scale_error",1e-4)):
        if not number(data.get(key),0,limit): raise ValidationError("Unbounded native FK/scale/translation residual")
    target_world=data.get("target_armature_world");nm.rotation(target_world)
    root_bind=vector(data.get("target_root_bind_head"))
    anchor=anchor_context(data,profile,source_points,target_points)
    source_indices={b["name"]:i for i,b in enumerate(source["bones"])}
    source_world_scale=nm.scale(world)
    max_source_translation=max_source_scale=0.
    maximum=maximum_residual=maximum_speed=maximum_distance=maximum_projection=maximum_travel=maximum_root_angle=0.
    previous_root=previous_root_rotation=None;vertex_count=None;deformation_hashes=set();root_angles=[]
    for frame,(row,bind,src) in enumerate(zip(rows,bind_rows,source["frames"]),1):
        cancel_check()
        if (type(row) is not dict or type(row.get("frame")) is not int or row["frame"]!=frame or
                type(row.get("source_frame")) is not int or row["source_frame"]!=source["first_frame"]+frame-1 or
                any(not is_sha256(row.get(k)) for k in ("evaluated_sha256","deformation_sha256","target_pose_sha256")) or
                type(row.get("evaluated_vertex_count")) is not int or not 100<row["evaluated_vertex_count"]<=250000 or
                type(row.get("moved_vertices")) is not int or not 0<=row["moved_vertices"]<=row["evaluated_vertex_count"] or
                not number(row.get("max_displacement_local"),0,diagonal*1.5) or
                not number(row.get("max_bind_displacement_local"),0,diagonal*1.5) or
                not number(row.get("adjacent_max_displacement_local"),0,diagonal*.8) or not number(row.get("global_pose_residual"),0,1e-4)):
            raise ValidationError("Unbounded/misordered native evaluated skin frame")
        if frame==1 and (row["moved_vertices"]!=0 or row["max_displacement_local"]>1e-6 or row["adjacent_max_displacement_local"]>1e-6):
            raise ValidationError("Native first frame is not its deformation reference")
        if vertex_count is None:vertex_count=row["evaluated_vertex_count"]
        elif vertex_count!=row["evaluated_vertex_count"]:raise ValidationError("Native evaluated vertex count changed")
        if (type(bind) is not dict or type(bind.get("frame")) is not int or bind["frame"]!=frame or
                not number(bind.get("min_edge_length_ratio"),.05,4) or not number(bind.get("max_edge_stretch_ratio"),.05,4) or bind["min_edge_length_ratio"]>bind["max_edge_stretch_ratio"]):
            raise ValidationError("Extreme native deformation relative to neutral bind skin")
        poses=row.get("target_global_poses")
        if type(poses) is not list or len(poses)!=len(pairs): raise ValidationError("Incomplete actual native target poses")
        digest=sha256();digest.update(struct.pack("<16q",*(round(v*1e6) for v in target_world)))
        sw=nm.rows(src["armature_world"])
        max_source_scale=max(max_source_scale,abs(nm.scale(sw)/source_world_scale-1))
        for pair,pose in zip(pairs,poses):
            actual,correction=nm.rotation(pose,target_noise=True)
            maximum_projection=max(maximum_projection,correction)
            name=pair["source"]
            if name!="@ARMATURE":
                local_pose=nm.rows(src["poses"][source_indices[name]])
                local_rest=nm.rows(source_bones[name]["matrix"])
                parent=source_bones[name]["parent"]
                if parent is not None:
                    local_pose=nm.product(nm.inverse(nm.rows(src["poses"][source_indices[parent]])),local_pose)
                    local_rest=nm.product(nm.inverse(nm.rows(source_bones[parent]["matrix"])),local_rest)
                error=math.dist([r[3] for r in local_pose[:3]],[r[3] for r in local_rest[:3]])/(sh/source_world_scale)
                max_source_translation=max(max_source_translation,error)
                max_source_scale=max(max_source_scale,abs(nm.scale(local_pose)/nm.scale(local_rest)-1))
                if max_source_translation>1e-5 or max_source_scale>1e-4:
                    raise ValidationError("Original native source has unsupported animated translation/scale")
            current=sw if name=="@ARMATURE" else nm.product(sw,nm.rows(src["poses"][source_indices[name]]))
            current_rotation,_=nm.rotation([v for r in current for v in r])
            expected=nm.global_pose(source_rest[name],current_rotation,axes,references[name])
            if _difference(expected,actual)>1e-4: raise ValidationError("Actual keyed native target does not implement the full source bind/pose conversion")
            digest.update(struct.pack("<16q",*(round(v*1e6) for v in pose)))
        if digest.hexdigest()!=row["target_pose_sha256"]:raise ValidationError("Native actual pose hash differs")
        root=vector(row.get("root_world_head"))
        if max(abs(root[i]-poses[0][i*4+3]) for i in range(3))>1e-6:raise ValidationError("Native root head/pose differ")
        delta=[src["armature_world"][i*4+3]-source["armature_rest_world"][i*4+3] for i in range(3)]
        expected_root=[root_bind[i]+sum(axes[i][j]*delta[j] for j in range(3))*data["root_motion_scale"] for i in range(3)]
        if anchor is None:
            if math.dist(root,expected_root)>1e-4:raise ValidationError("Native source root displacement was not preserved")
        else:check_anchor_frame(anchor,src,row,data,source_indices,root_bind,poses)
        distance=math.dist(root,previous_root) if previous_root is not None else 0.
        speed=distance*source["fps"]
        if not number(row.get("root_speed_world"),0,20) or abs(speed-row["root_speed_world"])>1e-4:raise ValidationError("Native root velocity differs")
        maximum_speed=max(maximum_speed,speed);maximum_distance=max(maximum_distance,distance);previous_root=root
        maximum_travel=max(maximum_travel,math.dist(root,root_bind))
        root_rotation,_=nm.rotation(poses[0],target_noise=True)
        root_angle=0.
        if previous_root_rotation is not None:
            delta=nm.product(nm.transposed(previous_root_rotation),root_rotation)
            root_angle=math.degrees(math.acos(max(-1.,min(1.,(sum(delta[i][i] for i in range(3))-1)/2))))
        if root_angle>80.001:raise ValidationError("Actual native root rotations are discontinuous")
        root_angles.append(root_angle);maximum_root_angle=max(maximum_root_angle,root_angle);previous_root_rotation=root_rotation
        maximum=max(maximum,row["adjacent_max_displacement_local"]);maximum_residual=max(maximum_residual,row["global_pose_residual"])
        deformation_hashes.add(row["deformation_sha256"])
    if (len(deformation_hashes)<3 or sum(r["moved_vertices"]>=16 for r in rows[1:])<2 or
            not number(data.get("max_adjacent_mesh_step_local"),0,diagonal*.8) or abs(data["max_adjacent_mesh_step_local"]-maximum)>1e-6 or
            abs(data["max_global_pose_residual"]-maximum_residual)>1e-6 or maximum_projection>data["max_target_rotation_projection"]+1e-6):
        raise ValidationError("Native full-frame motion/residual summaries differ")
    if max_source_translation>data["max_source_translation_error_ratio"]+1e-6 or max_source_scale>data["max_source_scale_error"]+1e-6:
        raise ValidationError("Native source translation/scale summaries omit measured input changes")
    root_metrics=data.get("root_motion_metrics")
    if (type(root_metrics) is not dict or type(root_metrics.get("frames_measured")) is not int or root_metrics["frames_measured"]!=count or
            not number(root_metrics.get("max_rotation_step_degrees"),0,80) or type(root_metrics.get("max_rotation_step_frame")) is not int or not 1<=root_metrics["max_rotation_step_frame"]<=count or
            not number(root_metrics.get("max_speed_world"),0,20) or abs(root_metrics["max_speed_world"]-maximum_speed)>1e-4 or
            type(root_metrics.get("max_speed_frame")) is not int or not 1<=root_metrics["max_speed_frame"]<=count or abs(rows[root_metrics["max_speed_frame"]-1]["root_speed_world"]-maximum_speed)>1e-4 or
            not number(root_metrics.get("max_distance_from_bind_world"),0,2e6) or abs(root_metrics["max_distance_from_bind_world"]-maximum_travel)>1e-4 or
            abs(root_metrics["max_rotation_step_degrees"]-maximum_root_angle)>.02 or abs(root_angles[root_metrics["max_rotation_step_frame"]-1]-maximum_root_angle)>.02 or
            not number(root_metrics.get("max_step_distance_world"),0,20/source["fps"]) or abs(root_metrics["max_step_distance_world"]-maximum_distance)>1e-5):
        raise ValidationError("Native root motion summaries differ")
    bind_mesh=data.get("bind_edge_strain");mesh=data.get("mesh_edge_strain")
    if type(bind_mesh) is not dict or type(mesh) is not dict or bind_mesh.get("evaluated_topology_sha256")!=mesh.get("evaluated_topology_sha256"):
        raise ValidationError("Native bind/pose skin topology differs")
    total,measured,excluded=(bind_mesh.get(k) for k in ("evaluated_edge_count","measured_edge_count","degenerate_baseline_edges_excluded"))
    if any(type(v) is not int for v in (total,measured,excluded)) or not 16<=measured<=total<=750000 or measured+excluded!=total:
        raise ValidationError("Native bind edge coverage is incomplete")
    neutral_reference=validate_strain_reference(data,profile)
    validate_motion_quality(data,[p["target"] for p in pairs[1:]],neutral_reference=neutral_reference)
    finish_anchor(anchor,data)
    validate_skin(data,report,profile)
    return data


def read_native_timeline(folder,report,source,profile,bindings,*,cancel_check=lambda:None):
    if type(report) is not dict:raise ValidationError("Missing native body worker report")
    path=bound_file(folder,report.get("timeline"),"target_timeline.json",64*1024*1024,cancel_check=cancel_check)
    with path.open("rb") as stream:payload=stream.read(64*1024*1024+1)
    if len(payload)>64*1024*1024 or sha256(payload).hexdigest()!=report["timeline"]["sha256"]:
        raise ValidationError("Native timeline changed during validation")
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result:raise ValueError("Duplicate native timeline key")
            result[k]=v
        return result
    def nonfinite(value):raise ValueError("Nonfinite native timeline number")
    try:data=json.loads(payload,object_pairs_hook=unique,parse_constant=nonfinite)
    except (ValueError,UnicodeError,RecursionError) as exc:raise ValidationError("Invalid native target timeline JSON") from exc
    validate_native_timeline(data,report,source,profile,bindings,cancel_check=cancel_check)
    action=bound_file(folder,report["visual_review_blend"],"review_motion.blend",512*1024*1024,cancel_check=cancel_check)
    if action.stat().st_size<=10000:
        raise ValidationError("Native Action copy is too small to be the measured character")
    with action.open("rb") as stream:
        if stream.read(7)!=b"BLENDER":raise ValidationError("Native Action copy is not an uncompressed Blender scene")
    return data,path
