extends SceneTree
## Original MPFB import/deformation diagnostic. Never ships a sample character.
## Headless data checks are explicitly separate from actual rendered playback.

func _initialize() -> void:
    call_deferred("_run")


func _failure(message: String) -> Dictionary:
    return {"status": "GODOT_IMPORT_PROBE_FAILED", "error": message,
        "engine_import_verified": false, "rendered_playback_verified": false}


func _nodes(node: Node, kind: String, result: Array) -> void:
    if node.is_class(kind):
        result.append(node)
    for child in node.get_children():
        _nodes(child, kind, result)


func _validate() -> Dictionary:
    var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://blender_stage.json"))
    if not parsed is Dictionary:
        return _failure("Missing real Blender source report")
    var report: Dictionary = parsed
    var reference: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://engine_reference.json"))
    if not reference is Dictionary or reference.get("glb_sha256", "") != report.get("glb_sha256", ""):
        return _failure("Missing independently inspected serialized skin evidence")
    if FileAccess.get_sha256("res://gltf_weights.json") != reference.get("gltf_weights_sha256", ""):
        return _failure("Serialized skin reference changed")
    var encoded_weights: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://gltf_weights.json"))
    if FileAccess.get_sha256("res://character.glb") != report.get("glb_sha256", ""):
        return _failure("Imported GLB differs from the exact staged candidate")
    if FileAccess.get_sha256("res://source_positions.bin") != report.get("positions_sha256", ""):
        return _failure("Original Blender position evidence changed")
    if FileAccess.get_sha256("res://source_weights.json") != report.get("weights_sha256", ""):
        return _failure("Original Blender skin evidence changed")
    var source_weights: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://source_weights.json"))
    var source: PackedFloat32Array = FileAccess.get_file_as_bytes("res://source_positions.bin").to_float32_array()
    var vertex_count: int = int(report.get("visible_vertices", 0))
    if vertex_count != 13380 or source.size() != 25 * vertex_count * 3:
        return _failure("Incomplete actual source geometry")
    if not source_weights is Array or source_weights.size() != vertex_count:
        return _failure("Incomplete actual source skin weights")
    if not encoded_weights is Array or encoded_weights.size() != vertex_count:
        return _failure("Incomplete serialized skin evidence")
    var packed: PackedScene = load("res://character.glb") as PackedScene
    if packed == null:
        return _failure("Actual editor-imported candidate scene could not be loaded")
    var scene: Node = packed.instantiate()
    root.add_child(scene)
    var meshes: Array = []; var skeletons: Array = []; var players: Array = []
    _nodes(scene, "MeshInstance3D", meshes)
    _nodes(scene, "Skeleton3D", skeletons)
    _nodes(scene, "AnimationPlayer", players)
    if meshes.size() != 1 or skeletons.size() != 1 or players.size() != 1:
        return _failure("Missing or extra imported mesh, skeleton or animation player")
    var instance: MeshInstance3D = meshes[0]
    var skeleton: Skeleton3D = skeletons[0]
    var player: AnimationPlayer = players[0]
    var mesh: ArrayMesh = instance.mesh as ArrayMesh
    if mesh == null or mesh.get_surface_count() != 1 or instance.skin == null:
        return _failure("Imported character is not one genuinely skinned surface")
    if instance.get_node_or_null(instance.skeleton) != skeleton:
        return _failure("Imported mesh is bound to another skeleton")
    var names: Dictionary = {}
    for index in range(skeleton.get_bone_count()):
        names[String(skeleton.get_bone_name(index))] = true
    if names.size() != report["bone_names"].size():
        return _failure("Imported bone count changed")
    for name in report["bone_names"]:
        if not names.has(String(name)):
            return _failure("An actual MPFB bone was lost during import")
    var arrays: Array = mesh.surface_get_arrays(0)
    var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
    var uv: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV2]
    var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
    var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
    if vertices.is_empty() or uv.size() != vertices.size():
        return _failure("Imported diagnostic vertex correspondence is missing")
    if weights.size() != vertices.size() * 8 or bones.size() != weights.size():
        return _failure("Imported character did not retain all eight influence slots")
    var ids: Array[int] = []
    var covered: Dictionary = {}
    var max_weight_error: float = 0.0
    var max_serialization_error: float = 0.0
    for index in range(vertices.size()):
        if not uv[index].is_finite():
            return _failure("Invalid imported vertex correspondence")
        # Blender exports UVs with the glTF V-origin convention. This is
        # diagnostic metadata, so invert that documented coordinate conversion.
        var source_id: int = int(round(uv[index].x * 255.0)) + 256 * int(round((1.0 - uv[index].y) * 255.0))
        if source_id < 0 or source_id >= vertex_count:
            return _failure("Imported vertex points outside the actual source")
        ids.append(source_id); covered[source_id] = true
        var expected: Dictionary = {}
        for row in source_weights[source_id]:
            expected[String(row[0])] = float(row[1])
        var actual: Dictionary = {}
        for slot in range(8):
            var offset: int = index * 8 + slot
            var weight: float = weights[offset]
            if not is_finite(weight) or weight < 0.0 or weight > 1.00001:
                return _failure("Invalid engine skin weight")
            if weight == 0.0:
                continue
            var bind_index: int = bones[offset]
            if bind_index < 0 or bind_index >= instance.skin.get_bind_count():
                return _failure("Engine skin references a missing bind")
            var bone_name: String = String(instance.skin.get_bind_name(bind_index))
            if bone_name.is_empty():
                var bone_index: int = instance.skin.get_bind_bone(bind_index)
                if bone_index < 0 or bone_index >= skeleton.get_bone_count():
                    return _failure("Engine skin has no resolvable bone identity")
                bone_name = String(skeleton.get_bone_name(bone_index))
            if actual.has(bone_name):
                return _failure("Duplicate imported positive influence")
            actual[bone_name] = weight
        if actual.size() != expected.size():
            return _failure("Engine import dropped a positive source influence: " + JSON.stringify({
                "vertex": index, "source_id": source_id, "expected": expected, "actual": actual,
                "surface_format": mesh.surface_get_format(0)}))
        # The 4.7 glTF importer accumulates all eight slots in float32 order
        # and divides each float32 weight by that float32 total before packing.
        var encoded_total: float = 0.0
        for name in encoded_weights[source_id]:
            encoded_total = PackedFloat32Array([encoded_total + float(encoded_weights[source_id][name])])[0]
        if not is_finite(encoded_total) or encoded_total <= 0.0:
            return _failure("Invalid serialized weight normalization total")
        for name in expected:
            if not actual.has(name):
                return _failure("Engine weight is attached to the wrong bone")
            if not encoded_weights[source_id].has(name):
                return _failure("Serialized reference dropped an original influence")
            var encoded: float = float(encoded_weights[source_id][name])
            var serialization_error: float = abs(encoded - float(expected[name]))
            if serialization_error > 0.000001:
                return _failure("Serialized relative weight changed before engine quantization")
            max_serialization_error = max(max_serialization_error, serialization_error)
            # Godot's surface arrays store weights as UNORM16. Check the exact
            # integer codes rather than confusing encoding with source repair.
            var normalized: float = PackedFloat32Array([encoded / encoded_total])[0]
            var expected_code: int = int(PackedFloat32Array([normalized * 65535.0])[0])
            var actual_code: int = int(round(float(actual[name]) * 65535.0))
            if actual_code != expected_code or abs(float(actual[name]) - float(actual_code)/65535.0) > 1.0/16777216.0:
                return _failure("Engine weight packing differs from the exact serialized contribution: " + JSON.stringify({
                    "bone": name, "source_id": source_id, "expected_code": expected_code,
                    "actual_code": actual_code, "encoded": encoded, "actual": actual[name]}))
            max_weight_error = max(max_weight_error, abs(float(actual[name]) - float(expected[name])))
    if covered.size() != vertex_count:
        return _failure("Incomplete source correspondence")
    if mesh.get_blend_shape_count() != 12:
        return _failure("Canonical facial morphs were lost")
    var shapes: Array = mesh.surface_get_blend_shape_arrays(0)
    var morph_names: Array[String] = []
    for index in range(mesh.get_blend_shape_count()):
        var name: String = String(mesh.get_blend_shape_name(index))
        if not report["expression_keys"].has(name):
            return _failure("Unknown imported facial morph")
        morph_names.append(name)
        if shapes[index][Mesh.ARRAY_VERTEX].size() != vertices.size():
            return _failure("Imported facial morph has inconsistent topology")
    var clips: Array[StringName] = []
    for name in player.get_animation_list():
        if String(name) != "RESET":
            clips.append(name)
    if clips.size() != 1 or abs(player.get_animation(clips[0]).length - 1.0) > 0.000001:
        return _failure("Missing complete one-second imported facial animation")
    player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL
    player.play(clips[0]); player.advance(0.0)
    var maximum: float = 0.0
    var weight_peak: float = 0.0
    for frame in range(25):
        player.seek(float(frame) / 24.0, true)
        var morph_weights: Array[float] = []
        var total: float = 0.0
        for index in range(12):
            var weight: float = instance.get_blend_shape_value(index)
            var peak: float = float(report["expression_peaks"][morph_names[index]])
            var expected: float = peak * float(min(frame, 24 - frame)) / 12.0
            if not is_finite(weight) or abs(weight - expected) > 0.000001:
                return _failure("Actual engine animation did not reproduce a named facial control")
            morph_weights.append(weight); total += weight; weight_peak = max(weight_peak, weight)
        for index in range(vertices.size()):
            var point: Vector3 = vertices[index]
            if mesh.get_blend_shape_mode() == Mesh.BLEND_SHAPE_MODE_NORMALIZED:
                point *= 1.0 - total
            for morph in range(12):
                var positions: PackedVector3Array = shapes[morph][Mesh.ARRAY_VERTEX]
                point += positions[index] * morph_weights[morph]
            point = instance.global_transform * point
            var offset: int = (frame * vertex_count + ids[index]) * 3
            var original: Vector3 = Vector3(source[offset], source[offset + 2], -source[offset + 1])
            maximum = max(maximum, point.distance_to(original))
    if maximum > 0.00001 or weight_peak <= 0.0:
        return _failure("Imported full-surface deformation differs from actual Blender evidence: " + str(maximum))
    return {"status": "ACTUAL_GODOT_SKIN_MORPHS_AND_25_FRAME_DATA_VERIFIED",
        "godot_version": Engine.get_version_info(), "source_vertices": vertex_count,
        "imported_vertices": vertices.size(), "bones": skeleton.get_bone_count(),
        "morphs": mesh.get_blend_shape_count(), "frames_checked": 25,
        "max_skin_weight_error": max_weight_error, "max_world_position_error_m": maximum,
        "max_weight_serialization_error": max_serialization_error,
        "all_positive_influences_retained": true, "exact_UNORM16_weight_codes_verified": true,
        "actual_animation_values_verified": true, "source_correspondence_complete": true,
        "diagnostic_UV2_only": true, "rendered_playback_verified": false,
        "skeletal_animation_verified": false, "material_appearance_verified": false,
        "engine_import_verified": false, "visual_quality_approved": false}


func _run() -> void:
    var result: Dictionary = _validate()
    var output: FileAccess = FileAccess.open("res://actual_godot_report.json", FileAccess.WRITE)
    if output == null:
        push_error("Cannot record actual Godot result"); quit(13); return
    output.store_string(JSON.stringify(result, "  ") + "\n")
    output.close()
    print(result["status"])
    quit(0 if result["status"] == "ACTUAL_GODOT_SKIN_MORPHS_AND_25_FRAME_DATA_VERIFIED" else 13)
