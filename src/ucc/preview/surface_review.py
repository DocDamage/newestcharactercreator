"""Immutable, bounded surface-review metadata; no mesh or UI runtime imports."""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from ucc.core.errors import ValidationError
from ucc.animations.source_rest_frames import is_sha256
from ucc.jobs.native_evidence import bound_file
from ucc.jobs.native_skin_evidence import validate_reopen_report

POLICY="HAND_OPPOSITE_UPPER_LIMB_TRIANGLES_V1"
REASONS={"HAND_BRANCHES_UNAVAILABLE","WEIGHTED_REGIONS_UNAVAILABLE","SURFACE_WORKLOAD_EXCEEDED"}
REGIONS={"left_hand","right_hand","left_arm","right_arm"}


@dataclass(frozen=True,slots=True)
class SurfaceReview:
    status: str
    reason: str
    triangles: tuple[tuple[int,...],...]
    pairs: tuple[tuple[int,int],...]
    triangle_hashes: tuple[str,...]

    @property
    def flagged_frames(self) -> tuple[int,...]:
        return tuple(i for i,p in enumerate(self.pairs) if sum(p)>0)


def validate_surface_verification(report: dict,bindings: dict,timeline: dict,contact_sha: str,world_matrix: list) -> None:
    fields={"status","bindings","frames_verified","saved_review_verification","world_matrix","originals_unchanged","contact_quality_verified"}
    if (type(report) is not dict or set(report)!=fields or report["status"]!="REAL_NATIVE_SURFACE_REVIEW_VERIFIED" or
            report["bindings"]!={**bindings,"surface_review_sha256":contact_sha} or
            type(report["frames_verified"]) is not int or report["frames_verified"]!=timeline["source_frame_count"] or
            type(report['world_matrix']) is not list or len(report['world_matrix'])!=16 or
            any(type(v) not in (int,float) or not -10000<=v<=10000 for v in report['world_matrix']) or
            report['world_matrix']!=world_matrix or report["originals_unchanged"] is not True or report["contact_quality_verified"] is not False):
        raise ValidationError("Surface inspection was not independently reproduced")
    validate_reopen_report(report["saved_review_verification"],bindings,timeline)


def read_surface_review(folder: Path,record: dict,bindings: dict,timeline: dict,profile: dict,
                        triangle_count: int,vertex_count: int,verification: dict,world_matrix: list,*,cancel_check=lambda:None) -> SurfaceReview:
    path=bound_file(folder,record,"motion_contacts.json",16*1024*1024,cancel_check=cancel_check)
    validate_surface_verification(verification,bindings,timeline,record["sha256"],world_matrix)
    def pairs(rows):
        out={}
        for k,v in rows:
            if k in out:raise ValidationError("Duplicate surface-review field")
            out[k]=v
        return out
    with path.open('rb') as stream:payload=stream.read(16*1024*1024+1)
    if len(payload)!=record["bytes"] or sha256(payload).hexdigest()!=record["sha256"]:raise ValidationError("Surface review changed while reading")
    try:data=json.loads(payload,object_pairs_hook=pairs,parse_constant=lambda _v:(_ for _ in ()).throw(ValidationError("Nonfinite surface review")))
    except (ValueError,UnicodeError,RecursionError) as error:raise ValidationError("Invalid surface-review JSON") from error
    fields={"schema_version","policy","bindings","status","reason","hands","region_bones","region_vertex_counts","frame_count","frames","contact_quality_verified","engine_import_verified"}
    count=timeline["source_frame_count"]
    if (type(data) is not dict or set(data)!=fields or type(data["schema_version"]) is not int or data["schema_version"]!=1 or
            data["policy"]!=POLICY or data["bindings"]!=bindings or type(data["status"]) is not str or data["status"] not in {"CHECKED","UNAVAILABLE"} or
            type(data["reason"]) is not str or (data["reason"]!="" if data["status"]=="CHECKED" else data["reason"] not in REASONS) or
            type(data["frame_count"]) is not int or data["frame_count"]!=count or type(data["frames"]) is not list or len(data["frames"])!=count or
            data["contact_quality_verified"] is not False or data["engine_import_verified"] is not False):
        raise ValidationError("Surface-review policy, flags or complete coverage differs")
    if (type(profile) is not dict or type(profile.get('landmarks')) is not dict or
            any(type(profile['landmarks'].get(s+'_hand')) is not dict or
                type(profile['landmarks'][s+'_hand'].get('target')) is not str for s in ('left','right'))):
        raise ValidationError("Surface review needs its bound mapping profile")
    if data["hands"]!={s:profile["landmarks"][s+"_hand"]["target"] for s in ("left","right")}:
        raise ValidationError("Surface-review hands differ from the selected character map")
    bones=data["region_bones"];counts=data["region_vertex_counts"]
    if type(bones) is not dict or type(counts) is not dict or set(bones) not in (set(),REGIONS) or set(counts) not in (set(),REGIONS):
        raise ValidationError("Invalid surface region identity")
    mapped=timeline.get('mapped_pairs');helpers=timeline.get('neutral_target_helpers')
    if (type(mapped) is not list or len(mapped)>64 or any(type(r) is not dict or type(r.get('target')) is not str for r in mapped) or
            type(helpers) is not list or len(helpers)>256 or any(type(n) is not str for n in helpers)):
        raise ValidationError('Surface review needs validated target rig names')
    known={r["target"] for r in mapped}|set(helpers)
    selected=set()
    for key,names in bones.items():
        if (type(names) is not list or not 1<=len(names)<=256 or any(type(n) is not str or n not in known for n in names) or
                len(set(names))!=len(names) or selected.intersection(names)):
            raise ValidationError("Surface regions must be disjoint actual rig bones")
        selected.update(names)
    if any(type(v) is not int or not 0<=v<=vertex_count for v in counts.values()):raise ValidationError("Invalid surface region counts")
    if data["status"]=="CHECKED" and (set(bones)!=REGIONS or set(counts)!=REGIONS or not all(counts.values()) or sum(counts.values())>vertex_count or
            any(data["hands"][s] not in bones[s+"_hand"] for s in ("left","right"))):
        raise ValidationError("Checked surface review lacks complete weighted hand/limb regions")
    highlights=0;triangles=[];pair_counts=[];hashes=[]
    for frame,(row,expected) in enumerate(zip(data["frames"],timeline["full_timeline_frames"]),1):
        cancel_check()
        if (type(row) is not dict or set(row)!={"frame","skin_sha256","triangle_sha256","left","right"} or
                type(row["frame"]) is not int or row["frame"]!=frame or row["skin_sha256"]!=expected["evaluated_sha256"] or not is_sha256(row["triangle_sha256"])):
            raise ValidationError("Surface-review frame/skin/topology binding differs")
        ids=set();numbers=[]
        for side in ("left","right"):
            hit=row[side]
            if data["status"]=="UNAVAILABLE":
                if hit is not None:raise ValidationError("Unavailable review contains partial contact verdicts")
                numbers.append(0);continue
            if (type(hit) is not dict or set(hit)!={"pair_count","pair_sha256","hand_triangles","opposite_arm_triangles"} or
                    type(hit["pair_count"]) is not int or not 0<=hit["pair_count"]<=5_000_000 or not is_sha256(hit["pair_sha256"])):
                raise ValidationError("Invalid surface triangle-pair record")
            lists=[hit["hand_triangles"],hit["opposite_arm_triangles"]]
            for value in lists:
                if (type(value) is not list or len(value)>triangle_count or any(type(i) is not int or not 0<=i<triangle_count for i in value) or
                        value!=sorted(set(value)) or len(value)>hit["pair_count"] or bool(value)!=bool(hit["pair_count"])):
                    raise ValidationError("Invalid surface highlight triangle indices")
                ids.update(value);highlights+=len(value)
            if set(lists[0])&set(lists[1]):raise ValidationError("Hand and opposite limb share a triangle")
            if not hit["pair_count"] and hit["pair_sha256"]!=sha256().hexdigest():raise ValidationError("Empty surface-pair digest differs")
            numbers.append(hit["pair_count"])
        triangles.append(tuple(sorted(ids)));pair_counts.append(tuple(numbers));hashes.append(row["triangle_sha256"])
    if highlights>1_000_000:raise ValidationError("Surface highlights exceed complete workload limit")
    return SurfaceReview(data["status"],data["reason"],tuple(triangles),tuple(pair_counts),tuple(hashes))
