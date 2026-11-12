"""Bound corrective skin on disposable native previews; never edit source data."""
from __future__ import annotations
import math
from typing import Any

from blender_bridge.pose_deformation import _evaluated_vertices, _movement
from blender_bridge.bvh_review_timeline import evaluated_edges
from blender_bridge.native_skin_stack import armature_state, source_stack

POLICY = "BOUND_CORRECTIVE_SMOOTH_V1"
NAME = "UCC_PRIVATE_BOUND_CORRECTIVE_UNAPPROVED"
SETTINGS = {"factor": .5, "iterations": 5, "smooth_type": "SIMPLE", "scale": 1.,
            "rest_source": "BIND", "use_only_smooth": False, "use_pin_boundary": False,
            "vertex_group": "", "invert_vertex_group": False, "show_viewport": True, "show_render": True}


def _bind(bpy: Any, name: str):
    return bpy.ops.object.correctivesmooth_bind(modifier=name)


class CorrectiveSkin:
    """Own exactly one temporary modifier, including bind-failure cleanup."""
    def __init__(self, bpy: Any, human: Any, rig: Any, original: tuple, original_sha: str):
        self.bpy, self.human, self.rig = bpy, human, rig
        self.original, self.original_sha = original, original_sha
        self.stack = tuple(human.modifiers)
        self.modifier = None
        if human.mode != "OBJECT" or rig.mode != "OBJECT":
            raise ValueError("Bound corrective preview requires an object-mode human and rig")
        self.source_states = source_stack(human,rig)
        self.armature = armature_state(self.stack[0])
        if (not self.armature["use_vertex_groups"] or self.armature["use_bone_envelopes"] or
                self.armature["use_multi_modifier"] or not self.armature["show_viewport"] or not self.armature["show_render"] or
                any(m.name == NAME for m in self.stack)):
            raise ValueError("Bound corrective preview needs ordinary visible vertex-group skinning")
        edges = evaluated_edges(bpy,human)
        active, position = bpy.context.view_layer.objects.active, rig.data.pose_position
        try:
            mod = human.modifiers.new(NAME,"CORRECTIVE_SMOOTH")
            self.modifier = mod
            for key,value in SETTINGS.items(): setattr(mod,key,value)
            bpy.context.view_layer.objects.active = human
            rig.data.pose_position = "REST"
            bpy.context.view_layer.update()
            result = _bind(bpy,mod.name)
            if "FINISHED" not in result or not mod.is_bind:
                raise ValueError("Blender did not bind private corrective smoothing")
            rig.data.pose_position = position
            self.neutral, self.neutral_sha = _evaluated_vertices(bpy,human)
            if len(self.neutral) != len(original) or evaluated_edges(bpy,human) != edges:
                raise ValueError("Bound corrective smoothing changed neutral topology")
            error = max(math.dist(a,b) for a,b in zip(original,self.neutral))
            if not math.isfinite(error) or error > 1e-6:
                raise ValueError("Bound corrective smoothing changed neutral shape beyond numerical tolerance")
            self.proof = {"schema_version":1,"policy":POLICY,"source_modifier_count":len(self.stack),"review_modifier_count":len(self.stack)+1,
                "modifier":{"name":NAME,"type":"CORRECTIVE_SMOOTH","is_bound":True,**SETTINGS},
                "source_armature":self.armature,"source_modifiers":self.source_states,"source_neutral_sha256":original_sha,
                "bound_neutral_sha256":self.neutral_sha,"neutral_vertex_count":len(original),
                "max_neutral_displacement_local":error}
            self.audit()
        except BaseException:
            self.remove()
            raise
        finally:
            rig.data.pose_position = position
            bpy.context.view_layer.objects.active = active
            bpy.context.view_layer.update()

    def audit(self) -> None:
        mod = self.modifier
        if (mod is None or tuple(self.human.modifiers) != (*self.stack,mod) or not mod.is_bind or
                mod.name != NAME or mod.type != "CORRECTIVE_SMOOTH" or
                any(type(getattr(mod,k)) is not type(v) or getattr(mod,k) != v for k,v in SETTINGS.items()) or
                armature_state(self.stack[0]) != self.armature):
            raise ValueError("Private corrective binding, settings or source modifier stack changed")
        # The owned modifier is last. Inspect static source masks without
        # removing or disabling them; topology is also checked every frame.
        for mod,state in zip(self.stack[1:],self.source_states[1:]):
            if any(getattr(mod,k)!=v for k,v in state.items() if k not in {"vertex_group_sha256","source_mesh_vertices"}):
                raise ValueError("Private corrective preview changed source mask settings")

    def measure_raw(self, corrected: tuple, diagonal: float) -> dict:
        """Read the same keyed pose with the owned modifier temporarily disabled."""
        self.audit()
        self.modifier.show_viewport = False
        try: raw, digest = _evaluated_vertices(self.bpy,self.human)
        finally:
            self.modifier.show_viewport = True
            self.bpy.context.view_layer.update()
        if len(raw) != len(corrected): raise ValueError("Corrective preview changed posed vertex count")
        moved, maximum = _movement(raw,corrected)
        if not math.isfinite(maximum) or maximum > diagonal*.03:
            raise ValueError("Private skin correction exceeds three percent of character bounds")
        return {"uncorrected_sha256":digest,"corrected_vertices":moved,"max_correction_local":maximum}

    def remove(self) -> None:
        if self.modifier is not None:
            self.human.modifiers.remove(self.modifier)
            self.modifier = None
        if tuple(self.human.modifiers) != self.stack or source_stack(self.human,self.rig) != self.source_states:
            raise ValueError("Private corrective cleanup did not preserve the original modifier stack")
