"""Read-only installed-exporter/real-MPFB capability probe, not export proof.

No scene, model, animation or render is generated. The optional master is
opened with auto-execution disabled and must remain byte-identical.
"""
import argparse
from hashlib import file_digest
import json
from pathlib import Path
import sys

import bpy


PROPERTIES = (
    'export_format', 'use_selection', 'export_yup', 'export_apply',
    'export_skins', 'export_morph', 'export_morph_normal', 'export_morph_tangent',
    'export_def_bones', 'export_rest_position_armature', 'export_influence_nb',
    'export_all_influences', 'export_materials', 'export_animations',
    'export_animation_mode', 'export_force_sampling', 'export_frame_range',
    'export_frame_step', 'export_anim_slide_to_zero', 'export_morph_animation',
)


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


def inspect(master: Path | None) -> dict:
    properties = bpy.ops.export_scene.gltf.get_rna_type().properties
    options = {}
    for name in PROPERTIES:
        if name not in properties:
            continue
        prop = properties[name]
        value = {'type': prop.type, 'default': prop.default}
        if prop.type == 'ENUM':
            value['values'] = [item.identifier for item in prop.enum_items if item.identifier]
        options[name] = value
    result = {'status': 'ACTUAL_INSTALLED_GODOT_EXPORT_CAPABILITIES_INSPECTED',
        'blender_version': bpy.app.version_string, 'exporter_options': options,
        'missing_options': sorted(set(PROPERTIES)-options.keys()),
        'export_executed': False, 'engine_import_verified': False}
    if master is None:
        return result
    if master.is_symlink() or not master.is_file():
        raise ValueError('Probe master must be an existing regular file')
    before = digest(master)
    bpy.ops.wm.open_mainfile(filepath=str(master.resolve()), load_ui=False)
    rigs = [obj for obj in bpy.context.scene.objects if obj.type == 'ARMATURE']
    if len(rigs) != 1:
        raise ValueError('Probe expects exactly one actual MPFB armature')
    rig = rigs[0]
    deform = {bone.name for bone in rig.data.bones if bone.use_deform}
    meshes = []
    for obj in bpy.context.scene.objects:
        if obj.type != 'MESH':
            continue
        group_names = {group.index: group.name for group in obj.vertex_groups}
        maximum = max((sum(group.weight > 0 and group_names[group.group] in deform
                           for group in vertex.groups) for vertex in obj.data.vertices), default=0)
        keys = obj.data.shape_keys
        meshes.append({'vertices': len(obj.data.vertices), 'polygons': len(obj.data.polygons),
            'shape_key_count': len(keys.key_blocks) if keys else 0,
            'canonical_expression_keys': [key.name for key in keys.key_blocks
                if key.name.startswith('UCC_EXPR_V1_')] if keys else [],
            'max_positive_deform_influences': maximum,
            'modifiers': [{'type': mod.type, **({'preserve_volume': mod.use_deform_preserve_volume,
                'vertex_groups': mod.use_vertex_groups, 'bone_envelopes': mod.use_bone_envelopes}
                if mod.type == 'ARMATURE' else {})} for mod in obj.modifiers]})
    if digest(master) != before:
        raise ValueError('Read-only capability inspection changed the original master')
    result.update(master_sha256=before, master_unchanged=True, armature_count=1,
                  bone_count=len(rig.data.bones), deform_bone_count=len(deform), meshes=meshes)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--master', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    if args.out.exists() or args.out.is_symlink():
        raise ValueError('Capability output already exists; do not replace evidence')
    report = inspect(args.master)
    with args.out.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    print(report['status'], flush=True)
