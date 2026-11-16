extends SceneTree
## Private original native300 probe only; production V1 settings stay fixed.
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
    print("PRIVATE_NATIVE300_IMPORT_30FPS_NO_OPTIMIZER_CONFIGURED")
    quit(0)
