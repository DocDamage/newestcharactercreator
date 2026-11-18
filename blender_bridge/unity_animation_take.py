"""Export an isolated Unity take without extending the saved target Action."""

from contextlib import contextmanager
import math

from blender_bridge.fbx_source import matrix_values
from blender_bridge.godot_bind_mesh import build_godot_bind_mesh, discard_godot_bind_mesh
from blender_bridge.triangulated_export import discard_triangulated_copy, triangulated_copy
from ucc.export.unity_animation_recipe import FPS, SOURCE_FRAMES, VIRTUAL_FRAME


def validate_clock(scene, action) -> None:
    if ((scene.frame_start, scene.frame_end, scene.render.fps, scene.render.fps_base)
            != (1, SOURCE_FRAMES, FPS, 1.0) or list(action.frame_range) != [1., float(SOURCE_FRAMES)]):
        raise ValueError('Registered Unity source requires the exact 300-sample 30 Hz target Action')


def _curves(action):
    bags = [bag for layer in action.layers for strip in layer.strips for bag in strip.channelbags]
    if len(bags) != 1:
        raise ValueError('Unity take requires one registered Action channel bag')
    return list(bags[0].fcurves)


def extend_export_curves(curves) -> None:
    """Add neutral serialization defaults and the virtual endpoint to a copy only."""
    endpoints = []
    seen = set()
    for curve in curves:
        channel = curve.data_path, curve.array_index
        rotation = curve.data_path.startswith('pose.bones[') and curve.data_path.endswith('.rotation_quaternion')
        location = curve.data_path.startswith('pose.bones[') and curve.data_path.endswith('.location')
        points = curve.keyframe_points
        if (channel in seen or not ((rotation and 0 <= curve.array_index < 4) or
                                    (location and 0 <= curve.array_index < 3))
                or len(points) != SOURCE_FRAMES or any(point.interpolation != 'LINEAR'
                    or point.co.x != index or not math.isfinite(point.co.y) for index, point in enumerate(points, 1))):
            raise ValueError('Unity take needs only complete linear target pose channels')
        seen.add(channel)
        endpoints.append((curve, float(points[0].co.y), float(rotation and curve.array_index == 0)))
    if not endpoints:
        raise ValueError('Unity take has no registered motion channels')
    for curve, first, neutral in endpoints:
        for frame, value in ((0, neutral), (VIRTUAL_FRAME, first)):
            curve.keyframe_points.insert(frame, value, options={'FAST'}).interpolation = 'LINEAR'
        curve.update()


@contextmanager
def export_take(bpy, rig):
    scene = bpy.context.scene
    animation = rig.animation_data
    if animation is None:
        raise ValueError('Unity take requires the registered Action')
    original, original_slot = animation.action, animation.action_slot
    if original is None or original_slot is None or len(original.slots) != 1 or len(animation.nla_tracks) or len(animation.drivers):
        raise ValueError('Unity take requires the registered Action slot without NLA or drivers')
    validate_clock(scene, original)
    current = scene.frame_current
    exported = original.copy()
    try:
        exported.use_fake_user = False
        exported.use_frame_range = False
        slots = [slot for slot in exported.slots if slot.identifier == original_slot.identifier]
        if len(slots) != 1:
            raise ValueError('Unity export copy lost the registered Action slot')
        slot = slots[0]
        extend_export_curves(_curves(exported))
        animation.action = exported
        animation.action_slot = slot
        scene.frame_end = VIRTUAL_FRAME
        scene.frame_set(0)
        bpy.context.view_layer.update()
        for bone in rig.pose.bones:
            pose, rest = matrix_values(bone.matrix), matrix_values(bone.bone.matrix_local)
            if max(abs(x-y) for x, y in zip(pose, rest)) > 1e-6:
                raise ValueError('Unity FBX defaults differ from the true neutral rest rig')
        yield
    finally:
        animation.action = original
        animation.action_slot = original_slot
        scene.frame_end = SOURCE_FRAMES
        scene.frame_set(current)
        bpy.context.view_layer.update()
        if exported.users == 0:
            bpy.data.actions.remove(exported)


def export_animated_fbx(bpy, human, rig, path, verify_endpoint) -> None:
    candidate = build_godot_bind_mesh(bpy, human, rig)
    triangulated = None
    selected = list(bpy.context.selected_objects)
    active = bpy.context.view_layer.objects.active
    try:
        triangulated = triangulated_copy(bpy, candidate.object)
        bpy.ops.object.select_all(action='DESELECT')
        triangulated.select_set(True)
        rig.select_set(True)
        bpy.context.view_layer.objects.active = rig
        with export_take(bpy, rig):
            verify_endpoint()
            result = bpy.ops.export_scene.fbx(filepath=str(path), check_existing=False, use_selection=True,
                object_types={'ARMATURE', 'MESH'}, apply_unit_scale=True, apply_scale_options='FBX_SCALE_UNITS',
                global_scale=1., axis_forward='-Z', axis_up='Y', add_leaf_bones=False, use_armature_deform_only=False,
                bake_anim=True, bake_anim_use_all_bones=True, bake_anim_use_nla_strips=False,
                bake_anim_use_all_actions=False, bake_anim_force_startend_keying=True, bake_anim_step=1.,
                bake_anim_simplify_factor=0., mesh_smooth_type='FACE', use_mesh_modifiers=False,
                path_mode='STRIP', embed_textures=False)
            if result != {'FINISHED'}:
                raise ValueError('Blender did not save the registered Unity animation FBX')
    finally:
        if triangulated is not None:
            discard_triangulated_copy(bpy, triangulated)
        discard_godot_bind_mesh(bpy, candidate)
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected:
            if obj.name in bpy.data.objects:
                obj.select_set(True)
        bpy.context.view_layer.objects.active = active
