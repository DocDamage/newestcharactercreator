"""Closed native skin policy and full-frame original/derived geometry evidence."""
from __future__ import annotations
import math
from ucc.core.errors import ValidationError
from ucc.animations.source_rest_frames import is_sha256

POLICY = "BOUND_CORRECTIVE_SMOOTH_V1"
SETTINGS = {"name":"UCC_PRIVATE_BOUND_CORRECTIVE_UNAPPROVED","type":"CORRECTIVE_SMOOTH","is_bound":True,
            "factor":.5,"iterations":5,"smooth_type":"SIMPLE","scale":1.,"rest_source":"BIND",
            "use_only_smooth":False,"use_pin_boundary":False,"vertex_group":"","invert_vertex_group":False,
            "show_viewport":True,"show_render":True}


def number(value,low,high):
    return type(value) in (int,float) and math.isfinite(value) and low <= value <= high


def validate_skin(data: dict, report: dict, profile: dict) -> None:
    keys={"skin_deformation_policy","skin_deformation","master_relative_frames","master_bind_edge_strain"}
    if profile.get("skin_deformation_policy","MASTER_MODIFIERS_V1") != POLICY:
        if keys.intersection(data) or "skin_state_restored" in report:
            raise ValidationError("Unrequested native corrective skin claims")
        return
    proof=data.get("skin_deformation")
    required={"schema_version","policy","source_modifier_count","review_modifier_count","modifier","source_armature","source_modifiers",
              "source_neutral_sha256","bound_neutral_sha256","neutral_vertex_count","max_neutral_displacement_local"}
    if (data.get("skin_deformation_policy")!=POLICY or report.get("skin_state_restored") is not True or
            type(proof) is not dict or set(proof)!=required or type(proof["schema_version"]) is not int or proof["schema_version"]!=1 or
            proof["policy"]!=POLICY or type(proof["source_modifier_count"]) is not int or not 1<=proof["source_modifier_count"]<=5 or
            type(proof["review_modifier_count"]) is not int or proof["review_modifier_count"]!=proof["source_modifier_count"]+1 or
            not is_sha256(proof["source_neutral_sha256"]) or not is_sha256(proof["bound_neutral_sha256"]) or
            proof["bound_neutral_sha256"]!=data["neutral_bind_skin_sha256"] or
            type(proof["neutral_vertex_count"]) is not int or not 100<proof["neutral_vertex_count"]<=250000 or
            not number(proof["max_neutral_displacement_local"],0,1e-6)):
        raise ValidationError("Invalid bound corrective skin identity, restoration or neutral-shape proof")
    mod=proof["modifier"]
    if type(mod) is not dict or set(mod)!=set(SETTINGS) or any(type(mod[k]) is not type(v) or mod[k]!=v for k,v in SETTINGS.items()):
        raise ValidationError("Bound corrective smoothing settings differ from the audited policy")
    arm=proof["source_armature"]
    fields={"name","type","rig_object","use_vertex_groups","use_bone_envelopes","use_deform_preserve_volume","use_multi_modifier","show_viewport","show_render"}
    if (type(arm) is not dict or set(arm)!=fields or arm["type"]!="ARMATURE" or
            any(type(arm[k]) is not str or not 0<len(arm[k])<=128 or not arm[k].isprintable() for k in ("name","rig_object")) or
            any(arm[k] is not v for k,v in (("use_vertex_groups",True),("use_bone_envelopes",False),("use_multi_modifier",False),("show_viewport",True),("show_render",True))) or
            type(arm["use_deform_preserve_volume"]) is not bool):
        raise ValidationError("Unsupported original armature skinning state")
    stack=proof["source_modifiers"]
    mask_fields={"name","type","mode","vertex_group","invert_vertex_group","threshold","use_smooth","show_viewport","show_render","source_mesh_vertices","vertex_group_sha256"}
    if type(stack) is not list or len(stack)!=proof["source_modifier_count"] or stack[0]!=arm:
        raise ValidationError("Native source modifier stack differs")
    for mask in stack[1:]:
        if (type(mask) is not dict or set(mask)!=mask_fields or mask["type"]!="MASK" or mask["mode"]!="VERTEX_GROUP" or
                any(type(mask[k]) is not str or not 0<len(mask[k])<=128 or not mask[k].isprintable() for k in ("name","vertex_group")) or
                type(mask["invert_vertex_group"]) is not bool or not number(mask["threshold"],0,1) or mask["use_smooth"] is not False or
                mask["show_viewport"] is not True or mask["show_render"] is not True or not is_sha256(mask["vertex_group_sha256"]) or
                type(mask["source_mesh_vertices"]) is not int or not proof["neutral_vertex_count"]<=mask["source_mesh_vertices"]<=250000):
            raise ValidationError("Unsupported or unbound static source mask")
    original=data.get("master_bind_edge_strain");derived=data["bind_edge_strain"]
    if type(original) is not dict or original!=derived:
        raise ValidationError("Original and corrected bind topology or edge coverage differs")
    frames=data.get("master_relative_frames")
    if type(frames) is not list or len(frames)!=data["source_frame_count"]:
        raise ValidationError("Incomplete original-master relative deformation evidence")
    moved_frames=0
    for frame,(row,master) in enumerate(zip(data["full_timeline_frames"],frames),1):
        if (row["evaluated_vertex_count"]!=proof["neutral_vertex_count"] or type(master) is not dict or
                type(master.get("frame")) is not int or master["frame"]!=frame or
                not number(master.get("min_edge_length_ratio"),.05,4) or not number(master.get("max_edge_stretch_ratio"),.05,4) or
                master["min_edge_length_ratio"]>master["max_edge_stretch_ratio"]):
            raise ValidationError("Corrected skin violates original-master deformation or topology bounds")
        correction=row.get("skin_correction")
        if (type(correction) is not dict or set(correction)!={"uncorrected_sha256","corrected_vertices","max_correction_local"} or
                not is_sha256(correction["uncorrected_sha256"]) or type(correction["corrected_vertices"]) is not int or
                not 0<=correction["corrected_vertices"]<=proof["neutral_vertex_count"] or
                not number(correction["max_correction_local"],0,data["model_baseline_diagonal_local"]*.03) or
                (correction["corrected_vertices"]==0) != (correction["max_correction_local"]<=1e-6)):
            raise ValidationError("Unbounded or incomplete per-frame native skin correction")
        if correction["corrected_vertices"]>=16: moved_frames+=1
    if moved_frames<2: raise ValidationError("Bound corrective skin did not measurably affect real posed geometry")


def validate_reopen_report(report: dict, bindings: dict, data: dict) -> None:
    keys={"status","bindings","frames_verified","uncorrected_skin_frames_verified","master_strain_frames_verified",
          "hip_frames_verified","skin_deformation_policy","original_master_unchanged","review_unchanged",
          "retargeting_verified","animation_visual_quality_verified","engine_import_verified"}
    count=data["source_frame_count"]
    if "hand_plane_proofs" in data:
        keys.add("hand_reference_planes_verified")
        if (type(report) is not dict or type(report.get("hand_reference_planes_verified")) is not int or
                report["hand_reference_planes_verified"]!=len(data["hand_plane_proofs"]["planes"])):
            raise ValidationError("Palm rest geometry was not independently reopened")
    neutral_reference=data.get("mesh_strain_reference")=="TRUE_NEUTRAL_BIND_V2"
    if neutral_reference:
        keys|={"mesh_strain_reference","first_pose_observation_frames_verified"}
        if (type(report) is not dict or report.get("mesh_strain_reference")!="TRUE_NEUTRAL_BIND_V2" or
                type(report.get("first_pose_observation_frames_verified")) is not int or report["first_pose_observation_frames_verified"]!=count):
            raise ValidationError("Neutral-reference observations were not independently reopened")
    if (type(report) is not dict or set(report)!=keys or report["status"]!="REAL_NATIVE_BODY_REVIEW_REOPENED" or
            report["bindings"]!=bindings or report["skin_deformation_policy"]!=POLICY or
            any(type(report[k]) is not int or report[k]!=count for k in ("frames_verified","uncorrected_skin_frames_verified","master_strain_frames_verified")) or
            type(report["hip_frames_verified"]) is not int or report["hip_frames_verified"]!=(count if "hip_anchor" in data else 0) or
            report["original_master_unchanged"] is not True or report["review_unchanged"] is not True or
            any(report[k] is not False for k in ("retargeting_verified","animation_visual_quality_verified","engine_import_verified"))):
        raise ValidationError("Saved native review did not independently reopen with complete bound/raw geometry")
