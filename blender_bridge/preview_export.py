"""Read-only geometry export for the UCC Qt static preview.

Executed inside an isolated Blender process with --disable-autoexec, on a
private copy of the existing master. No generated assets are committed here.
This is deliberately a *mesh surface* preview: no materials, image textures,
animations, morph playback, skinning or game-engine export certification.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

MAX_PREVIEW_BYTES = 128 * 1024 * 1024
MAX_SELECTED_VERTICES = 250_000
MAX_SELECTED_MESHES = 64


class PreviewExportError(RuntimeError):
    """The source master cannot be converted safely to a static GLB preview."""


def export_static_glb(bpy: Any, source: Path, destination: Path) -> dict:
    if source.suffix.lower() != ".blend" or not source.is_file() or source.is_symlink():
        raise PreviewExportError("Expected a regular staged Blender master")
    if destination.exists() or destination.is_symlink() or destination.suffix.lower() != ".glb":
        raise PreviewExportError("Preview GLB destination must be a new regular path")

    bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False)
    scene = bpy.context.scene
    # The default Blender startup cube is not a humanoid. Select only
    # substantial mesh objects from the opened scene; do not export the
    # scene's cameras, lights or optional asset collection contents.
    meshes = [
        obj for obj in scene.objects
        if obj.type == "MESH" and len(obj.data.vertices) > 100
    ]
    count = sum(len(obj.data.vertices) for obj in meshes)
    if not meshes or len(meshes) > MAX_SELECTED_MESHES or not (
        101 <= count <= MAX_SELECTED_VERTICES
    ):
        raise PreviewExportError("No bounded, substantial humanoid meshes in saved master")

    # A plain export with export_morph=False can export the original Basis,
    # ignoring active MPFB shape keys. Bake each *evaluated* mesh into a new,
    # unrigged in-memory object, so GLB positions reflect the current phenotype.
    # The original scene and saved .blend are never written to disk.
    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    baked = []
    total_baked = 0
    for index, original in enumerate(meshes):
        evaluated = original.evaluated_get(graph)
        mesh = bpy.data.meshes.new_from_object(
            evaluated, preserve_all_data_layers=False, depsgraph=graph,
        )
        total_baked += len(mesh.vertices)
        if not 100 < total_baked <= MAX_SELECTED_VERTICES:
            bpy.data.meshes.remove(mesh)
            raise PreviewExportError("Evaluated Blender preview mesh exceeds safe limits")
        temporary = bpy.data.objects.new(f"UCC_Evaluated_Static_{index}", mesh)
        scene.collection.objects.link(temporary)
        temporary.matrix_world = original.matrix_world.copy()
        temporary.hide_set(False)
        baked.append(temporary)

    for obj in scene.objects:
        obj.select_set(False)
    for obj in baked:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = baked[0]

    result = bpy.ops.export_scene.gltf(
        filepath=str(destination),
        check_existing=False,
        export_format="GLB",
        use_selection=True,
        export_materials="NONE",
        export_texcoords=False,
        export_normals=False,
        export_animations=False,
        export_skins=False,
        export_morph=False,
        export_cameras=False,
        export_lights=False,
        export_apply=False,
        export_yup=True,
    )
    if "FINISHED" not in result:
        raise PreviewExportError("Blender glTF exporter did not finish")
    if destination.is_symlink() or not destination.is_file():
        raise PreviewExportError("Blender did not create a regular preview GLB")
    size = destination.stat().st_size
    if not 20 < size <= MAX_PREVIEW_BYTES:
        destination.unlink(missing_ok=True)
        raise PreviewExportError("Generated GLB is empty or exceeds safe preview limits")
    with destination.open("rb") as stream:
        if stream.read(4) != b"glTF":
            destination.unlink(missing_ok=True)
            raise PreviewExportError("Blender wrote an invalid GLB container")

    return {
        "staged_glb": destination.name,
        "selected_mesh_count": len(baked),
        "selected_vertex_count": total_baked,
        "evaluated_geometry_baked": True,
        "preview_bytes": size,
        "static_only": True,
        "textures_included": False,
        "animation_exported": False,
        "skinning_exported": False,
        "engine_import_verified": False,
        "blender_version": bpy.app.version_string,
    }
