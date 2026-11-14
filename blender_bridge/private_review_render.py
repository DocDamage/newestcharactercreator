"""Private CPU clay renders of actual evaluated skin, never source-master saves."""
from __future__ import annotations

from hashlib import sha256
import json
import math
from pathlib import Path
from typing import Any

from blender_bridge.pose_deformation import _evaluated_vertices

WIDTH, HEIGHT = 256, 384
VIEWS = {"front": (0., -1., 0.), "side": (1., 0., 0.), "quarter": (1., -1., .15)}
METHOD = "CYCLES_CPU_EVALUATED_SKIN_CLAY_V1"


class PrivateRenderError(RuntimeError):
    """Actual skin cannot be rendered and measured in the private workspace."""


def _record(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {"name": path.name, "bytes": len(data), "sha256": sha256(data).hexdigest()}


def render_private_review(bpy: Any, human: Any, frames: int, review_path: Path,
                          bindings: dict[str, Any], *, root_positions: dict | None = None) -> dict[str, Any]:
    from mathutils import Vector
    source_scene = bpy.context.scene
    prior_frame = source_scene.frame_current
    folder = review_path.parent / "review_frames"
    if folder.exists() or folder.is_symlink():
        raise PrivateRenderError("Refuse to overwrite or redirect private review renders")
    folder.mkdir()
    samples = sorted({1, 1+(frames-1)//4, 1+(frames-1)//2, 1+3*(frames-1)//4, frames})
    if len(samples) != 5:
        raise PrivateRenderError("Private review requires five distinct source frames")
    def offset(frame):
        if root_positions is None:
            return Vector((0.,0.,0.))
        for key in (frame,samples[0]):
            value=root_positions.get(key)
            if (not isinstance(value,(list,tuple)) or len(value)!=3 or
                    any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1e6 for v in value)):
                raise PrivateRenderError("Invalid root-follow camera coordinates")
        return Vector(root_positions[frame])-Vector(root_positions[samples[0]])
    points_world = []
    signatures = {}
    for frame in samples:
        source_scene.frame_set(frame)
        points, signature = _evaluated_vertices(bpy, human)
        signatures[frame] = signature
        frame_offset=offset(frame)
        points_world.extend(human.matrix_world @ Vector(point)-frame_offset for point in points)
    minimum = Vector(tuple(min(p[i] for p in points_world) for i in range(3)))
    maximum = Vector(tuple(max(p[i] for p in points_world) for i in range(3)))
    center, diagonal = (minimum + maximum) / 2, (maximum - minimum).length
    if (not .01 < diagonal < 1e5 or
            any(not math.isfinite(v) or abs(v) > 1e6 for p in (minimum, maximum) for v in p)):
        raise PrivateRenderError("Invalid world-space bounds for private camera framing")
    scene = bpy.data.scenes.new("UCC_PRIVATE_RENDER_ONLY")
    created_objects, created_data, records = [], [], []
    world = material = None
    try:
        scene.render.engine = "CYCLES"
        scene.cycles.device = "CPU"
        scene.cycles.samples = 8
        scene.cycles.use_denoising = False
        scene.cycles.seed = 0
        scene.render.threads_mode = "FIXED"
        scene.render.threads = 2
        scene.render.resolution_x, scene.render.resolution_y = WIDTH, HEIGHT
        scene.render.resolution_percentage = 100
        scene.render.film_transparent = True
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGBA"
        scene.render.image_settings.color_depth = "8"
        scene.view_settings.view_transform = "Standard"
        world = bpy.data.worlds.new("UCC_PRIVATE_WORLD")
        world.use_nodes = True
        world.node_tree.nodes["Background"].inputs["Color"].default_value = (.3, .3, .3, 1.)
        world.node_tree.nodes["Background"].inputs["Strength"].default_value = .6
        scene.world = world
        material = bpy.data.materials.new("UCC_PRIVATE_CLAY")
        material.use_nodes = True
        shader = material.node_tree.nodes.get("Principled BSDF")
        shader.inputs["Base Color"].default_value = (.52, .52, .52, 1.)
        shader.inputs["Roughness"].default_value = .7
        camera_data = bpy.data.cameras.new("UCC_PRIVATE_CAMERA")
        camera_data.type = "ORTHO"
        camera_data.clip_start = .001
        camera_data.clip_end = max(100., diagonal * 10)
        camera = bpy.data.objects.new(camera_data.name, camera_data)
        scene.collection.objects.link(camera)
        scene.camera = camera
        created_objects.append(camera)
        created_data.append((bpy.data.cameras, camera_data))
        light_positions=[]
        for i, direction in enumerate(((1., -2., 3.), (-2., 1., 2.))):
            lamp_data = bpy.data.lights.new(f"UCC_PRIVATE_LIGHT_{i}", "AREA")
            lamp_data.energy = 35 * diagonal * diagonal
            lamp_data.shape = "DISK"
            lamp_data.size = diagonal * 1.5
            lamp = bpy.data.objects.new(lamp_data.name, lamp_data)
            scene.collection.objects.link(lamp)
            lamp.location = center + Vector(direction).normalized() * diagonal * 2
            lamp.rotation_euler = (center - lamp.location).to_track_quat("-Z", "Y").to_euler()
            created_objects.append(lamp)
            created_data.append((bpy.data.lights, lamp_data))
            light_positions.append((lamp,lamp.location.copy()))
        for frame in samples:
            source_scene.frame_set(frame)
            bpy.context.view_layer.update()
            graph = bpy.context.evaluated_depsgraph_get()
            mesh = bpy.data.meshes.new_from_object(human.evaluated_get(graph), depsgraph=graph)
            mesh.materials.clear()
            mesh.materials.append(material)
            snapshot = bpy.data.objects.new("UCC_PRIVATE_EVALUATED_SKIN", mesh)
            scene.collection.objects.link(snapshot)
            snapshot.matrix_world = human.matrix_world.copy()
            root_offset=offset(frame)
            view_center=center+root_offset
            for lamp,base in light_positions: lamp.location=base+root_offset
            try:
                for view, direction in VIEWS.items():
                    camera.location = view_center + Vector(direction).normalized() * diagonal * 2
                    orientation = (view_center - camera.location).to_track_quat("-Z", "Y")
                    camera.rotation_euler = orientation.to_euler()
                    right, up = orientation @ Vector((1, 0, 0)), orientation @ Vector((0, 1, 0))
                    half_height = max(max(abs((p-center).dot(up)),
                                          abs((p-center).dot(right)) / (WIDTH/HEIGHT)) for p in points_world)
                    camera_data.ortho_scale = half_height * 2.3
                    path = folder / f"frame_{frame:04}_{view}.png"
                    scene.render.filepath = str(path)
                    outcome = bpy.ops.render.render(scene=scene.name, write_still=True)
                    if "FINISHED" not in outcome or not path.is_file():
                        raise PrivateRenderError("Blender failed to render private evaluated skin")
                    image = bpy.data.images.load(str(path), check_existing=False)
                    try:
                        if tuple(image.size) != (WIDTH, HEIGHT):
                            raise PrivateRenderError("Unexpected private render dimensions")
                        pixels = list(image.pixels[:])
                        visible = [i for i in range(0, len(pixels), 4) if pixels[i+3] >= .5]
                        if not 64 <= len(visible) < WIDTH * HEIGHT * .95:
                            raise PrivateRenderError("Private render is blank or clipped/full-frame")
                        xs = [(i//4) % WIDTH for i in visible]
                        ys = [HEIGHT-1-(i//4)//WIDTH for i in visible]
                        bounds = [min(xs), min(ys), max(xs), max(ys)]
                        if bounds[0] < 4 or bounds[1] < 4 or bounds[2] >= WIDTH-4 or bounds[3] >= HEIGHT-4:
                            raise PrivateRenderError("Private skin render touches camera boundary")
                        colors = [pixels[i+c] for i in visible for c in range(3)]
                        if max(colors) - min(colors) < .02:
                            raise PrivateRenderError("Private render has no useful surface contrast")
                        records.append({**_record(path), "frame": frame, "view": view,
                                        "width": WIDTH, "height": HEIGHT,
                                        "opaque_pixels": len(visible),
                                        "opaque_bounds": bounds,
                                        "evaluated_sha256": signatures[frame]})
                        if root_positions is not None:
                            offset_key="camera_hip_offset_world" if bindings.get("camera_translation_policy")=="FOLLOW_HIP_MIDPOINT_TRANSLATION" else "camera_root_offset_world"
                            records[-1][offset_key]=list(root_offset)
                    finally:
                        bpy.data.images.remove(image)
            finally:
                bpy.data.objects.remove(snapshot, do_unlink=True)
                bpy.data.meshes.remove(mesh)
        if any(len({r["sha256"] for r in records if r["view"] == view}) < 2 for view in VIEWS):
            raise PrivateRenderError("Sampled renders did not show changing skinned motion")
        manifest = {"schema_version": 1, "method": METHOD, **bindings,
                    "source_frame_count": frames, "rendered_frames": samples,
                    "animation_visual_quality_verified": False, "images": records}
        manifest_path = folder / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        rows = []
        for frame in samples:
            cells = "".join(f'<figure><img src="frame_{frame:04}_{view}.png"><figcaption>{view}</figcaption></figure>' for view in VIEWS)
            rows.append(f"<h2>Frame {frame}</h2><section>{cells}</section>")
        index = folder / "index.html"
        index.write_text('<!doctype html><meta charset="utf-8"><title>Private UCC motion review</title>'
                         '<style>body{background:#222;color:#eee;font:16px sans-serif}section{display:flex}'
                         'figure{margin:8px}img{background:#444;width:256px;height:384px}</style>'
                         '<h1>Private sampled motion review — unapproved</h1>'
                         '<p>Actual evaluated skin, CPU clay views. Inspect joints and deformation manually. '
                         'These sampled renders do not certify visual quality or engine compatibility.</p>'
                         + "".join(rows), encoding="utf-8")
        return {"manifest": _record(manifest_path), "index": _record(index),
                "image_count": len(records), "animation_visual_quality_verified": False}
    finally:
        source_scene.frame_set(prior_frame)
        for obj in created_objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.scenes.remove(scene)
        for collection, data in created_data:
            collection.remove(data)
        if material is not None:
            bpy.data.materials.remove(material)
        if world is not None:
            bpy.data.worlds.remove(world)
