extends SceneTree
## Actual imported MPFB mesh negatives; no synthetic character or animation.

func _initialize() -> void:
    call_deferred("_run")

func _nodes(node: Node, result: Array) -> void:
    if node is MeshInstance3D:
        result.append(node)
    for child in node.get_children():
        _nodes(child, result)

func _validate() -> Dictionary:
    var original: Array = JSON.parse_string(FileAccess.get_file_as_string("res://gltf_weights.json"))
    var bound: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://engine_reference.json"))
    if FileAccess.get_sha256("res://gltf_weights.json") != bound.get("gltf_weights_sha256", ""):
        return {"error": "Independent original GLB reference changed"}
    var report: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://blender_stage.json"))
    if FileAccess.get_sha256("res://character.glb") != report.get("glb_sha256", ""):
        return {"error": "Candidate changed"}
    var scene: Node = (load("res://character.glb") as PackedScene).instantiate()
    root.add_child(scene)
    var nodes: Array = []
    _nodes(scene, nodes)
    if nodes.size() != 1:
        return {"error": "Missing actual imported MPFB mesh"}
    var instance: MeshInstance3D = nodes[0]
    var original_mesh: ArrayMesh = instance.mesh
    var before: PackedFloat32Array = original_mesh.surface_get_arrays(0)[Mesh.ARRAY_WEIGHTS]
    var policy: Script = load("res://unit_sum_skin.gd")
    var guards: Array = []
    var target: int = -1
    for index in range(original.size()):
        if original[index].size() > 1:
            target = index; break
    if target < 0:
        return {"error": "Actual MPFB mesh unexpectedly has no mixed-weight vertex"}
    for kind in ["missing_row", "nonfinite", "negative", "nonunit", "missing_bone", "unrepresentable_positive"]:
        var damaged: Array = original.duplicate(true)
        var row: Dictionary = damaged[target]
        var name: String = String(row.keys()[0])
        match kind:
            "missing_row":
                damaged.clear()
            "nonfinite":
                row[name] = INF
            "negative":
                row[name] = -0.1
            "nonunit":
                row[name] = float(row[name]) + 0.1
            "missing_bone":
                row["UCC_NOT_AN_ACTUAL_BONE"] = row[name]
                row.erase(name)
            "unrepresentable_positive":
                var other_total: float = 0.0
                for other in row:
                    if other != name:
                        other_total += float(row[other])
                for other in row:
                    row[other] = 0.000000000001 if other == name else float(row[other])/other_total*(1.0-0.000000000001)
        var result: Dictionary = policy.apply(instance, damaged)
        if not result.has("error"):
            return {"error": "Actual negative was incorrectly admitted: " + kind}
        if instance.mesh != original_mesh or original_mesh.surface_get_arrays(0)[Mesh.ARRAY_WEIGHTS] != before:
            return {"error": "Negative changed the original imported skin: " + kind}
        guards.append({"case": kind, "error": result["error"], "original_resource_preserved": true})
    var first: Dictionary = policy.apply(instance, original)
    if first.has("error"):
        return {"error": "Valid original failed: " + str(first)}
    if original_mesh.surface_get_arrays(0)[Mesh.ARRAY_WEIGHTS] != before or instance.mesh == original_mesh:
        return {"error": "Successful application mutated the imported resource"}
    var once: PackedFloat32Array = instance.mesh.surface_get_arrays(0)[Mesh.ARRAY_WEIGHTS]
    var second: Dictionary = policy.apply(instance, original)
    if second.has("error") or instance.mesh.surface_get_arrays(0)[Mesh.ARRAY_WEIGHTS] != once:
        return {"error": "Unit-sum encoding is not idempotent"}
    if instance.mesh.get_blend_shape_count() != original_mesh.get_blend_shape_count():
        return {"error": "Unit-sum encoding lost actual morphs"}
    return {"status": "ACTUAL_SKIN_POLICY_GUARDS_AND_IDEMPOTENCE_VERIFIED",
        "guards": guards, "idempotence_verified": true, "original_resource_preserved": true,
        "original_morphs_retained": true, "policy": first,
        "engine_import_verified": false, "skeletal_animation_verified": false}

func _run() -> void:
    var result: Dictionary = _validate()
    var output: FileAccess = FileAccess.open("res://skin_policy_guards.json", FileAccess.WRITE)
    if output == null:
        quit(13); return
    output.store_string(JSON.stringify(result, "  ") + "\n"); output.close()
    print(JSON.stringify(result))
    quit(13 if result.has("error") else 0)
