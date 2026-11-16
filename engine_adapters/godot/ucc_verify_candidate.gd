extends SceneTree
## V1 private candidate verification on the actual graphics backend.
## This does not grant rights, certify materials or publish shipping assets.


var _request: Dictionary = {}
var _request_sha: String = ""

func _initialize() -> void:
    call_deferred("_run")

func _nodes(node: Node, kind: String, result: Array) -> void:
    if node.is_class(kind): result.append(node)
    for child in node.get_children(): _nodes(child, kind, result)

func _fail(message: String) -> Dictionary:
    return {"status":"GODOT_CANDIDATE_VERIFICATION_FAILED", "error":message,
        "engine_import_verified":false, "visual_quality_approved":false}

func _position_key(point: Vector3) -> String:
    return PackedFloat32Array([0.0 if point.x == 0.0 else point.x,
        0.0 if point.y == 0.0 else point.y, 0.0 if point.z == 0.0 else point.z]).to_byte_array().hex_encode()

func _validate() -> Dictionary:
    var report: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://blender_stage.json"))
    var request: Dictionary = _request
    var config := ConfigFile.new()
    if config.load("res://character.glb.import") != OK or config.get_value("params", "animation/fps", 0) != 24:
        return _fail("Final actual import frame rate differs from the bound source")
    var settings: Variant = config.get_value("params", "_subresources", {})
    if not settings is Dictionary or not settings.get("nodes") is Dictionary or not settings["nodes"].get("PATH:AnimationPlayer") is Dictionary:
        return _fail("Final actual import has no bound AnimationPlayer profile")
    var player_settings: Dictionary = settings["nodes"]["PATH:AnimationPlayer"]
    if typeof(player_settings.get("optimizer/enabled")) != TYPE_BOOL or player_settings["optimizer/enabled"] != false or typeof(player_settings.get("compression/enabled")) != TYPE_BOOL or player_settings["compression/enabled"] != false:
        return _fail("Final actual import changed required optimization or compression settings")
    for name in request["files"]:
        if FileAccess.get_sha256("res://" + name) != request["files"].get(name, ""):
            return _fail("Combined motion input changed: " + name)
    var indices: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://bind_source_indices.json"))
    var source: PackedFloat32Array = FileAccess.get_file_as_bytes("res://source_positions.bin").to_float32_array()
    var count: int = int(report["visible_vertices"])
    if count != 13380 or indices.size() != count or source.size() != 25*count*3:
        return _fail("Incomplete independently reopened original motion evidence")
    var viewport := SubViewport.new()
    viewport.size = Vector2i(256, 384); viewport.own_world_3d = true
    viewport.transparent_bg = true; viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    root.add_child(viewport)
    var scene: Node = (load("res://character.glb") as PackedScene).instantiate()
    viewport.add_child(scene)
    var meshes: Array = []; var players: Array = []; var skeletons: Array = []
    _nodes(scene, "MeshInstance3D", meshes); _nodes(scene, "AnimationPlayer", players)
    _nodes(scene, "Skeleton3D", skeletons)
    if meshes.size() != 1 or players.size() != 1 or skeletons.size() != 1:
        return _fail("Missing actual imported rig, mesh or animation")
    var instance: MeshInstance3D = meshes[0]
    var skeleton: Skeleton3D = skeletons[0]
    var player: AnimationPlayer = players[0]
    var adapter: Dictionary = load("res://ucc_skin_adapter.gd").apply(instance, "res://character.glb", "res://skin_plan.json", request["files"]["skin_plan.json"])
    if adapter.get("status") != "GODOT_SKIN_PLAN_APPLIED":
        return _fail("Versioned skin adapter failed: " + JSON.stringify(adapter))
    var arrays: Array = instance.mesh.surface_get_arrays(0)
    if arrays[Mesh.ARRAY_TEX_UV2] != null and not arrays[Mesh.ARRAY_TEX_UV2].is_empty():
        return _fail("Diagnostic UV2 must not be present")
    var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
    var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
    var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
    var ids: Array[int] = []
    var covered: Dictionary = {}
    for point in vertices:
        var key: String = _position_key(point)
        if not indices.has(key):
            return _fail("Actual imported position has no exact independently bound source identity")
        var source_id: int = int(indices[key])
        if source_id < 0 or source_id >= count:
            return _fail("Actual source identity escaped reference")
        ids.append(source_id); covered[source_id] = true
    if covered.size() != count or instance.mesh.get_blend_shape_count() != 12 or skeleton.get_bone_count() != 163:
        return _fail("Actual full source, canonical morph or family-bone coverage was lost")
    var clips: Array[StringName] = []
    for name in player.get_animation_list():
        if String(name) != "RESET": clips.append(name)
    if clips.size() != 1:
        return _fail("Combined original motion was split or lost")
    var clip: Animation = player.get_animation(clips[0])
    if abs(clip.length-1.0) > 0.000001:
        return _fail("Imported complete timeline length changed")
    var skeletal_tracks: int = 0
    for track in range(clip.get_track_count()):
        if clip.track_get_type(track) == Animation.TYPE_ROTATION_3D:
            skeletal_tracks += 1
    if skeletal_tracks < 5:
        return _fail("Actual keyed skeletal rotation tracks were lost")
    player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
    player.play(clips[0]); player.advance(0.0)
    var bounds: AABB = instance.global_transform * instance.get_aabb()
    var center: Vector3 = bounds.get_center()
    var camera := Camera3D.new(); viewport.add_child(camera)
    camera.position = center + Vector3(0, 0, bounds.size.length()*1.6)
    camera.look_at(center); camera.current = true
    var light := DirectionalLight3D.new(); viewport.add_child(light)
    light.rotation_degrees = Vector3(-25, -25, 0)
    var environment := WorldEnvironment.new(); environment.environment = Environment.new()
    environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
    environment.environment.ambient_light_color = Color.WHITE
    environment.environment.ambient_light_energy = 0.6; viewport.add_child(environment)
    # The bake API ignores morphs when baking a skeleton. Bake morphs first
    # into a hidden diagnostic mesh, restore exact skin-buffer codes, and use
    # the registered actual skeleton to evaluate the combined result. Rendering
    # continues to use the original imported animated instance.
    var buffer := PackedByteArray(); buffer.resize(vertices.size()*32)
    for index in range(vertices.size()):
        for slot in range(8):
            buffer.encode_u16(index*32+slot*2, bones[index*8+slot])
            buffer.encode_u16(index*32+16+slot*2, int(round(weights[index*8+slot]*65535.0)))
    var probe := MeshInstance3D.new(); scene.add_child(probe)
    probe.visible = false
    var frames: Array = []; var hashes: Dictionary = {}
    var maximum: float = 0.0
    for frame in range(25):
        player.seek(float(frame)/24.0, true)
        for index in range(12):
            var name: String = String(instance.mesh.get_blend_shape_name(index))
            var expected: float = float(report["expression_peaks"][name])*float(min(frame,24-frame))/12.0
            if abs(instance.get_blend_shape_value(index)-expected) > 0.000001:
                return _fail("Actual imported named facial control differs")
        skeleton.force_update_all_bone_transforms()
        await process_frame
        await RenderingServer.frame_post_draw
        var morph: ArrayMesh = instance.bake_mesh_from_current_blend_shape_mix()
        morph.surface_update_skin_region(0, 0, buffer)
        probe.mesh = morph; probe.skin = instance.skin
        probe.skeleton = probe.get_path_to(skeleton); probe.global_transform = instance.global_transform
        await process_frame
        await RenderingServer.frame_post_draw
        var combined: ArrayMesh = probe.bake_mesh_from_current_skeleton_pose()
        if combined == null or combined.get_surface_count() != 1:
            return _fail("Actual combined engine snapshot unavailable")
        var positions: PackedVector3Array = combined.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
        if positions.size() != vertices.size():
            return _fail("Combined snapshot changed topology")
        var error: float = 0.0
        for index in range(positions.size()):
            var point: Vector3 = probe.global_transform * positions[index]
            var offset: int = (frame*count+ids[index])*3
            var original := Vector3(source[offset], source[offset+2], -source[offset+1])
            if not point.is_finite(): return _fail("Nonfinite combined geometry")
            error = max(error, point.distance_to(original))
        maximum = max(maximum, error)
        if error > 0.00001:
            return _fail("Combined actual motion exceeds fixed world limit: " + JSON.stringify({"frame":frame,"error_m":error}))
        var image: Image = viewport.get_texture().get_image()
        if image == null or image.get_size() != Vector2i(256, 384):
            return _fail("Actual candidate viewport is unavailable")
        image.convert(Image.FORMAT_RGBA8)
        var bytes: PackedByteArray = image.get_data()
        var visible: int = 0
        for offset in range(3,bytes.size(),4):
            if bytes[offset] > 0: visible += 1
        if visible < 100: return _fail("Actual combined character did not draw")
        var digest := HashingContext.new(); digest.start(HashingContext.HASH_SHA256); digest.update(bytes)
        var sha: String = digest.finish().hex_encode(); hashes[sha] = true
        var filename: String = "res://combined_%02d.png" % frame
        if image.save_png(filename) != OK: return _fail("Cannot retain private combined render")
        frames.append({"frame":frame,"max_world_error_m":error,"rgba_sha256":sha,
            "png_sha256":FileAccess.get_sha256(filename),"visible_pixels":visible})
    if hashes.size() < 2: return _fail("Combined rendered motion did not change pixels")
    return {"status":"GODOT_CANDIDATE_DEFORMATION_AND_RENDER_VERIFIED_V1",
        "verified_import_profile":{"animation_fps":config.get_value("params", "animation/fps"),
            "animation_player_import_id":"PATH:AnimationPlayer", "optimizer_enabled":false, "compression_enabled":false},
        "import_options_sha256":FileAccess.get_sha256("res://character.glb.import"),
        "godot_version":Engine.get_version_info(),"rendering_device":RenderingServer.get_video_adapter_name(),
        "source_vertices":count,"imported_vertices":vertices.size(),"bones":163,"morphs":12,
        "skeletal_rotation_tracks":skeletal_tracks,"frames":frames,"distinct_rendered_frames":hashes.size(),
        "max_combined_world_error_m":maximum,"fixed_limit_m":0.00001,"skin_adapter":adapter,
        "imported_diagnostic_skeletal_channels_verified":true,"rendered_combined_samples_verified":true,
        "engine_baked_combined_deformation_verified":true,"shipping_animation_created":false,
        "vertex_shader_positions_directly_verified":false,"material_appearance_verified":false,
        "engine_import_verified":false,"visual_quality_approved":false}

func _run() -> void:
    var args: PackedStringArray = OS.get_cmdline_user_args()
    var result: Dictionary
    if args.size() != 2 or args[0] != "--request-sha256" or FileAccess.get_sha256("res://request.json") != args[1]:
        result = _fail("Candidate request changed or has no independent identity")
    else:
        _request_sha = args[1]
        var raw: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://request.json"))
        if not raw is Dictionary or raw.get("policy") != "UCC_PRIVATE_GODOT_CANDIDATE_JOB_V1" or raw.get("schema_version") != 1:
            result = _fail("Unsupported candidate request")
        else:
            _request = raw
            result = await _validate()
    result["job_id"] = _request.get("job_id", "")
    result["request_sha256"] = _request_sha
    result["project_id"] = _request.get("project_id", "")
    result["revision"] = int(_request.get("revision", -1))
    result["master_sha256"] = _request.get("master_sha256", "")
    var file := FileAccess.open("res://verification.json", FileAccess.WRITE)
    if file == null: quit(13); return
    file.store_string(JSON.stringify(result,"  ")+"\n"); file.close()
    print(result["status"])
    quit(0 if result["status"] == "GODOT_CANDIDATE_DEFORMATION_AND_RENDER_VERIFIED_V1" else 13)
