extends SceneTree
## Real candidate without a bound UV2 attribute; never fabricates engine proof.

func _initialize() -> void:
    call_deferred("_run")

func _nodes(node: Node, result: Array) -> void:
    if node is MeshInstance3D:
        result.append(node)
    for child in node.get_children():
        _nodes(child, result)

func _validate() -> Dictionary:
    var request: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://adapter_request.json"))
    if FileAccess.get_sha256("res://character.glb") != request["candidate_sha256"]:
        return {"error": "Candidate changed before actual import verification"}
    var scene: Node = (load("res://character.glb") as PackedScene).instantiate()
    root.add_child(scene)
    var meshes: Array = []
    _nodes(scene, meshes)
    if meshes.size() != 1:
        return {"error": "Unexpected actual imported mesh count"}
    var instance: MeshInstance3D = meshes[0]
    var mesh: ArrayMesh = instance.mesh
    var arrays: Array = mesh.surface_get_arrays(0)
    if arrays[Mesh.ARRAY_TEX_UV2] != null and not arrays[Mesh.ARRAY_TEX_UV2].is_empty():
        return {"error": "Candidate still has diagnostic UV2 correspondence"}
    var policy: Script = load("res://ucc_skin_adapter.gd")
    var guards: Array = []
    var absent: Dictionary = policy.apply(null, "res://character.glb", "res://skin_plan.json", request["plan_sha256"])
    if absent.get("code") != "ENGINE_INSTANCE":
        return {"error": "Missing engine instance did not reject explicitly"}
    guards.append({"fault": "missing_instance", "code": absent["code"], "original_preserved": true})
    var original: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://skin_plan.json"))
    for fault in ["hash", "schema", "candidate", "coverage", "sum", "bone", "correspondence"]:
        var damaged: Dictionary = original.duplicate(true)
        var key: String = String(damaged["entries"].keys()[0])
        var entry: Dictionary = damaged["entries"][key]
        match fault:
            "schema": damaged["schema_version"] = true
            "candidate": damaged["candidate_sha256"] = "0".repeat(64)
            "coverage": entry["count"] += 1
            "sum": entry["codes"][entry["codes"].keys()[0]] += 1
            "bone":
                var name: String = String(entry["codes"].keys()[0])
                entry["codes"]["UCC_MISSING_BONE"] = entry["codes"][name]
                entry["codes"].erase(name)
            "correspondence":
                damaged["entries"]["0000803f0000803f0000803f:" + key.split(":")[1]] = entry
                damaged["entries"].erase(key)
        var file := FileAccess.open("res://damaged_plan.json", FileAccess.WRITE)
        file.store_string(JSON.stringify(damaged)); file.close()
        var sha: String = FileAccess.get_sha256("res://damaged_plan.json")
        if fault == "hash": sha = "0".repeat(64)
        var result: Dictionary = policy.apply(instance, "res://character.glb", "res://damaged_plan.json", sha)
        if result.get("status") != "GODOT_SKIN_ADAPTER_REJECTED":
            return {"error": "Actual malformed plan admitted: " + fault}
        if instance.mesh != mesh or mesh.surface_get_arrays(0) != arrays:
            return {"error": "Failed plan mutated original imported arrays: " + fault}
        guards.append({"fault": fault, "code": result["code"], "original_preserved": true})
    var applied: Dictionary = policy.apply(instance, "res://character.glb", "res://skin_plan.json", request["plan_sha256"])
    if applied.get("status") != "GODOT_SKIN_PLAN_APPLIED":
        return {"error": "Valid bound plan failed", "result": applied}
    if instance.mesh == mesh or mesh.surface_get_arrays(0) != arrays:
        return {"error": "Valid plan changed original import resource"}
    var once: Array = instance.mesh.surface_get_arrays(0)
    var second: Dictionary = policy.apply(instance, "res://character.glb", "res://skin_plan.json", request["plan_sha256"])
    if second.get("status") != "GODOT_SKIN_PLAN_APPLIED" or instance.mesh.surface_get_arrays(0) != once:
        return {"error": "Versioned adapter is not idempotent", "result": second}
    return {"status": "ACTUAL_VERSIONED_ADAPTER_WITHOUT_UV2_VERIFIED", "godot_version": Engine.get_version_info(),
        "guards": guards, "applied": applied, "idempotence_verified": true,
        "original_import_preserved": true, "morphs": instance.mesh.get_blend_shape_count(),
        "engine_import_verified": false, "skeletal_animation_verified": false}

func _run() -> void:
    var result: Dictionary = _validate()
    var file := FileAccess.open("res://actual_adapter_report.json", FileAccess.WRITE)
    if file == null:
        quit(13); return
    file.store_string(JSON.stringify(result, "  ") + "\n"); file.close()
    print(JSON.stringify(result))
    quit(13 if result.has("error") else 0)
