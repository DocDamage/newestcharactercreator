extends SceneTree
## Private first-party debug drawing of already admitted numerical readbacks.
## No source assets, private programs, skeletons, appearance or runtime proof.
const PROFILE := "GODOT_4_7_1_MOBILE_VULKAN_BODY300_DEBUG_DRAW_V1"
const STATUS := "REGISTERED_BODY300_DEBUG_DRAW_VERIFIED"
const VERTICES: int = 14517
const INDICES: int = 80268
const FALSE_FLAGS := ["engine_import_verified", "visual_quality_approved", "usable_action_approved",
    "material_appearance_verified", "distribution_license_review_complete", "private_runtime_delivery_authorized",
    "runtime_code_provenance_verified", "source_redistribution_authorized", "cloud_transmission_authorized", "shipping_runtime_implemented"]
var viewport: SubViewport

func _initialize() -> void:
    call_deferred("_run")

func _fail(message: String) -> Dictionary:
    return {"status":"REGISTERED_BODY300_DEBUG_DRAW_REJECTED", "error":message, "engine_import_verified":false}

func _hash(bytes: PackedByteArray) -> String:
    var value := HashingContext.new()
    if value.start(HashingContext.HASH_SHA256) != OK or value.update(bytes) != OK:return ""
    return value.finish().hex_encode()

func _sha(value: Variant) -> bool:
    return typeof(value) == TYPE_STRING and RegEx.create_from_string("^[0-9a-f]{64}$").search(value) != null

func _bytes(name: String, maximum: int, expected: String = "") -> PackedByteArray:
    var file := FileAccess.open("res://" + name, FileAccess.READ)
    if file == null:return PackedByteArray()
    var length: int = file.get_length()
    if length < 1 or length > maximum:
        file.close();return PackedByteArray()
    var bytes: PackedByteArray = file.get_buffer(maximum + 1)
    var stable: bool = file.get_length() == length
    file.close()
    if not stable or bytes.size() != length or (not expected.is_empty() and _hash(bytes) != expected):return PackedByteArray()
    return bytes

func _write(name: String, bytes: PackedByteArray) -> Dictionary:
    if bytes.is_empty() or FileAccess.file_exists("res://" + name):return {}
    var file := FileAccess.open("res://" + name, FileAccess.WRITE)
    if file == null:return {}
    file.store_buffer(bytes);file.flush()
    var success: bool = file.get_error() == OK and file.get_length() == bytes.size()
    file.close()
    if not success or _bytes(name, bytes.size(), _hash(bytes)) != bytes:return {}
    return {"sha256":_hash(bytes), "bytes":bytes.size()}

func _input_lengths() -> Dictionary:
    var lengths: Dictionary = {"imported_uv.f32":VERTICES * 8, "imported_uv_triangles.u32":INDICES * 4,
        "selection.json":256 * 1024, "project.godot":256 * 1024, "validate.gd":256 * 1024}
    for frame in [1, 150, 300]:
        var prefix: String = "frame%03d" % frame
        lengths[prefix + "_positions.f32"] = VERTICES * 12
        lengths[prefix + "_normals.f32"] = VERTICES * 12
    return lengths

func _capture_arrays(mesh: ArrayMesh, expected: Dictionary, prefix: String) -> Dictionary:
    if mesh.get_surface_count() != 1 or mesh.surface_get_primitive_type(0) != Mesh.PRIMITIVE_TRIANGLES:return {}
    if mesh.surface_get_format(0) & Mesh.ARRAY_FLAG_COMPRESS_ATTRIBUTES:return {}
    var arrays: Array = mesh.surface_get_arrays(0)
    var positions: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
    var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
    var uv: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
    var triangles: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
    if positions.size() != VERTICES or normals.size() != VERTICES or uv.size() != VERTICES or triangles.size() != INDICES:return {}
    var captured: Dictionary = {"positions":positions.to_byte_array(), "normals":normals.to_byte_array(),
        "uv":uv.to_byte_array(), "triangles":triangles.to_byte_array()}
    # Godot's flags0 ArrayMesh normal format quantizes independently of source
    # diagnostic tolerances. Retain the ACTUAL assigned normals, with this
    # separately measured draw-format bound; never substitute requested bytes.
    var requested_normals: PackedFloat32Array = expected["normals"].to_float32_array()
    if requested_normals.size() != VERTICES * 3:return {}
    for index in range(VERTICES):
        var offset: int = index * 3
        var requested := Vector3(requested_normals[offset], requested_normals[offset + 1], requested_normals[offset + 2])
        if not normals[index].is_finite() or abs(normals[index].length_squared() - 1.0) > 0.00002 or normals[index].distance_to(requested) > 0.0002:return {}
    var files: Dictionary = {}
    for role in captured:
        if role != "normals" and captured[role] != expected[role]:return {}
        var name: String = prefix + "_draw_" + role + (".u32" if role == "triangles" else ".f32")
        var record: Dictionary = _write(name, captured[role])
        if record.is_empty():return {}
        files[name] = record
    return files

func _draw_frame(frame: int, data: Dictionary) -> Dictionary:
    var prefix: String = "frame%03d" % frame
    var raw_positions: PackedFloat32Array = data[prefix + "_positions.f32"].to_float32_array()
    var raw_normals: PackedFloat32Array = data[prefix + "_normals.f32"].to_float32_array()
    var positions := PackedVector3Array();var normals := PackedVector3Array()
    positions.resize(VERTICES);normals.resize(VERTICES)
    var low := Vector3(INF, INF, INF);var high := Vector3(-INF, -INF, -INF)
    for index in range(VERTICES):
        var offset: int = index * 3
        var point := Vector3(raw_positions[offset], raw_positions[offset + 1], raw_positions[offset + 2])
        var normal := Vector3(raw_normals[offset], raw_normals[offset + 1], raw_normals[offset + 2])
        if not point.is_finite() or max(abs(point.x), max(abs(point.y), abs(point.z))) > 100.0 or not normal.is_finite() or abs(normal.length_squared() - 1.0) > 0.00002:
            return _fail("Invalid mapped positions or normals")
        positions[index] = point;normals[index] = normal;low = low.min(point);high = high.max(point)
    var extent: Vector3 = high - low
    if not extent.is_finite() or extent.length() < 0.001:return _fail("Degenerate bounded draw extent")
    var uv_values: PackedFloat32Array = data["imported_uv.f32"].to_float32_array()
    var uv := PackedVector2Array();uv.resize(VERTICES)
    for index in range(VERTICES):
        var point := Vector2(uv_values[index * 2], uv_values[index * 2 + 1])
        if not point.is_finite():return _fail("Invalid mapped UV")
        uv[index] = point
    var triangles: PackedInt32Array = data["imported_uv_triangles.u32"].to_int32_array()
    var used := PackedByteArray();used.resize(VERTICES)
    for index in triangles:
        if index < 0 or index >= VERTICES:return _fail("Invalid draw triangle index")
        used[index] = 1
    for value in used:
        if value != 1:return _fail("Incomplete draw index coverage")
    var colors := PackedColorArray();colors.resize(VERTICES)
    var axis := Vector3(0.35, 0.65, 0.7).normalized()
    for index in range(VERTICES):
        var variation: float = abs(normals[index].dot(axis))
        var height: float = (positions[index].y - low.y) / max(extent.y, 0.001)
        colors[index] = Color(0.15 + 0.65 * variation, 0.25 + 0.45 * (1.0 - variation), 0.2 + 0.6 * height, 1.0)
    var arrays: Array = [];arrays.resize(Mesh.ARRAY_MAX)
    arrays[Mesh.ARRAY_VERTEX] = positions;arrays[Mesh.ARRAY_NORMAL] = normals
    arrays[Mesh.ARRAY_TEX_UV] = uv;arrays[Mesh.ARRAY_INDEX] = triangles;arrays[Mesh.ARRAY_COLOR] = colors
    var mesh := ArrayMesh.new()
    mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays, [], {}, 0)
    if mesh.get_surface_count() != 1:return _fail("Draw surface allocation failed")
    var holder := Node3D.new();viewport.add_child(holder)
    var instance := MeshInstance3D.new();holder.add_child(instance)
    instance.transform = Transform3D.IDENTITY;instance.mesh = mesh;instance.visible = true
    var material := StandardMaterial3D.new()
    material.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
    material.vertex_color_use_as_albedo = true
    material.albedo_color = Color(1.0, 1.0, 1.0, 1.0)
    material.cull_mode = BaseMaterial3D.CULL_DISABLED
    instance.material_override = material
    var camera := Camera3D.new();holder.add_child(camera)
    var center: Vector3 = (low + high) * 0.5
    var distance: float = max(1.0, extent.length() * 2.0)
    camera.projection = Camera3D.PROJECTION_ORTHOGONAL
    camera.size = max(0.05, max(extent.x, extent.y) * 1.25)
    camera.near = 0.01;camera.far = distance + extent.length() + 2.0
    camera.position = center + Vector3(0.0, 0.0, distance);camera.look_at(center, Vector3.UP);camera.make_current()
    await process_frame;await RenderingServer.frame_post_draw
    await process_frame;await RenderingServer.frame_post_draw
    if not instance.is_visible_in_tree() or not camera.is_current() or instance.global_transform != Transform3D.IDENTITY:
        return _fail("Assigned mesh is hidden or camera/transform changed")
    var expected: Dictionary = {"positions":data[prefix + "_positions.f32"], "normals":data[prefix + "_normals.f32"],
        "uv":data["imported_uv.f32"], "triangles":data["imported_uv_triangles.u32"]}
    var files: Dictionary = _capture_arrays(instance.mesh, expected, prefix)
    if files.size() != 4:return _fail("Actually assigned mesh arrays differ from mapped source")
    var image: Image = viewport.get_texture().get_image()
    if image == null or image.is_empty() or image.get_width() != 512 or image.get_height() != 512:return _fail("Incomplete actual viewport capture")
    if image.get_format() != Image.FORMAT_RGBA8:image.convert(Image.FORMAT_RGBA8)
    var rgba: PackedByteArray = image.get_data()
    if rgba.size() != 512 * 512 * 4:return _fail("Incomplete viewport RGBA8 data")
    var visible: int = 0;var transparent: int = 0
    for offset in range(3, rgba.size(), 4):
        if rgba[offset] > 0:visible += 1
        else:transparent += 1
    if visible < 128 or transparent < 128:return _fail("Actual viewport lacks a visible bounded mesh and transparent background")
    var png_name: String = prefix + ".png"
    if FileAccess.file_exists("res://" + png_name) or image.save_png("res://" + png_name) != OK:return _fail("Cannot retain viewport PNG")
    var png: PackedByteArray = _bytes(png_name, 2 * 1024 * 1024)
    if png.is_empty():return _fail("Invalid bounded viewport PNG")
    files[png_name] = {"sha256":_hash(png), "bytes":png.size()}
    holder.free()
    return {"frame":frame, "files":files, "mesh_visible":true, "camera_current":true}

func _validate() -> Dictionary:
    var version: Dictionary = Engine.get_version_info()
    if version["major"] != 4 or version["minor"] != 7 or version["patch"] != 1:return _fail("Require selected Godot 4.7.1")
    if RenderingServer.get_rendering_device() == null or RenderingServer.get_current_rendering_method() != "mobile" or RenderingServer.get_current_rendering_driver_name() != "vulkan":
        return _fail("Require actual Mobile/Vulkan rendering")
    var spec_bytes: PackedByteArray = _bytes("spec.json", 256 * 1024)
    if spec_bytes.is_empty():return _fail("Missing bounded draw specification")
    var parsed: Variant = JSON.parse_string(spec_bytes.get_string_from_utf8())
    if not parsed is Dictionary:return _fail("Malformed draw specification")
    var spec: Dictionary = parsed
    if spec.size() != 5 or not spec.has_all(["schema_version", "profile", "selection_sha256", "diagnostic_receipt_sha256", "files"]):
        return _fail("Draw specification is not closed")
    if (typeof(spec["schema_version"]) != TYPE_INT and typeof(spec["schema_version"]) != TYPE_FLOAT) or spec["schema_version"] != 1 or spec["profile"] != PROFILE or not _sha(spec["selection_sha256"]) or not _sha(spec["diagnostic_receipt_sha256"]) or not spec["files"] is Dictionary:
        return _fail("Unsupported draw profile or identities")
    var lengths: Dictionary = _input_lengths()
    if spec["files"].size() != lengths.size() or not spec["files"].has_all(lengths.keys()):return _fail("Draw file set differs from exact eleven inputs")
    var data: Dictionary = {}
    for name in lengths:
        if not _sha(spec["files"][name]):return _fail("Missing exact input SHA")
        var bytes: PackedByteArray = _bytes(name, lengths[name], spec["files"][name])
        if bytes.is_empty() or (name.ends_with(".f32") or name.ends_with(".u32")) and bytes.size() != lengths[name]:
            return _fail("Changed or incomplete staged draw input: " + name)
        data[name] = bytes
    if _hash(data["selection.json"]) != spec["selection_sha256"]:return _fail("Draw selection differs")
    var selection: Variant = JSON.parse_string(data["selection.json"].get_string_from_utf8())
    var selection_keys: Array = ["schema_version", "policy", "profile", "draw_id", "diagnostic_receipt_sha256",
        "godot_executable_sha256", "godot_main_sha256", "purpose", "private_local_draw_confirmed"]
    selection_keys.append_array(FALSE_FLAGS)
    if not selection is Dictionary or selection.size() != selection_keys.size() or not selection.has_all(selection_keys):return _fail("Draw selection is not closed")
    if selection["policy"] != "UCC_PRIVATE_REGISTERED_BODY300_DEBUG_DRAW_V1" or selection["profile"] != PROFILE or selection["schema_version"] != 1 or selection["diagnostic_receipt_sha256"] != spec["diagnostic_receipt_sha256"] or typeof(selection["private_local_draw_confirmed"]) != TYPE_BOOL or selection["private_local_draw_confirmed"] != true:return _fail("Draw selection is not explicit or source-bound")
    for name in FALSE_FLAGS:
        if not selection.has(name) or typeof(selection[name]) != TYPE_BOOL or selection[name] != false:return _fail("Draw selection upgraded readiness")
    viewport = SubViewport.new();viewport.size = Vector2i(512, 512)
    viewport.own_world_3d = true;viewport.transparent_bg = true
    viewport.render_target_clear_mode = SubViewport.CLEAR_MODE_ALWAYS
    viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    root.add_child(viewport)
    var frames: Array = []
    for frame in [1, 150, 300]:
        var row: Dictionary = await _draw_frame(frame, data)
        if row.has("status"):return row
        frames.append(row)
    var report: Dictionary = {"schema_version":1, "status":STATUS, "spec_sha256":_hash(spec_bytes),
        "godot_version":version, "rendering_device":RenderingServer.get_video_adapter_name(), "frames":frames}
    for name in FALSE_FLAGS:report[name] = false
    return report

func _run() -> void:
    var report: Dictionary = await _validate()
    if viewport != null:viewport.free();viewport = null
    if FileAccess.file_exists("res://measurement.json"):quit(13);return
    var bytes: PackedByteArray = (JSON.stringify(report) + "\n").to_utf8_buffer()
    if _write("measurement.json", bytes).is_empty():quit(13);return
    print(report["status"])
    quit(0 if report["status"] == STATUS else 13)
