extends SceneTree
## Configure only an isolated V1 candidate after its first editor import.

func _initialize() -> void:
    call_deferred("_run")

func _configure() -> Dictionary:
    var args: PackedStringArray = OS.get_cmdline_user_args()
    if args.size() != 2 or args[0] != "--request-sha256" or FileAccess.get_sha256("res://request.json") != args[1]:
        return {"error": "Candidate request changed before import configuration"}
    var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string("res://request.json"))
    if not parsed is Dictionary or parsed.get("policy") != "UCC_PRIVATE_GODOT_CANDIDATE_JOB_V1" or parsed.get("schema_version") != 1:
        return {"error": "Unsupported candidate configuration request"}
    var request: Dictionary = parsed
    var expected: Dictionary = {"animation_fps":24, "optimizer_enabled":false,
        "compression_enabled":false, "animation_player_import_id":"PATH:AnimationPlayer"}
    var profile: Variant = request.get("import_profile")
    # JSON numbers are float64 in Godot; compare their validated values rather
    # than Dictionary equality against an integer-valued local literal.
    if not profile is Dictionary or profile.size() != 4 or typeof(profile.get("animation_fps")) != TYPE_FLOAT or profile["animation_fps"] != 24.0 or typeof(profile.get("optimizer_enabled")) != TYPE_BOOL or profile["optimizer_enabled"] != false or typeof(profile.get("compression_enabled")) != TYPE_BOOL or profile["compression_enabled"] != false or profile.get("animation_player_import_id") != "PATH:AnimationPlayer":
        return {"error": "Candidate import profile differs from the verified V1 settings"}
    if FileAccess.get_sha256("res://character.glb") != request["files"].get("character.glb", ""):
        return {"error": "Candidate changed before import configuration"}
    var config := ConfigFile.new()
    if config.load("res://character.glb.import") != OK:
        return {"error": "Initial actual editor import did not produce candidate settings"}
    var before: String = FileAccess.get_file_as_string("res://character.glb.import")
    # Preserve the original generated options for local diagnosis/rollback.
    # The coordinator guarantees a fresh isolated directory for this operation.
    if FileAccess.file_exists("res://original_import_options.cfg"):
        return {"error": "Refuse to overwrite earlier import configuration evidence"}
    var backup := FileAccess.open("res://original_import_options.cfg", FileAccess.WRITE)
    if backup == null: return {"error": "Cannot retain original candidate import options"}
    backup.store_string(before); backup.close()
    var subresources: Variant = config.get_value("params", "_subresources", {})
    if not subresources is Dictionary:
        return {"error": "Malformed original candidate subresource settings"}
    var changed: Dictionary = subresources.duplicate(true)
    if not changed.get("nodes", {}) is Dictionary:
        return {"error": "Malformed candidate node settings"}
    var nodes: Dictionary = changed.get("nodes", {})
    if not nodes.get("PATH:AnimationPlayer", {}) is Dictionary:
        return {"error": "Malformed AnimationPlayer import settings"}
    var player: Dictionary = nodes.get("PATH:AnimationPlayer", {})
    player["optimizer/enabled"] = false
    player["compression/enabled"] = false
    nodes["PATH:AnimationPlayer"] = player; changed["nodes"] = nodes
    config.set_value("params", "animation/fps", 24)
    config.set_value("params", "_subresources", changed)
    if config.save("res://character.glb.import") != OK:
        return {"error": "Cannot save staged candidate import settings"}
    var reopened := ConfigFile.new()
    if reopened.load("res://character.glb.import") != OK or reopened.get_value("params", "animation/fps", 0) != 24:
        return {"error": "Saved candidate frame rate differs"}
    var actual: Variant = reopened.get_value("params", "_subresources", {})
    if actual != changed:
        return {"error": "Saved candidate optimization settings differ"}
    return {"status":"GODOT_CANDIDATE_IMPORT_CONFIGURED_V1", "job_id":request["job_id"],
        "request_sha256":args[1], "import_profile":expected,
        "import_options_sha256":FileAccess.get_sha256("res://character.glb.import"),
        "original_options_sha256":FileAccess.get_sha256("res://original_import_options.cfg"),
        "engine_import_verified":false}

func _run() -> void:
    var result: Dictionary = _configure()
    var file := FileAccess.open("res://configuration.json", FileAccess.WRITE)
    if file == null: quit(13); return
    file.store_string(JSON.stringify(result,"  ")+"\n"); file.close()
    print(JSON.stringify(result))
    quit(13 if result.has("error") else 0)
