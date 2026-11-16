extends SceneTree
## Read actual imported scalar timing/weights, no geometry or poses emitted.
func _nodes(node: Node, result: Array) -> void:
    if node is AnimationPlayer: result.append(node)
    for child in node.get_children(): _nodes(child,result)
func _initialize() -> void:
    var scene: Node = load("res://character.glb").instantiate()
    root.add_child(scene)
    var players: Array = []; _nodes(scene,players)
    var player: AnimationPlayer = players[0]
    var clips: Array = []
    for name in player.get_animation_list():
        if String(name) != "RESET": clips.append(name)
    var clip: Animation = player.get_animation(clips[0])
    var rows: Array = []
    for track in range(clip.get_track_count()):
        if String(clip.track_get_path(track)).ends_with("UCC_POSE_CORRECTION_V1_f0033"):
            var keys: Array = []
            for key in range(clip.track_get_key_count(track)):
                var time: float = clip.track_get_key_time(track,key)
                if time > 0.98 and time < 1.15:
                    keys.append({"index":key,"time":time,"value":clip.track_get_key_value(track,key)})
            rows.append({"track":String(clip.track_get_path(track)),"interpolation":clip.track_get_interpolation_type(track),"keys":keys})
    var file := FileAccess.open("res://time_probe87.json",FileAccess.WRITE)
    file.store_string(JSON.stringify({"clip_length":clip.length,"rows":rows},"  ")+"\n"); file.close()
    print("ACTUAL_CORRECTIVE_SCALAR_TIMING_INSPECTED")
    quit(0)
