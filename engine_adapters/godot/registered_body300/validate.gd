extends SceneTree
## Owned private body300 diagnostic. No material/renderer/shipping acceptance.
var kernel: RefCounted
var positions_file: FileAccess
var normals_file: FileAccess
const STATUS := "REGISTERED_BODY300_GPU_GEOMETRY_NORMALS_DIAGNOSTIC_VERIFIED"
const FALSE_FLAGS := ["engine_import_verified", "visual_quality_approved", "usable_action_approved",
    "material_appearance_verified", "distribution_license_review_complete", "private_runtime_delivery_authorized",
    "runtime_code_provenance_verified", "source_redistribution_authorized", "cloud_transmission_authorized", "shipping_runtime_implemented"]

func _initialize() -> void:
    call_deferred("_run")

func _fail(message: String) -> Dictionary:
    return {"status":"REGISTERED_BODY300_REJECTED", "error":message, "engine_import_verified":false}

func _nodes(node: Node, kind: String, found: Array) -> void:
    if node.is_class(kind):found.append(node)
    for child in node.get_children():_nodes(child, kind, found)

func _key(point: Vector3) -> String:
    return PackedFloat32Array([0.0 if point.x == 0.0 else point.x,
        0.0 if point.y == 0.0 else point.y, 0.0 if point.z == 0.0 else point.z]).to_byte_array().hex_encode()

func _read_json(path: String, maximum: int) -> Variant:
    var file := FileAccess.open(path, FileAccess.READ)
    if file == null:return null
    var length: int = file.get_length()
    if length < 2 or length > maximum:
        file.close();return null
    var bytes: PackedByteArray = file.get_buffer(maximum + 1)
    file.close()
    if bytes.size() != length:return null
    return JSON.parse_string(bytes.get_string_from_utf8())

func _frame(values: PackedFloat32Array, normal: bool) -> bool:
    if values.size() != 13380 * 4:return false
    for vertex in range(13380):
        var offset: int = vertex * 4
        var point := Vector3(values[offset], values[offset + 1], values[offset + 2])
        if not point.is_finite() or values[offset + 3] != (0.0 if normal else 1.0):return false
        if normal and abs(point.length_squared() - 1.0) > 0.00002:return false
    return true

func _validate() -> Dictionary:
    var version: Dictionary = Engine.get_version_info()
    if version["major"] != 4 or version["minor"] != 7 or version["patch"] != 1:return _fail("Require selected Godot 4.7.1")
    if RenderingServer.get_rendering_device() == null:return _fail("Require actual Mobile/Vulkan RenderingDevice")
    if RenderingServer.get_current_rendering_method() != "mobile" or RenderingServer.get_current_rendering_driver_name() != "vulkan":
        return _fail("Unsupported rendering method or driver")
    var parsed: Variant = _read_json("res://spec.json", 256 * 1024)
    if not parsed is Dictionary:return _fail("Missing bounded body300 specification")
    var spec: Dictionary = parsed
    if spec.get("profile") != "GODOT_4_7_1_MOBILE_VULKAN_BODY300_V1" or spec.get("frames") != 300 or spec.get("fps") != 30 or not spec.get("files") is Dictionary:
        return _fail("Unsupported body300 specification")
    for name in spec["files"]:
        if typeof(name) != TYPE_STRING or name.contains("/") or name.contains("\\") or name.contains(".."):
            return _fail("Invalid staged resource path")
        if FileAccess.get_sha256("res://" + name) != spec["files"][name]:return _fail("Changed staged resource: " + name)
    if FileAccess.get_sha256("res://execution.json") != spec["execution_sha256"]:return _fail("Changed execution selection")
    var config := ConfigFile.new()
    if config.load("res://character.glb.import") != OK:return _fail("Missing current import configuration")
    var actual_settings: Variant = config.get_value("params", "_subresources", {})
    if not actual_settings is Dictionary or not actual_settings.get("nodes") is Dictionary:return _fail("Malformed imported node settings")
    var imported: Variant = actual_settings["nodes"].get("PATH:AnimationPlayer")
    if not imported is Dictionary or imported.get("optimizer/enabled") != false or imported.get("compression/enabled") != false or config.get_value("params", "animation/fps", 0.0) != 30.0:
        return _fail("Actual imported animation configuration differs")
    var configuration: Dictionary = {"schema_version":1, "phase":"POST_REIMPORT", "animation_fps":30.0,
        "optimizer_enabled":false, "compression_enabled":false,
        "import_settings_sha256":FileAccess.get_sha256("res://character.glb.import")}
    var config_output := FileAccess.open("res://import_configuration.json", FileAccess.WRITE)
    if config_output == null:return _fail("Cannot retain typed import configuration")
    config_output.store_string(JSON.stringify(configuration) + "\n");config_output.flush()
    var config_written: bool = config_output.get_error() == OK
    config_output.close()
    if not config_written:return _fail("Cannot flush import configuration")
    var packed: PackedScene = load("res://character.glb") as PackedScene
    if packed == null:return _fail("Missing imported scene")
    var scene: Node = packed.instantiate()
    if scene == null:return _fail("Imported scene failed to instantiate")
    var viewport := SubViewport.new()
    viewport.size = Vector2i(64, 64)
    viewport.own_world_3d = true
    viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    root.add_child(viewport);viewport.add_child(scene)
    var meshes: Array = [];var players: Array = [];var skeletons: Array = []
    _nodes(scene, "MeshInstance3D", meshes);_nodes(scene, "AnimationPlayer", players);_nodes(scene, "Skeleton3D", skeletons)
    if meshes.size() != 1 or players.size() != 1 or skeletons.size() != 1:return _fail("Incomplete actual imported rig")
    var instance: MeshInstance3D = meshes[0]
    var skeleton: Skeleton3D = skeletons[0]
    var player: AnimationPlayer = players[0]
    if skeleton.get_bone_count() != 163 or instance.mesh == null or instance.mesh.get_blend_shape_count() != 12:return _fail("Imported family changed")
    var skin: Dictionary = load("res://ucc_skin_adapter.gd").apply(instance, "res://character.glb", "res://skin_plan.json", spec["plan_sha256"])
    if skin.get("status") != "GODOT_SKIN_PLAN_APPLIED":return _fail("Skin adapter rejected imported source")
    var arrays: Array = instance.mesh.surface_get_arrays(0)
    var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
    var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
    var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
    var uv: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
    var triangles: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
    if vertices.size() != 14517 or uv.size() != vertices.size() or bones.size() != vertices.size() * 8 or weights.size() != bones.size():return _fail("Imported array lengths changed")
    var source_ids: Variant = _read_json("res://bind_source_indices.json", 4 * 1024 * 1024)
    if not source_ids is Dictionary or source_ids.size() != 13380:return _fail("Invalid bind source identity map")
    var ids := PackedInt32Array();var covered: Dictionary = {}
    for point in vertices:
        if not point.is_finite() or not source_ids.has(_key(point)):return _fail("Missing finite source bind identity")
        var value: Variant = source_ids[_key(point)]
        if (typeof(value) != TYPE_FLOAT and typeof(value) != TYPE_INT) or not is_finite(float(value)) or float(value) != floor(float(value)) or value < 0 or value >= 13380:return _fail("Invalid source bind index")
        var index: int = int(value);ids.append(index);covered[index] = true
    if covered.size() != 13380:return _fail("Lost complete source coverage")
    var uv_buffers: Dictionary = {"imported_uv.f32":uv.to_byte_array(), "imported_uv_source_ids.u32":ids.to_byte_array(), "imported_uv_triangles.u32":triangles.to_byte_array()}
    var uv_hashes: Dictionary = {}
    for name in uv_buffers:
        if FileAccess.file_exists("res://" + name):return _fail("Earlier UV output exists")
        var stream := FileAccess.open("res://" + name, FileAccess.WRITE)
        if stream == null:return _fail("Cannot retain UV readback")
        stream.store_buffer(uv_buffers[name]);stream.flush()
        if stream.get_error() != OK:stream.close();return _fail("UV readback write failed")
        stream.close();uv_hashes[name] = FileAccess.get_sha256("res://" + name)
    var skin_bytes := PackedByteArray();skin_bytes.resize(vertices.size() * 32)
    for vertex in range(vertices.size()):
        for slot in range(8):
            skin_bytes.encode_u16(vertex * 32 + slot * 2, bones[vertex * 8 + slot])
            skin_bytes.encode_u16(vertex * 32 + 16 + slot * 2, int(round(weights[vertex * 8 + slot] * 65535.0)))
    var clips: Array = []
    for name in player.get_animation_list():
        if String(name) != "RESET":clips.append(name)
    if clips.size() != 1:return _fail("Source clip split or missing")
    if abs(player.get_animation(clips[0]).length - 299.0 / 30.0) > 0.000001:return _fail("Source clock changed")
    player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
    player.play(clips[0]);player.advance(0.0)
    var probe := MeshInstance3D.new();scene.add_child(probe);probe.visible = false;instance.visible = false
    kernel = load("res://runtime_kernel.gd").new()
    var setup: Dictionary = kernel.setup(spec)
    if setup.get("status") != "READY":return _fail("Private runtime setup rejected")
    for name in ["actual_corrected_world.f32", "actual_normals_vec4.f32"]:
        if FileAccess.file_exists("res://" + name):return _fail("Earlier GPU readback exists")
    positions_file = FileAccess.open("res://actual_corrected_world.f32", FileAccess.WRITE)
    normals_file = FileAccess.open("res://actual_normals_vec4.f32", FileAccess.WRITE)
    if positions_file == null or normals_file == null:return _fail("Cannot retain GPU readbacks")
    var frames: Array = []
    for sample in range(300):
        player.seek(PackedFloat32Array([float(sample) / 30.0])[0], true)
        for morph in range(12):instance.set_blend_shape_value(morph, 0.0)
        skeleton.force_update_all_bone_transforms();await process_frame;await RenderingServer.frame_post_draw
        var morph_mesh: ArrayMesh = instance.bake_mesh_from_current_blend_shape_mix()
        if morph_mesh == null or morph_mesh.get_surface_count() != 1:return _fail("Actual blend shape bake failed")
        morph_mesh.surface_update_skin_region(0, 0, skin_bytes)
        probe.mesh = morph_mesh;probe.skin = instance.skin;probe.skeleton = probe.get_path_to(skeleton);probe.global_transform = instance.global_transform
        await process_frame;await RenderingServer.frame_post_draw
        var baked: ArrayMesh = probe.bake_mesh_from_current_skeleton_pose()
        if baked == null or baked.get_surface_count() != 1:return _fail("Actual skeleton bake failed")
        var actual: PackedVector3Array = baked.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
        if actual.size() != vertices.size():return _fail("Actual skin topology changed")
        var raw := PackedFloat32Array();raw.resize(13380 * 4)
        var visited := PackedByteArray();visited.resize(13380)
        for vertex in range(actual.size()):
            var point: Vector3 = probe.global_transform * actual[vertex]
            point = Vector3(point.x, -point.z, point.y)
            if not point.is_finite():return _fail("Nonfinite actual skin positions")
            var index: int = ids[vertex];var offset: int = index * 4
            if visited[index] != 0:
                if point.distance_to(Vector3(raw[offset], raw[offset + 1], raw[offset + 2])) > 0.000001:return _fail("UV seam positions disagree")
            else:
                raw[offset] = point.x;raw[offset + 1] = point.y;raw[offset + 2] = point.z;raw[offset + 3] = 1.0;visited[index] = 1
        var corrected: Dictionary = kernel.correct(raw)
        if corrected.get("status") != "OK" or not corrected.get("positions") is PackedFloat32Array or not corrected.get("normals") is PackedFloat32Array:return _fail("Private GPU correction rejected")
        if not _frame(corrected["positions"], false) or not _frame(corrected["normals"], true):return _fail("Invalid GPU readback values")
        positions_file.store_buffer(corrected["positions"].to_byte_array());normals_file.store_buffer(corrected["normals"].to_byte_array())
        if positions_file.get_error() != OK or normals_file.get_error() != OK:return _fail("GPU readback write failed")
        frames.append(sample + 1)
    positions_file.flush();normals_file.flush();positions_file.close();normals_file.close()
    positions_file = null;normals_file = null
    var outputs: Dictionary = {}
    for name in ["actual_corrected_world.f32", "actual_normals_vec4.f32"]:
        var file := FileAccess.open("res://" + name, FileAccess.READ)
        if file == null or file.get_length() != 300 * 13380 * 16:return _fail("Incomplete GPU stream")
        outputs[name] = {"sha256":FileAccess.get_sha256("res://" + name), "bytes":file.get_length()};file.close()
    var report: Dictionary = {"schema_version":1, "status":STATUS, "execution_sha256":spec["execution_sha256"],
        "spec_sha256":FileAccess.get_sha256("res://spec.json"), "frames":frames, "source_vertices":13380,
        "imported_vertices":vertices.size(), "bones":163, "canonical_morphs":12, "godot_version":version,
        "rendering_device":RenderingServer.get_video_adapter_name(), "gpu_correction_applied":true,
        "uv_readback_sha256":uv_hashes, "files":outputs}
    for name in FALSE_FLAGS:report[name] = false
    return report

func _run() -> void:
    var report: Dictionary = await _validate()
    if positions_file != null:positions_file.close()
    if normals_file != null:normals_file.close()
    if kernel != null:kernel.cleanup()
    var file := FileAccess.open("res://measurement.json", FileAccess.WRITE)
    if file == null:quit(13);return
    file.store_string(JSON.stringify(report) + "\n");file.flush()
    var valid: bool = file.get_error() == OK
    file.close()
    print(report["status"])
    quit(0 if valid and report["status"] == STATUS else 13)
