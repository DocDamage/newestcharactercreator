"""Serialize one isolated 30 Hz take with the admitted Unreal FBX axes and units."""

from pathlib import Path
from typing import Any

from blender_bridge.fbx_source import matrix_values
from blender_bridge.godot_bind_mesh import build_godot_bind_mesh, discard_godot_bind_mesh
from blender_bridge.triangulated_export import discard_triangulated_copy, triangulated_copy
from blender_bridge.unity_animation_take import export_take
from blender_bridge.unreal_source_reference import portable_export_header
from ucc.export.unreal_animation_recipe import FBX_BASIS_MODEL, VIRTUAL_FRAME
from ucc.export.unreal_blender_recipe import EXPORT_OPTIONS


ANIMATED_EXPORT_OPTIONS = {
    **EXPORT_OPTIONS,
    'bake_anim': True,
    'bake_anim_use_all_bones': True,
    'bake_anim_use_nla_strips': False,
    'bake_anim_use_all_actions': False,
    'bake_anim_force_startend_keying': True,
    'bake_anim_step': 1.0,
    'bake_anim_simplify_factor': 0.0,
    'path_mode': 'STRIP',
}


def _world_pose(rig: Any) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(matrix_values(rig.matrix_world @ bone.matrix)) for bone in rig.pose.bones)


def _verify_seam(bpy: Any, rig: Any) -> None:
    scene = bpy.context.scene
    try:
        scene.frame_set(1)
        bpy.context.view_layer.update()
        first = _world_pose(rig)
        scene.frame_set(VIRTUAL_FRAME)
        bpy.context.view_layer.update()
        if not first or _world_pose(rig) != first:
            raise ValueError('Unreal export virtual endpoint changed the first sampled world pose')
    finally:
        # The FBX exporter takes its unanimated defaults from the current pose.
        scene.frame_set(0)
        bpy.context.view_layer.update()


def serialize_prepared_animated_fbx(bpy: Any, mesh: Any, rig: Any, path: Path) -> None:
    """Export an already prepared triangle mesh and a private copy of its bound rig."""
    if path.suffix.lower() != '.fbx' or path.exists() or path.is_symlink():
        raise ValueError('Unreal animation needs a fresh FBX destination')
    if bpy.data.objects.get(FBX_BASIS_MODEL) is not None:
        raise ValueError('Reserved Unreal animation basis name is occupied')
    if (rig.type != 'ARMATURE' or rig.data.pose_position != 'POSE' or mesh.type != 'MESH'
            or len(mesh.modifiers) != 1 or mesh.modifiers[0].type != 'ARMATURE'
            or mesh.modifiers[0].object != rig or not mesh.data.polygons
            or any(len(polygon.vertices) != 3 for polygon in mesh.data.polygons)):
        raise ValueError('Unreal animation needs one prepared triangle mesh and its posed armature')

    scene, view = bpy.context.scene, bpy.context.view_layer
    selected, active = list(bpy.context.selected_objects), view.objects.active
    export_rig = export_mesh = armature = None
    try:
        export_rig = rig.copy()
        armature = rig.data.copy()
        export_rig.data = armature
        # Unreal's legacy importer strips the special Armature name.
        export_rig.name = FBX_BASIS_MODEL
        export_rig.parent = None
        export_rig.matrix_world = rig.matrix_world.copy()
        scene.collection.objects.link(export_rig)

        export_mesh = mesh.copy()
        export_mesh.parent = export_rig
        export_mesh.matrix_world = mesh.matrix_world.copy()
        export_mesh.modifiers[0].object = export_rig
        scene.collection.objects.link(export_mesh)
        bpy.ops.object.select_all(action='DESELECT')
        export_mesh.select_set(True)
        export_rig.select_set(True)
        view.objects.active = export_rig
        view.update()
        options = dict(ANIMATED_EXPORT_OPTIONS, object_types=set(ANIMATED_EXPORT_OPTIONS['object_types']))
        # The existing take context copies the sole dense Action, checks frame
        # zero against true rest, and branches the virtual seam from frame one.
        with export_take(bpy, export_rig):
            _verify_seam(bpy, export_rig)
            with portable_export_header(bpy):
                result = bpy.ops.export_scene.fbx(filepath=str(path), **options)
            if result != {'FINISHED'} or not path.is_file() or path.is_symlink() or not path.stat().st_size:
                raise ValueError('Blender did not save the Unreal animated FBX')
    finally:
        if export_mesh is not None:
            bpy.data.objects.remove(export_mesh, do_unlink=True)
        if export_rig is not None:
            bpy.data.objects.remove(export_rig, do_unlink=True)
        if armature is not None:
            bpy.data.armatures.remove(armature)
        bpy.ops.object.select_all(action='DESELECT')
        for obj in selected:
            if obj.name in bpy.data.objects:
                obj.select_set(True)
        view.objects.active = active


def export_animated_fbx(bpy: Any, human: Any, rig: Any, path: Path) -> None:
    """Prepare an admitted uncorrected MPFB donor and export one Unreal take."""
    candidate = build_godot_bind_mesh(bpy, human, rig)
    triangulated = None
    try:
        triangulated = triangulated_copy(bpy, candidate.object)
        serialize_prepared_animated_fbx(bpy, triangulated, rig, path)
    finally:
        if triangulated is not None:
            discard_triangulated_copy(bpy, triangulated)
        discard_godot_bind_mesh(bpy, candidate)
