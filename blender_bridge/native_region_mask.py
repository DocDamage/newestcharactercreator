"""Exact source-group signatures and one versioned nondeform correction mask."""
from hashlib import sha256
import math
import struct

MASK_NAME = "UCC_PRIVATE_REGIONAL_SKIN_MASK_UNAPPROVED"
SOURCE_GROUPS = ("spine05", "pelvis.L", "pelvis.R", "upperleg01.L", "upperleg01.R")


def source_group_signature(human, *, exclude=None):
    """Keep binary weights and membership order, including nonbone source groups."""
    digest = sha256()
    for group in human.vertex_groups:
        if group == exclude:
            continue
        digest.update(struct.pack("<I", group.index) + group.name.encode("utf-8") + b"\0")
    for vertex in human.data.vertices:
        rows = [row for row in vertex.groups if exclude is None or row.group != exclude.index]
        digest.update(struct.pack("<II", vertex.index, len(rows)))
        for row in rows:
            if not math.isfinite(row.weight) or not 0 <= row.weight <= 1.00001:
                raise ValueError("Regional correction found an invalid original vertex weight")
            digest.update(struct.pack("<If", row.group, float(row.weight)))
    return digest.hexdigest()


def expected_mask(human, rig):
    indices = set()
    for name in SOURCE_GROUPS:
        group, bone = human.vertex_groups.get(name), rig.data.bones.get(name)
        if group is None or bone is None or not bone.use_deform:
            raise ValueError("Regional correction requires the declared deform group: " + name)
        indices.add(group.index)
    values = []
    for vertex in human.data.vertices:
        values.append(min(1., sum(float(row.weight) for row in vertex.groups if row.group in indices)))
    if any(not math.isfinite(value) or not 0 <= value <= 1 for value in values):
        raise ValueError("Regional correction could not derive finite bounded mask weights")
    if sum(value > 0 for value in values) < 16:
        raise ValueError("Regional correction has no substantial original weight coverage")
    return values


def mask_signature(human, group):
    digest = sha256()
    weighted = 0
    for vertex in human.data.vertices:
        rows = [row for row in vertex.groups if row.group == group.index]
        if len(rows) > 1:
            raise ValueError("Regional correction has duplicate mask memberships")
        value = float(rows[0].weight) if rows else 0.
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("Regional correction mask weight is outside its exact policy")
        weighted += value > 0
        digest.update(struct.pack("<If", vertex.index, value))
    return {"name": MASK_NAME, "formula": "MIN_ONE_SUM_ORIGINAL_DEFORM_WEIGHTS_V1",
            "source_groups": list(SOURCE_GROUPS), "source_mesh_vertices": len(human.data.vertices),
            "weighted_vertices": weighted, "weights_sha256": digest.hexdigest()}


def create_mask(human, rig):
    if human.vertex_groups.get(MASK_NAME) is not None or rig.data.bones.get(MASK_NAME) is not None:
        raise ValueError("Regional correction refuses an occupied mask name")
    original = source_group_signature(human)
    values = expected_mask(human, rig)
    group = human.vertex_groups.new(name=MASK_NAME)
    try:
        for vertex, value in zip(human.data.vertices, values):
            if value > 0:
                group.add([vertex.index], value, "REPLACE")
        if source_group_signature(human, exclude=group) != original:
            raise ValueError("Regional correction changed original group memberships")
        return group, mask_signature(human, group)
    except BaseException:
        human.vertex_groups.remove(group)
        if source_group_signature(human) != original:
            raise ValueError("Regional mask failure did not restore original memberships")
        raise


def verify_mask(human, rig, proof, original_signature):
    group = human.vertex_groups.get(MASK_NAME)
    if (group is None or rig.data.bones.get(MASK_NAME) is not None or
            group.index != len(human.vertex_groups) - 1 or
            source_group_signature(human, exclude=group) != original_signature or
            mask_signature(human, group) != proof):
        raise ValueError("Regional mask, original groups or exact source weights changed")
    values = expected_mask(human, rig)
    digest = sha256()
    for vertex, value in zip(human.data.vertices, values):
        digest.update(struct.pack("<If", vertex.index, value))
    if digest.hexdigest() != proof["weights_sha256"]:
        raise ValueError("Regional mask does not match the fixed original-weight formula")
    return group
