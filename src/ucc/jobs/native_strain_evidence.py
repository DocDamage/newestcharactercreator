"""Native neutral-reference contract; arbitrary posed origins are observations."""
import math
from ucc.core.errors import ValidationError

LEGACY="FIRST_POSE_AND_NEUTRAL_V1"
NEUTRAL="TRUE_NEUTRAL_BIND_V2"


def validate_strain_reference(data: dict,profile: dict) -> bool:
    reference=profile.get("mesh_strain_reference",LEGACY)
    if reference not in (LEGACY,NEUTRAL) or data.get("mesh_strain_reference",LEGACY)!=reference:
        raise ValidationError("Native mesh-strain reference differs from its bound map")
    if reference==LEGACY:
        if "first_pose_relative_frames" in data or "first_pose_edge_strain" in data:
            raise ValidationError("Legacy native strain cannot use V2 observation fields")
        return False
    if (data.get("mesh_edge_strain")!=data.get("bind_edge_strain") or
            type(data.get("motion_quality_schema_version")) is not int or data["motion_quality_schema_version"]!=2):
        raise ValidationError("V2 native quality is not measured against true neutral bind skin")
    info=data.get("first_pose_edge_strain");bind=data.get("bind_edge_strain")
    fields={"evaluated_edge_count","measured_edge_count","degenerate_baseline_edges_excluded","evaluated_topology_sha256"}
    if (type(info) is not dict or set(info)!=fields or type(bind) is not dict or
            info["evaluated_topology_sha256"]!=bind.get("evaluated_topology_sha256") or
            info["evaluated_edge_count"]!=bind.get("evaluated_edge_count")):
        raise ValidationError("First-pose observations lack the actual evaluated topology")
    total,measured,excluded=(info[k] for k in ("evaluated_edge_count","measured_edge_count","degenerate_baseline_edges_excluded"))
    if any(type(v) is not int for v in (total,measured,excluded)) or not 16<=measured<=total<=750000 or excluded<0 or measured+excluded!=total:
        raise ValidationError("First-pose observation edge coverage differs")
    observed=data.get("first_pose_relative_frames")
    count=data.get("source_frame_count")
    if (type(count) is not int or type(observed) is not list or len(observed)!=count or
            type(data.get("full_timeline_frames")) is not list or len(data["full_timeline_frames"])!=count or
            type(data.get("bind_relative_frames")) is not list or len(data["bind_relative_frames"])!=count):
        raise ValidationError("Missing complete first-pose strain observations")
    for frame,(row,main,neutral) in enumerate(zip(observed,data["full_timeline_frames"],data["bind_relative_frames"]),1):
        if type(row) is not dict or set(row)!={"frame","max_edge_stretch_ratio","min_edge_length_ratio"} or type(row["frame"]) is not int or row["frame"]!=frame:
            raise ValidationError("Misordered first-pose strain observations")
        lo,hi=row["min_edge_length_ratio"],row["max_edge_stretch_ratio"]
        # This bound is JSON/numerical hygiene, NOT a deformation acceptance
        # threshold. True neutral ranges remain 0.05–4 for every actual frame.
        if (any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=1e15 for v in (lo,hi)) or lo>hi or
                (frame==1 and (abs(lo-1)>1e-6 or abs(hi-1)>1e-6))):
            raise ValidationError("Invalid first-pose strain observation")
        for k in ("max_edge_stretch_ratio","min_edge_length_ratio"):
            if main.get(k)!=neutral.get(k):raise ValidationError("V2 main quality rows differ from actual neutral-bind strain")
        if excluded==0 and bind.get("degenerate_baseline_edges_excluded")==0:
            first=data["bind_relative_frames"][0]
            first_lo,first_hi=first["min_edge_length_ratio"],first["max_edge_stretch_ratio"]
            current_lo,current_hi=neutral["min_edge_length_ratio"],neutral["max_edge_stretch_ratio"]
            if (lo<current_lo/first_hi-1e-6 or lo>current_lo/first_lo+1e-6 or
                    hi>current_hi/first_lo+1e-6 or hi<current_hi/first_hi-1e-6):
                raise ValidationError("First-pose observations contradict measured neutral edge envelopes")
    return True
