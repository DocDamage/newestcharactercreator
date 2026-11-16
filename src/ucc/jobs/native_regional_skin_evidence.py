"""Independent host checks for the closed regional skin and original-weight mask."""
from ucc.core.errors import ValidationError
from ucc.animations.source_rest_frames import is_sha256

MASK_NAME = "UCC_PRIVATE_REGIONAL_SKIN_MASK_UNAPPROVED"
SOURCE_GROUPS = ["spine05", "pelvis.L", "pelvis.R", "upperleg01.L", "upperleg01.R"]
COMMON = {"type": "CORRECTIVE_SMOOTH", "is_bound": True, "factor": .5,
          "iterations": 20, "smooth_type": "SIMPLE", "scale": 1., "rest_source": "BIND",
          "use_only_smooth": False, "use_pin_boundary": False, "vertex_group": "",
          "invert_vertex_group": False, "show_viewport": True, "show_render": True}
MODIFIERS = (
    {**COMMON, "name": "UCC_PRIVATE_REGIONAL_GLOBAL_UNAPPROVED", "smooth_type": "LENGTH_WEIGHTED"},
    {**COMMON, "name": "UCC_PRIVATE_REGIONAL_TORSO_UNAPPROVED", "factor": .75, "vertex_group": MASK_NAME},
)


def validate_regional_settings(proof: dict) -> None:
    mods = proof["modifiers"]
    if type(mods) is not list or len(mods) != 2:
        raise ValidationError("Regional skin requires its two ordered bound layers")
    for mod, expected in zip(mods, MODIFIERS):
        if (type(mod) is not dict or set(mod) != set(expected) or
                any(type(mod[k]) is not type(v) or mod[k] != v for k, v in expected.items())):
            raise ValidationError("Regional skin settings differ from the closed versioned policy")
    mask = proof["region_mask"]
    keys = {"name", "formula", "source_groups", "source_mesh_vertices", "weighted_vertices", "weights_sha256"}
    if (not is_sha256(proof["source_vertex_groups_sha256"]) or type(mask) is not dict or set(mask) != keys or
            mask["name"] != MASK_NAME or mask["formula"] != "MIN_ONE_SUM_ORIGINAL_DEFORM_WEIGHTS_V1" or
            type(mask["source_groups"]) is not list or mask["source_groups"] != SOURCE_GROUPS or
            type(mask["source_mesh_vertices"]) is not int or
            not proof["neutral_vertex_count"] <= mask["source_mesh_vertices"] <= 250000 or
            type(mask["weighted_vertices"]) is not int or not 16 <= mask["weighted_vertices"] <= mask["source_mesh_vertices"] or
            not is_sha256(mask["weights_sha256"])):
        raise ValidationError("Regional skin has no exact original-weight mask binding")
