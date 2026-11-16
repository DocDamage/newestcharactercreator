extends SceneTree
## Private original-character GPU diagnostic; never ships a sample asset.

func _initialize() -> void:
    call_deferred("_run")

func _nodes(node: Node, kind: String, result: Array) -> void:
    if node.is_class(kind):
        result.append(node)
    for child in node.get_children():
        _nodes(child, kind, result)

func _fail(message: String) -> Dictionary:
    return {"status": "GODOT_RENDER_PROBE_FAILED", "error": message,
        "engine_import_verified": false, "visual_quality_approved": false}

func _validate() -> Dictionary:
    var report: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://blender_stage.json"))
    if FileAccess.get_sha256("res://character.glb") != report.get("glb_sha256", ""):
        return _fail("Staged candidate changed")
    if FileAccess.get_sha256("res://source_positions.bin") != report.get("positions_sha256", ""):
        return _fail("Actual Blender geometry evidence changed")
    var data_proof: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://actual_godot_report.json"))
    if data_proof.get("status", "") != "ACTUAL_GODOT_SKIN_MORPHS_AND_25_FRAME_DATA_VERIFIED":
        return _fail("Actual engine data validation must precede rendering")
    var viewport := SubViewport.new()
    viewport.size = Vector2i(512, 512)
    viewport.own_world_3d = true
    viewport.transparent_bg = true
    viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    root.add_child(viewport)
    var scene: Node = (load("res://character.glb") as PackedScene).instantiate()
    viewport.add_child(scene)
    var meshes: Array = []; var players: Array = []
    _nodes(scene, "MeshInstance3D", meshes); _nodes(scene, "AnimationPlayer", players)
    if meshes.size() != 1 or players.size() != 1:
        return _fail("Unexpected actual imported scene")
    var instance: MeshInstance3D = meshes[0]
    var player: AnimationPlayer = players[0]
    var clips: Array[StringName] = []
    for name in player.get_animation_list():
        if String(name) != "RESET":
            clips.append(name)
    if clips.size() != 1:
        return _fail("Incomplete imported animation")
    player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
    player.play(clips[0]); player.advance(0.0)
    var bounds: AABB = instance.global_transform * instance.get_aabb()
    var center: Vector3 = bounds.get_center()
    var camera := Camera3D.new()
    viewport.add_child(camera)
    camera.position = center + Vector3(0.0, 0.0, bounds.size.length() * 1.6)
    camera.look_at(center); camera.current = true
    var light := DirectionalLight3D.new()
    viewport.add_child(light)
    light.rotation_degrees = Vector3(-25.0, -25.0, 0.0)
    var environment := WorldEnvironment.new()
    environment.environment = Environment.new()
    environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
    environment.environment.ambient_light_color = Color.WHITE
    environment.environment.ambient_light_energy = 0.6
    viewport.add_child(environment)
    var source: PackedFloat32Array = FileAccess.get_file_as_bytes("res://source_positions.bin").to_float32_array()
    var count: int = int(report["visible_vertices"])
    if source.size() != 25 * count * 3:
        return _fail("Incomplete original geometry")
    var uv: PackedVector2Array = instance.mesh.surface_get_arrays(0)[Mesh.ARRAY_TEX_UV2]
    var maximum: float = 0.0
    var frames: Array = []
    var hashes: Dictionary = {}
    for frame in range(25):
        player.seek(float(frame) / 24.0, true)
        await process_frame
        await RenderingServer.frame_post_draw
        await process_frame
        await RenderingServer.frame_post_draw
        # Godot retrieves mesh arrays and computes this bake on the CPU.
        # Actual GPU drawing is checked independently by viewport images.
        var baked: ArrayMesh = instance.bake_mesh_from_current_blend_shape_mix()
        if baked == null or baked.get_surface_count() != 1:
            return _fail("Engine blend-shape snapshot unavailable")
        var vertices: PackedVector3Array = baked.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
        if vertices.size() != uv.size():
            return _fail("Engine snapshot topology changed")
        for index in range(vertices.size()):
            var source_id: int = int(round(uv[index].x * 255.0)) + 256 * int(round((1.0 - uv[index].y) * 255.0))
            if source_id < 0 or source_id >= count:
                return _fail("Engine snapshot correspondence escaped actual source")
            var offset: int = (frame * count + source_id) * 3
            var original := Vector3(source[offset], source[offset + 2], -source[offset + 1])
            var point: Vector3 = instance.global_transform * vertices[index]
            if not point.is_finite():
                return _fail("Nonfinite engine snapshot geometry")
            maximum = max(maximum, point.distance_to(original))
        if maximum > 0.00001:
            return _fail("Engine baked morph geometry differs from actual Blender: " + str(maximum))
        var image: Image = viewport.get_texture().get_image()
        if image == null or image.get_size() != Vector2i(512, 512):
            return _fail("Actual rendered viewport unavailable")
        image.convert(Image.FORMAT_RGBA8)
        var bytes: PackedByteArray = image.get_data()
        var visible: int = 0
        for offset in range(3, bytes.size(), 4):
            if bytes[offset] > 0:
                visible += 1
        if visible < 100:
            return _fail("Actual viewport did not draw the character")
        var digest := HashingContext.new()
        digest.start(HashingContext.HASH_SHA256); digest.update(bytes)
        var sha: String = digest.finish().hex_encode()
        hashes[sha] = true
        # Private, local-only renders; never send to AI or publish as assets.
        var filename: String = "res://render_%02d.png" % frame
        if image.save_png(filename) != OK:
            return _fail("Cannot retain private actual rendered evidence")
        frames.append({"frame": frame, "rgba_sha256": sha, "nontransparent_pixels": visible,
            "png_sha256": FileAccess.get_sha256(filename)})
    if hashes.size() < 2:
        return _fail("Rendered facial animation did not change any pixels")
    return {"status": "ACTUAL_GODOT_RENDER_AND_ENGINE_BAKED_MORPHS_VERIFIED",
        "godot_version": Engine.get_version_info(),
        "rendering_device": RenderingServer.get_video_adapter_name(),
        "rendering_method": RenderingServer.get_current_rendering_method(),
        "frames": frames, "distinct_rendered_frames": hashes.size(),
        "source_vertices": count, "max_engine_baked_morph_world_error_m": maximum,
        "rendered_facial_samples_verified": true, "engine_baked_morphs_verified": true, "vertex_shader_positions_directly_verified": false,
        "skeletal_animation_verified": false, "material_appearance_verified": false,
        "visual_quality_approved": false, "engine_import_verified": false}

func _run() -> void:
    var result: Dictionary = await _validate()
    var output: FileAccess = FileAccess.open("res://actual_render_report.json", FileAccess.WRITE)
    if output == null:
        push_error("Cannot record real rendering result"); quit(13); return
    output.store_string(JSON.stringify(result, "  ") + "\n"); output.close()
    print(result["status"])
    quit(0 if result["status"] == "ACTUAL_GODOT_RENDER_AND_ENGINE_BAKED_MORPHS_VERIFIED" else 13)
