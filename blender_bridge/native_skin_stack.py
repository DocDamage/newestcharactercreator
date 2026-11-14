"""Read-only armature/static-mask signatures for native corrective previews."""
from hashlib import sha256
import math
import struct
from typing import Any


def armature_state(mod: Any) -> dict:
    return {"name":mod.name,"type":mod.type,"rig_object":mod.object.name,
            **{key:getattr(mod,key) for key in ("use_vertex_groups","use_bone_envelopes",
                "use_deform_preserve_volume","use_multi_modifier","show_viewport","show_render")}}


def source_stack(human: Any, rig: Any, *, include_weights: bool=True, modifiers=None) -> list[dict]:
    mods=tuple(human.modifiers) if modifiers is None else tuple(modifiers)
    if not 1<=len(mods)<=5 or mods[0].type!="ARMATURE" or mods[0].object!=rig:
        raise ValueError("Corrective preview needs one armature followed only by static vertex-group masks")
    states=[armature_state(mods[0])]
    for mod in mods[1:]:
        if (mod.type!="MASK" or mod.mode!="VERTEX_GROUP" or mod.use_smooth or mod.armature is not None or
                not mod.show_viewport or not mod.show_render or not math.isfinite(mod.threshold) or not 0<=mod.threshold<=1 or
                not mod.vertex_group or human.vertex_groups.get(mod.vertex_group) is None):
            raise ValueError("Corrective preview cannot reinterpret nonstatic or unsupported source modifiers")
        state={"name":mod.name,"type":"MASK","mode":mod.mode,"vertex_group":mod.vertex_group,
               "invert_vertex_group":mod.invert_vertex_group,"threshold":float(mod.threshold),
               "use_smooth":False,"show_viewport":True,"show_render":True,"source_mesh_vertices":len(human.data.vertices)}
        if include_weights:
            index=human.vertex_groups[mod.vertex_group].index
            digest=sha256(struct.pack("<I",len(human.data.vertices)))
            digest.update(mod.vertex_group.encode("utf-8"))
            for vertex in human.data.vertices:
                for group in vertex.groups:
                    if group.group==index:
                        if not math.isfinite(group.weight) or not 0<=group.weight<=1.00001:
                            raise ValueError("Invalid source mask weight")
                        digest.update(struct.pack("<If",vertex.index,float(group.weight)))
            state["vertex_group_sha256"]=digest.hexdigest()
        states.append(state)
    return states
