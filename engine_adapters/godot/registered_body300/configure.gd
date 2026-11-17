extends SceneTree
## Owned body300 import configuration; V1 resources remain unchanged.
func _initialize() -> void:
    var config := ConfigFile.new()
    if config.load("res://character.glb.import") != OK:
        quit(13); return
    config.set_value("params", "animation/fps", 30.0)
    var subresources: Dictionary = config.get_value("params", "_subresources", {})
    var nodes: Dictionary = subresources.get("nodes", {})
    var player: Dictionary = nodes.get("PATH:AnimationPlayer", {})
    player["optimizer/enabled"] = false
    player["compression/enabled"] = false
    nodes["PATH:AnimationPlayer"] = player
    subresources["nodes"] = nodes
    config.set_value("params", "_subresources", subresources)
    if config.save("res://character.glb.import") != OK:
        quit(13); return
    var checked := ConfigFile.new()
    if checked.load("res://character.glb.import") != OK:
        quit(13); return
    var actual: Variant = checked.get_value("params", "_subresources", {})
    if not actual is Dictionary or not actual.get("nodes") is Dictionary:
        quit(13); return
    var imported: Variant = actual["nodes"].get("PATH:AnimationPlayer")
    if not imported is Dictionary or imported.get("optimizer/enabled") != false or imported.get("compression/enabled") != false or checked.get_value("params", "animation/fps", 0.0) != 30.0:
        quit(13); return
    var report: Dictionary = {"schema_version":1, "phase":"PRE_REIMPORT", "animation_fps":30.0,
        "optimizer_enabled":false, "compression_enabled":false,
        "import_settings_sha256":FileAccess.get_sha256("res://character.glb.import")}
    var stream := FileAccess.open("res://configured_import.json", FileAccess.WRITE)
    if stream == null:quit(13); return
    stream.store_string(JSON.stringify(report) + "\n");stream.flush()
    var valid: bool = stream.get_error() == OK
    stream.close()
    if not valid:quit(13); return
    print("PRIVATE_NATIVE300_IMPORT_30FPS_NO_OPTIMIZER_CONFIGURED")
    quit(0)
