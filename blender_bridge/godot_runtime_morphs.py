"""Read-only fresh saved morph comparison against the authoritative source."""
from typing import Any
import numpy as np
from blender_bridge.expression_policy import TARGETS,keyname
from blender_bridge.godot_runtime_geometry import sampled_mesh
from blender_bridge.native_corrective import NAME


def verify_morphs(bpy: Any,human: Any,rig: Any,converted: Any) -> dict:
    names=[keyname(r,f) for r,f,_ in TARGETS];keys=converted.data.shape_keys
    if (keys is None or {k.name for k in keys.key_blocks}!={'Basis',*names}
            or any(k.value!=0. for k in keys.key_blocks) or keys.animation_data
            or any(keys.key_blocks[n].relative_key!=keys.key_blocks['Basis'] for n in names)):
        raise ValueError('Saved runtime copy lost its exact canonical neutral morphs')
    mods=[human.modifiers[0],human.modifiers[NAME],converted.modifiers[0]]
    states=[m.show_viewport for m in mods];pose=rig.data.pose_position;maximum=0.
    try:
        rig.data.pose_position='REST'
        for m in mods:m.show_viewport=False
        for name in [None,*names]:
            if name is not None:
                human.data.shape_keys.key_blocks[name].value=.5;keys.key_blocks[name].value=.5
            try:
                source=sampled_mesh(bpy,human)[0];candidate=sampled_mesh(bpy,converted)[0]
                error=float(np.max(np.linalg.norm(source.astype(np.float64)-candidate.astype(np.float64),axis=1)))
                if not np.isfinite(error) or error>1e-6:raise ValueError('Saved canonical morph differs from original source: '+str(name))
                maximum=max(maximum,error)
            finally:
                if name is not None:
                    human.data.shape_keys.key_blocks[name].value=0.;keys.key_blocks[name].value=0.
    finally:
        rig.data.pose_position=pose
        for mod,state in zip(mods,states):mod.show_viewport=state
        bpy.context.view_layer.update()
    return {'canonical_morphs_verified':12,'maximum_morph_position_error_m':maximum}
