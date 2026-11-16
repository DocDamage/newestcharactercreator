"""Versioned regional skin on disposable previews; original weights stay exact."""
import math
import struct

from blender_bridge.native_corrective import SETTINGS, _bind
from blender_bridge.native_skin_stack import armature_state, source_stack
from blender_bridge.pose_deformation import _evaluated_vertices, _movement
from blender_bridge.bvh_review_timeline import evaluated_edges
from blender_bridge.native_region_mask import (
    MASK_NAME, create_mask, source_group_signature, verify_mask,
)

POLICY = "BOUND_REGIONAL_CORRECTIVE_SMOOTH_V2"
LAYER_SETTINGS = (
    {**SETTINGS, "iterations": 20, "smooth_type": "LENGTH_WEIGHTED"},
    {**SETTINGS, "iterations": 20, "factor": .75, "vertex_group": MASK_NAME},
)
LAYER_NAMES = ("UCC_PRIVATE_REGIONAL_GLOBAL_UNAPPROVED", "UCC_PRIVATE_REGIONAL_TORSO_UNAPPROVED")


def exact_points(a, b):
    return (len(a) == len(b) and
            b"".join(struct.pack("<fff", *p) for p in a) ==
            b"".join(struct.pack("<fff", *p) for p in b))


def verify_saved_layers(human, rig, original_stack, proof, original_groups_sha):
    """Audit persisted V2 state without rebinding, repairing or changing weights."""
    required = {"schema_version", "policy", "source_modifier_count", "review_modifier_count", "modifiers",
                "source_armature", "source_modifiers", "source_vertex_groups_sha256", "region_mask",
                "source_neutral_sha256", "bound_neutral_sha256", "neutral_vertex_count", "max_neutral_displacement_local"}
    mods = tuple(human.modifiers)
    if (type(proof) is not dict or set(proof) != required or type(proof["schema_version"]) is not int or
            proof["schema_version"] != 2 or proof["policy"] != POLICY or
            type(proof["source_modifier_count"]) is not int or proof["source_modifier_count"] != len(original_stack) or
            type(proof["review_modifier_count"]) is not int or proof["review_modifier_count"] != len(original_stack) + 2 or
            len(mods) != len(original_stack) + 2 or proof["source_modifiers"] != original_stack or
            proof["source_armature"] != original_stack[0] or
            source_stack(human, rig, modifiers=mods[:-2]) != original_stack or
            proof["source_vertex_groups_sha256"] != original_groups_sha or
            type(proof["modifiers"]) is not list or len(proof["modifiers"]) != 2):
        raise ValueError("Saved regional skin has different original or owned state")
    for mod, row, name, settings in zip(mods[-2:], proof["modifiers"], LAYER_NAMES, LAYER_SETTINGS):
        expected = {"name": name, "type": "CORRECTIVE_SMOOTH", "is_bound": True, **settings}
        if (type(row) is not dict or set(row) != set(expected) or
                any(type(row[k]) is not type(v) or row[k] != v for k, v in expected.items()) or
                mod.name != name or mod.type != "CORRECTIVE_SMOOTH" or not mod.is_bind or
                any(type(getattr(mod, k)) is not type(v) or getattr(mod, k) != v for k, v in settings.items())):
            raise ValueError("Saved regional skin has changed ordered settings or binding")
    verify_mask(human, rig, proof["region_mask"], original_groups_sha)
    return mods[-2:]


class RegionalCorrectiveSkin:
    """Own two fixed bound layers and one mask, preserving all V1 code paths."""
    def __init__(self, bpy, human, rig, original, original_sha):
        self.bpy, self.human, self.rig = bpy, human, rig
        self.original, self.original_sha = original, original_sha
        self.stack = tuple(human.modifiers)
        self.modifiers = []
        self.mask = None
        self.source_states = source_stack(human, rig)
        self.source_groups_sha = source_group_signature(human)
        self.armature = armature_state(self.stack[0])
        if (human.mode != "OBJECT" or rig.mode != "OBJECT" or
                not self.armature["use_vertex_groups"] or self.armature["use_bone_envelopes"] or
                self.armature["use_multi_modifier"] or not self.armature["show_viewport"] or
                not self.armature["show_render"] or any(m.name in LAYER_NAMES for m in self.stack)):
            raise ValueError("Regional correction requires ordinary visible object-mode source skin")
        edges = evaluated_edges(bpy, human)
        active, position = bpy.context.view_layer.objects.active, rig.data.pose_position
        selected = human.select_get()
        try:
            self.mask, self.mask_proof = create_mask(human, rig)
            raw, raw_sha = _evaluated_vertices(bpy, human)
            if raw_sha != original_sha or not exact_points(raw, original):
                raise ValueError("Regional nondeform mask changed original neutral skin")
            bpy.context.view_layer.objects.active = human
            human.select_set(True)
            rig.data.pose_position = "REST"
            bpy.context.view_layer.update()
            for name, settings in zip(LAYER_NAMES, LAYER_SETTINGS):
                mod = human.modifiers.new(name, "CORRECTIVE_SMOOTH")
                self.modifiers.append(mod)
                for key, value in settings.items():
                    setattr(mod, key, value)
                result = _bind(bpy, mod.name)
                if "FINISHED" not in result or not mod.is_bind:
                    raise ValueError("Blender did not bind every regional correction layer")
            rig.data.pose_position = position
            self.neutral, self.neutral_sha = _evaluated_vertices(bpy, human)
            if len(self.neutral) != len(original) or evaluated_edges(bpy, human) != edges:
                raise ValueError("Regional correction changed original neutral topology")
            error = max(math.dist(a, b) for a, b in zip(original, self.neutral))
            if not math.isfinite(error) or error > 1e-6:
                raise ValueError("Regional correction changed neutral shape beyond numerical tolerance")
            self.proof = {"schema_version": 2, "policy": POLICY,
                "source_modifier_count": len(self.stack), "review_modifier_count": len(self.stack) + 2,
                "modifiers": [{"name": n, "type": "CORRECTIVE_SMOOTH", "is_bound": True, **s}
                              for n, s in zip(LAYER_NAMES, LAYER_SETTINGS)],
                "source_armature": self.armature, "source_modifiers": self.source_states,
                "source_vertex_groups_sha256": self.source_groups_sha, "region_mask": self.mask_proof,
                "source_neutral_sha256": original_sha, "bound_neutral_sha256": self.neutral_sha,
                "neutral_vertex_count": len(original), "max_neutral_displacement_local": error}
            self.audit()
        except BaseException:
            self.remove()
            raise
        finally:
            rig.data.pose_position = position
            human.select_set(selected)
            bpy.context.view_layer.objects.active = active
            bpy.context.view_layer.update()

    def audit(self):
        if (len(self.modifiers) != 2 or tuple(self.human.modifiers) != (*self.stack, *self.modifiers) or
                source_stack(self.human, self.rig, modifiers=self.stack) != self.source_states):
            raise ValueError("Regional correction changed the original modifier stack or weights")
        for mod, name, settings in zip(self.modifiers, LAYER_NAMES, LAYER_SETTINGS):
            if (mod.name != name or mod.type != "CORRECTIVE_SMOOTH" or not mod.is_bind or
                    any(type(getattr(mod, k)) is not type(v) or getattr(mod, k) != v
                        for k, v in settings.items())):
                raise ValueError("Regional correction binding or ordered settings changed")
        verify_mask(self.human, self.rig, self.mask_proof, self.source_groups_sha)

    def measure_raw(self, corrected, diagonal):
        self.audit()
        for mod in self.modifiers:
            mod.show_viewport = False
        try:
            raw, digest = _evaluated_vertices(self.bpy, self.human)
        finally:
            for mod in self.modifiers:
                mod.show_viewport = True
            self.bpy.context.view_layer.update()
        if len(raw) != len(corrected):
            raise ValueError("Regional correction changed posed vertex count")
        moved, maximum = _movement(raw, corrected)
        if not math.isfinite(maximum) or maximum > diagonal * .03:
            raise ValueError("Private skin correction exceeds three percent of character bounds")
        return {"uncorrected_sha256": digest, "corrected_vertices": moved, "max_correction_local": maximum}

    def remove(self):
        for mod in reversed(self.modifiers):
            self.human.modifiers.remove(mod)
        self.modifiers.clear()
        if self.mask is not None:
            self.human.vertex_groups.remove(self.mask)
            self.mask = None
        if (tuple(self.human.modifiers) != self.stack or
                source_stack(self.human, self.rig) != self.source_states or
                source_group_signature(self.human) != self.source_groups_sha):
            raise ValueError("Regional correction cleanup did not restore exact source state")
