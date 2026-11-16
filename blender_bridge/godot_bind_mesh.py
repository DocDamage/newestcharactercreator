"""Private MPFB bind-mesh conversion; static preview export stays independent."""
from dataclasses import dataclass
import math
from typing import Any

from blender_bridge.expression_policy import PREFIX, TARGETS, keyname
from blender_bridge.native_skin_stack import source_stack
from blender_bridge.godot_skin_weights import (
    POLICY as WEIGHT_POLICY, SERIALIZATION_POLICY, normalize_weights, serialization_weights,
)

SOURCE_ID = '_UCC_EXPORT_SOURCE_VERTEX_V1'


@dataclass(frozen=True, slots=True)
class GodotBindMesh:
    object: Any
    source_vertex_ids: tuple[int, ...]
    observation: dict


def _visible_sample(bpy: Any, human: Any) -> tuple[tuple[int, ...], tuple[tuple[float, ...], ...]]:
    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    evaluated = human.evaluated_get(graph)
    mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=graph)
    try:
        attribute = mesh.attributes.get(SOURCE_ID)
        if attribute is None or attribute.domain != 'POINT' or attribute.data_type != 'INT':
            raise ValueError('Static masks discarded the export source-vertex identity')
        return (tuple(row.value for row in attribute.data),
                tuple(tuple(float(value) for value in vertex.co) for vertex in mesh.vertices))
    finally:
        evaluated.to_mesh_clear()


def build_godot_bind_mesh(bpy: Any, human: Any, rig: Any) -> GodotBindMesh:
    """Bake active body/hand targets and masks, retaining exact admitted morphs.

    This creates an in-memory copy only. It rejects Blender-only correction
    stacks and dual-quaternion skinning instead of discarding their effects.
    The caller must independently verify the exported file in the engine.
    """
    if (bpy.data.objects.get('UCC_Godot_Private_Character') is not None
            or bpy.data.meshes.get('UCC_Godot_Private_Bind_Mesh') is not None):
        raise ValueError('Reserved private Godot candidate name already exists')
    states = source_stack(human, rig)
    if any(not math.isfinite(float(value)) or value <= 0 for obj in (human, rig) for value in obj.scale):
        raise ValueError('Godot candidate rejects negative, zero or nonfinite object scale')
    armature = human.modifiers[0]
    if (armature.use_deform_preserve_volume or armature.use_bone_envelopes
            or not armature.use_vertex_groups or armature.use_multi_modifier):
        raise ValueError('Godot candidate requires independently admitted linear vertex-group skinning')
    if rig.matrix_world.determinant() <= 0 or human.matrix_world.determinant() <= 0:
        raise ValueError('Godot candidate rejects reflected or singular object transforms')
    names = tuple(keyname(role, family) for role, family, _ in TARGETS)
    keys = human.data.shape_keys
    if keys is None or not keys.use_relative or {key.name for key in keys.key_blocks
                                               if key.name.startswith(PREFIX)} != set(names):
        raise ValueError('Godot candidate requires exactly the admitted twelve expression keys')
    basis = keys.key_blocks.get('Basis')
    if basis is None or any(keys.key_blocks[name].relative_key != basis for name in names):
        raise ValueError('Godot candidate requires Basis-relative canonical expression keys')
    if any(keys.key_blocks[name].value != 0 for name in names):
        raise ValueError('Bind conversion requires neutral canonical expression values')
    if human.data.attributes.get(SOURCE_ID) is not None:
        raise ValueError('Reserved export source-vertex attribute already exists')
    deform = {bone.name for bone in rig.data.bones if bone.use_deform}
    groups = {group.index: group.name for group in human.vertex_groups}
    original_pose = rig.data.pose_position
    original_armature_visibility = armature.show_viewport
    source_attribute = human.data.attributes.new(SOURCE_ID, 'INT', 'POINT')
    source_attribute.data.foreach_set('value', list(range(len(human.data.vertices))))
    created = mesh = None
    try:
        rig.data.pose_position = 'REST'
        # Bind coordinates precede the skin operation. Evaluating a REST
        # armature still rounds its object-space transforms; applying that
        # extra conversion before the exported skin can duplicate the error.
        armature.show_viewport = False
        ids, baseline = _visible_sample(bpy, human)
        if len(ids) != 13380 or len(set(ids)) != len(ids) or any(
                index < 0 or index >= len(human.data.vertices) for index in ids):
            raise ValueError('Godot candidate requires the complete pinned visible MPFB surface')
        graph = bpy.context.evaluated_depsgraph_get()
        mesh = bpy.data.meshes.new_from_object(human.evaluated_get(graph),
                                              preserve_all_data_layers=True, depsgraph=graph)
        mesh.name = 'UCC_Godot_Private_Bind_Mesh'
        created = bpy.data.objects.new('UCC_Godot_Private_Character', mesh)
        bpy.context.scene.collection.objects.link(created)
        created.parent = rig
        created.matrix_parent_inverse = human.matrix_parent_inverse.copy()
        created.matrix_basis = human.matrix_basis.copy()
        for group in human.vertex_groups:
            created.vertex_groups.new(name=group.name)
        maximum = 0; maximum_sum_error = 0.; nonunit = 0
        # Assign explicit original weights by retained source identity. A
        # topology-changing mask cannot silently shift weights to other vertices.
        for index, source_index in enumerate(ids):
            original = human.data.vertices[source_index]
            if any(not math.isfinite(group.weight) or not 0 <= group.weight <= 1.00001
                   for group in original.groups):
                raise ValueError('Invalid original vertex-group weight')
            converted, total = normalize_weights(tuple((groups[group.group], float(group.weight))
                for group in original.groups if groups[group.group] in deform))
            serialized = dict(serialization_weights(converted))
            maximum = max(maximum, len(converted))
            maximum_sum_error = max(maximum_sum_error, abs(total-1))
            nonunit += total != 1
            for group in original.groups:
                name = groups[group.group]
                weight = serialized.get(name, 0.) if name in deform else group.weight
                created.vertex_groups[name].add([index], weight, 'REPLACE')
        created.shape_key_add(name='Basis', from_mix=False).value = 0.
        for name in names:
            keys.key_blocks[name].value = 1.
            try:
                changed_ids, coordinates = _visible_sample(bpy, human)
            finally:
                keys.key_blocks[name].value = 0.
            if changed_ids != ids:
                raise ValueError('Expression changed masked source-vertex correspondence')
            target = created.shape_key_add(name=name, from_mix=False)
            target.data.foreach_set('co', [value for point in coordinates for value in point])
            target.slider_min = 0.; target.slider_max = .5
            target.value = 0.
        if mesh.attributes.get(SOURCE_ID) is not None:
            mesh.attributes.remove(mesh.attributes[SOURCE_ID])
        skin = created.modifiers.new('UCC_Godot_Linear_Skin', 'ARMATURE')
        skin.object = rig
        for name in ('use_vertex_groups', 'use_bone_envelopes', 'use_deform_preserve_volume',
                     'use_multi_modifier', 'show_viewport', 'show_render'):
            setattr(skin, name, states[0][name])
        if any(tuple(vertex.co) != point for vertex, point in zip(mesh.vertices, baseline)):
            raise ValueError('Private bind mesh differs from the actual evaluated source phenotype')
        observation = {'schema_version': 1, 'profile': 'MPFB_GODOT_BIND_MESH_V1',
            'source_vertices': len(human.data.vertices), 'visible_vertices': len(ids),
            'polygons': len(mesh.polygons), 'bone_count': len(rig.data.bones),
            'deform_bones': len(deform), 'max_bone_influences': maximum,
            'weight_conversion_policy': WEIGHT_POLICY,
            'weight_serialization_policy': SERIALIZATION_POLICY,
            'source_nonunit_weight_vertices': nonunit,
            'max_source_weight_sum_deviation': maximum_sum_error,
            'expression_keys': list(names), 'source_modifiers': states,
            'static_masks_baked': True, 'body_and_hand_targets_baked': True,
            'engine_import_verified': False, 'animation_verified': False}
        return GodotBindMesh(created, ids, observation)
    except BaseException:
        if created is not None:
            bpy.data.objects.remove(created, do_unlink=True)
        if mesh is not None:
            bpy.data.meshes.remove(mesh)
        raise
    finally:
        for name in names:
            keys.key_blocks[name].value = 0.
        rig.data.pose_position = original_pose
        armature.show_viewport = original_armature_visibility
        human.data.attributes.remove(source_attribute)
        bpy.context.view_layer.update()


def discard_godot_bind_mesh(bpy: Any, candidate: GodotBindMesh) -> None:
    """Remove only the copy owned by this conversion, never source data."""
    mesh = candidate.object.data
    action = mesh.shape_keys.animation_data.action if mesh.shape_keys.animation_data else None
    bpy.data.objects.remove(candidate.object, do_unlink=True)
    bpy.data.meshes.remove(mesh)
    if action is not None and action.users == 0:
        bpy.data.actions.remove(action)
