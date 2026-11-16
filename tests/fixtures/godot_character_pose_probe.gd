extends "res://render_validate.gd"
## Independently apply real Blender world deformation deltas to imported bones.
## This checks bind/skin behavior, not imported skeletal animation channels.

func _transform(rows: Array) -> Transform3D:
    return Transform3D(Basis(Vector3(rows[0][0], rows[1][0], rows[2][0]),
        Vector3(rows[0][1], rows[1][1], rows[2][1]),
        Vector3(rows[0][2], rows[1][2], rows[2][2])),
        Vector3(rows[0][3], rows[1][3], rows[2][3]))

func _validate() -> Dictionary:
    var report: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://blender_stage.json"))
    var reference: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://pose_reference.json"))
    if reference.get("master_sha256", "") != report.get("master_sha256", ""):
        return _fail("Actual pose and candidate masters differ")
    if FileAccess.get_sha256("res://character.glb") != report.get("glb_sha256", ""):
        return _fail("Staged candidate changed")
    if FileAccess.get_sha256("res://pose_positions.bin") != reference.get("positions_sha256", ""):
        return _fail("Actual pose reference changed")
    var source: PackedFloat32Array = FileAccess.get_file_as_bytes("res://pose_positions.bin").to_float32_array()
    if FileAccess.get_sha256("res://source_weights.json") != report.get("weights_sha256", ""):
        return _fail("Actual original skin reference changed")
    var source_weights: Array = JSON.parse_string(FileAccess.get_file_as_string("res://source_weights.json"))
    var count: int = int(reference["source_vertices"])
    if count != 13380 or reference["cases"].size() != 4 or source.size() != 4 * count * 3:
        return _fail("Incomplete actual source pose data")
    var scene: Node = (load("res://character.glb") as PackedScene).instantiate()
    root.add_child(scene)
    var meshes: Array = []; var skeletons: Array = []; var players: Array = []
    _nodes(scene, "MeshInstance3D", meshes); _nodes(scene, "Skeleton3D", skeletons)
    _nodes(scene, "AnimationPlayer", players)
    if meshes.size() != 1 or skeletons.size() != 1:
        return _fail("Unexpected imported mesh or skeleton")
    for player in players:
        player.stop()
    var instance: MeshInstance3D = meshes[0]
    var skeleton: Skeleton3D = skeletons[0]
    var adapter: Dictionary = {"policy": "UNMODIFIED_GODOT_IMPORT"}
    if OS.get_cmdline_user_args().has("--unit-sum"):
        var encoded: Array = JSON.parse_string(FileAccess.get_file_as_string("res://gltf_weights.json"))
        var engine_reference: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://engine_reference.json"))
        if FileAccess.get_sha256("res://gltf_weights.json") != engine_reference.get("gltf_weights_sha256", ""):
            return _fail("Independent encoded skin reference changed")
        adapter = load("res://unit_sum_skin.gd").apply(instance, encoded)
        if adapter.has("error"):
            return _fail(String(adapter["error"]))
    for index in range(instance.get_blend_shape_count()):
        instance.set_blend_shape_value(index, 0.0)
    var uv: PackedVector2Array = instance.mesh.surface_get_arrays(0)[Mesh.ARRAY_TEX_UV2]
    var arrays: Array = instance.mesh.surface_get_arrays(0)
    var packed_weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
    var packed_bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
    var bind_names: Array[String] = []
    for index in range(instance.skin.get_bind_count()):
        var name: String = String(instance.skin.get_bind_name(index))
        if name.is_empty():
            name = String(skeleton.get_bone_name(instance.skin.get_bind_bone(index)))
        bind_names.append(name)
    var rests: Array[Transform3D] = []
    for index in range(skeleton.get_bone_count()):
        rests.append(skeleton.global_transform * skeleton.get_bone_global_rest(index))
    # Blender (x,y,z) -> glTF/Godot (x,z,-y), applied to world deltas.
    var conversion := Transform3D(Basis(Vector3.RIGHT, Vector3(0,0,-1), Vector3.UP), Vector3.ZERO)
    var cases: Array = []
    var maximum: float = 0.0
    for case_index in range(4):
        var deltas: Dictionary = reference["cases"][case_index]["source_world_deltas"]
        if deltas.size() != skeleton.get_bone_count():
            return _fail("Incomplete actual bone deformation deltas")
        # Global target poses are independent of importer bone-axis conventions.
        # Apply parents before children, then let the actual registered skin update.
        var remaining: Dictionary = {}
        for index in range(skeleton.get_bone_count()):
            remaining[index] = true
        while not remaining.is_empty():
            var progress: bool = false
            for index in remaining.keys():
                if remaining.has(skeleton.get_bone_parent(index)):
                    continue
                var name: String = String(skeleton.get_bone_name(index))
                if not deltas.has(name):
                    return _fail("Pose reference lost an actual bone name")
                var delta: Transform3D = conversion * _transform(deltas[name]) * conversion.affine_inverse()
                skeleton.set_bone_global_pose(index, skeleton.global_transform.affine_inverse() * delta * rests[index])
                remaining.erase(index); progress = true
            if not progress:
                return _fail("Invalid imported bone hierarchy")
        skeleton.force_update_all_bone_transforms()
        await process_frame
        await RenderingServer.frame_post_draw
        var baked: ArrayMesh = instance.bake_mesh_from_current_skeleton_pose()
        if baked == null or baked.get_surface_count() != 1:
            return _fail("Actual registered skin snapshot unavailable")
        var vertices: PackedVector3Array = baked.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
        if vertices.size() != uv.size():
            return _fail("Actual skin snapshot topology changed")
        var error: float = 0.0
        var quantized_prediction_error: float = 0.0
        var original_prediction_error: float = 0.0
        var world_deltas: Dictionary = {}
        for name in deltas:
            world_deltas[name] = conversion * _transform(deltas[name]) * conversion.affine_inverse()
        for index in range(vertices.size()):
            var source_id: int = int(round(uv[index].x * 255.0)) + 256 * int(round((1.0 - uv[index].y) * 255.0))
            if source_id < 0 or source_id >= count:
                return _fail("Actual pose source identity escaped reference")
            var offset: int = (case_index * count + source_id) * 3
            var original := Vector3(source[offset], source[offset + 2], -source[offset + 1])
            var point: Vector3 = instance.global_transform * vertices[index]
            if not point.is_finite():
                return _fail("Nonfinite actual skin snapshot")
            error = max(error, point.distance_to(original))
            var rest_offset: int = source_id * 3
            var baseline := Vector3(source[rest_offset], source[rest_offset + 2], -source[rest_offset + 1])
            var quantized: Vector3 = baseline
            for slot in range(8):
                var weight: float = packed_weights[index * 8 + slot]
                if weight == 0.0:
                    continue
                var name: String = bind_names[packed_bones[index * 8 + slot]]
                quantized += ((world_deltas[name] as Transform3D) * baseline - baseline) * weight
            quantized_prediction_error = max(quantized_prediction_error, quantized.distance_to(point))
            var unquantized := Vector3.ZERO
            for row in source_weights[source_id]:
                unquantized += ((world_deltas[String(row[0])] as Transform3D) * baseline) * float(row[1])
            original_prediction_error = max(original_prediction_error, unquantized.distance_to(original))
        maximum = max(maximum, error)
        cases.append({"case": case_index, "max_world_position_error_m": error,
            "packed_weight_rest_blend_prediction_error_m": quantized_prediction_error,
            "original_normalized_weight_prediction_error_m": original_prediction_error})
    return {"status": "ACTUAL_GODOT_BIND_SKIN_POSES_VERIFIED" if maximum <= 0.00001 else "GODOT_POSE_DIFFERENCE_EXCEEDS_FIXED_LIMIT",
        "godot_version": Engine.get_version_info(), "cases": cases,
        "max_world_position_error_m": maximum, "fixed_limit_m": 0.00001,
        "source_vertices": count, "actual_registered_skin_bake": true,
        "skin_encoding": adapter,
        "independent_actual_Blender_pose_references": true,
        "imported_skeletal_animation_channels_verified": false,
        "vertex_shader_positions_directly_verified": false,
        "engine_import_verified": false, "visual_quality_approved": false}

func _run() -> void:
    var result: Dictionary = await _validate()
    var output: FileAccess = FileAccess.open("res://actual_pose_report.json", FileAccess.WRITE)
    if output == null:
        push_error("Cannot record real skin result"); quit(13); return
    output.store_string(JSON.stringify(result, "  ") + "\n"); output.close()
    print(result["status"])
    quit(0 if result["status"] == "ACTUAL_GODOT_BIND_SKIN_POSES_VERIFIED" else 13)
