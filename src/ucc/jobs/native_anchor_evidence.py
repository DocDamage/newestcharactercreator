"""Independent hip-trajectory/root-pivot validation using native source matrices."""
import math
from ucc.animations import native_math as nm
from ucc.core.errors import ValidationError

POLICY = "SOURCE_HIP_MIDPOINT_V1"
LEGACY = "ARMATURE_ORIGIN_DISPLACEMENT_V1"


def midpoint(points):
    return [sum(p[i] for p in points)/len(points) for i in range(3)]


def anchor_context(data, profile, source_points, target_points):
    policy = profile.get("root_motion_policy", LEGACY)
    if policy != POLICY:
        if "hip_anchor" in data or "root_motion_policy" in data:
            raise ValidationError("Legacy native profile cannot claim hip-anchor verification")
        return None
    proof = data.get("hip_anchor")
    names = [profile["landmarks"][key] for key in ("left_hip", "right_hip")]
    source_bind = midpoint([source_points[n["source"]] for n in names])
    target_bind = midpoint([target_points[key] for key in ("left_hip", "right_hip")])
    if (data.get("root_motion_policy") != POLICY or type(proof) is not dict or
            set(proof) != {"source_bones", "target_bones", "source_bind_midpoint_world", "target_bind_midpoint_world", "frames_measured", "max_residual_world"} or
            proof["source_bones"] != [n["source"] for n in names] or proof["target_bones"] != [n["target"] for n in names] or
            type(proof["frames_measured"]) is not int or proof["frames_measured"] != data["source_frame_count"] or
            type(proof["max_residual_world"]) not in (int,float) or
            not math.isfinite(proof["max_residual_world"]) or not 0 <= proof["max_residual_world"] <= 1e-4):
        raise ValidationError("Missing or unbounded native hip-anchor proof")
    for key, expected in (("source_bind_midpoint_world", source_bind), ("target_bind_midpoint_world", target_bind)):
        value = proof[key]
        if (type(value) is not list or len(value) != 3 or
                any(type(v) not in (int,float) or not math.isfinite(v) for v in value) or math.dist(value,expected) > 1e-5):
            raise ValidationError("Native hip-anchor bind point differs from anatomical landmarks")
    return {"names":names, "source_bind":source_bind, "target_bind":target_bind,
            "individual_target_bind":[target_points[k] for k in ("left_hip", "right_hip")], "max_error":0.}


def check_anchor_frame(context, src, row, data, source_indices, root_bind, poses):
    """No worker root/hip position summaries substitute for original matrices."""
    world = nm.rows(src["armature_world"])
    source_hips = [nm.point(world,[src["poses"][source_indices[n["source"]]][i*4+3] for i in range(3)]) for n in context["names"]]
    source_mid = midpoint(source_hips)
    expected_hip = [context["target_bind"][i]+data["root_motion_scale"]*sum(
        data["source_to_target_axes"][i][j]*(source_mid[j]-context["source_bind"][j]) for j in range(3)) for i in range(3)]
    rotation,_ = nm.rotation(poses[0],target_noise=True)
    bind_rotation = data["reference_proofs"][0]["target_bind_rotation"]
    delta = nm.product(rotation,nm.transposed(bind_rotation))
    root = [poses[0][i*4+3] for i in range(3)]
    offset = [context["target_bind"][i]-root_bind[i] for i in range(3)]
    expected_root = [expected_hip[i]-sum(delta[i][j]*offset[j] for j in range(3)) for i in range(3)]
    if math.dist(root,expected_root) > 1e-4:
        raise ValidationError("Native root rotates around the wrong hip anchor")
    pair_indices = {p["target"]:i for i,p in enumerate(data["mapped_pairs"])}
    actual_hips = []
    for name,bind in zip(context["names"],context["individual_target_bind"]):
        pose = poses[pair_indices[name["target"]]]
        point = [pose[i*4+3] for i in range(3)]
        rigid = [root[i]+sum(delta[i][j]*(bind[j]-root_bind[j]) for j in range(3)) for i in range(3)]
        if math.dist(point,rigid) > 1e-4:
            raise ValidationError("Native hip heads are not rigidly attached through neutral helpers")
        actual_hips.append(point)
    actual_mid = midpoint(actual_hips)
    reported = row.get("hip_midpoint_world")
    if (type(reported) is not list or len(reported) != 3 or
            any(type(v) not in (int,float) or not math.isfinite(v) for v in reported) or math.dist(reported,actual_mid) > 1e-6):
        raise ValidationError("Native measured hip midpoint differs from actual target matrices")
    error = math.dist(actual_mid,expected_hip)
    if error > 1e-4:
        raise ValidationError("Native source hip trajectory was not preserved")
    context["max_error"] = max(context["max_error"],error)


def finish_anchor(context, data):
    if context is not None and abs(context["max_error"]-data["hip_anchor"]["max_residual_world"]) > 1e-6:
        raise ValidationError("Native hip-anchor residual summary omits measured error")
