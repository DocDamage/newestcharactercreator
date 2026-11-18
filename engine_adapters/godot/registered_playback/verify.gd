extends SceneTree
## Independent fresh-project verification of the published scene's normal path.

const SIZE := Vector2i(384, 384)
const MAX_MSEC := 32000

func _initialize() -> void:
    call_deferred("_verify")


func _finish(status: String, result := {}) -> void:
    var args := OS.get_cmdline_user_args()
    if args.size() != 1 or FileAccess.file_exists(args[0]):
        quit(3)
        return
    var file := FileAccess.open(args[0], FileAccess.WRITE)
    if file == null:
        quit(3)
        return
    result["status"] = status
    file.store_string(JSON.stringify(result) + "\n")
    file.flush()
    var written := file.get_error() == OK
    file.close()
    quit(0 if status == "PRIVATE_GODOT_PLAYBACK_REOPENED" and written else 2)


func _pixels(view: SubViewport) -> PackedByteArray:
    var image := view.get_texture().get_image()
    if image == null or image.is_empty() or image.get_size() != SIZE:
        return PackedByteArray()
    image.convert(Image.FORMAT_RGBA8)
    var pixels := image.get_data()
    var covered := 0
    for alpha in range(3, pixels.size(), 4):
        if pixels[alpha] >= 240:
            covered += 1
    if covered < 500 or covered > SIZE.x * SIZE.y * 0.9:
        return PackedByteArray()
    return pixels


func _verify() -> void:
    var scene := load("res://character.tscn") as PackedScene
    if scene == null:
        _finish("SCENE_LOAD")
        return
    var character := scene.instantiate()
    if character == null or not character.has_method("playback_status"):
        _finish("SCENE_CONTROLLER")
        return
    var view := SubViewport.new()
    view.size = SIZE
    view.own_world_3d = true
    view.transparent_bg = true
    view.render_target_update_mode = SubViewport.UPDATE_ALWAYS
    root.add_child(view)
    view.add_child(character)
    var player := character.find_children("*", "AnimationPlayer", true, false)
    if player.size() != 1:
        _finish("NATIVE_PLAYER")
        return
    var clip: AnimationPlayer = player[0]
    var first: PackedByteArray
    var second: PackedByteArray
    var expected_draws := 0
    var previous := -1.0
    var wrapped := false
    var started := Time.get_ticks_msec()
    while Time.get_ticks_msec() - started <= MAX_MSEC:
        await process_frame
        await RenderingServer.frame_post_draw
        var state: Dictionary = character.playback_status()
        if state.get("failed", true):
            _finish("PLAYBACK_CONTROLLER")
            return
        if not state.get("corrected_surface_visible", false) or not clip.is_playing():
            continue
        var time := clip.current_animation_position
        if not is_finite(time) or time < 0.0 or time > 10.001:
            _finish("NATIVE_CLOCK")
            return
        if previous >= 0.0 and time < previous:
            if previous < 8.0 or time > 2.0:
                _finish("NATIVE_WRAP")
                return
            wrapped = true
        if time != previous:
            expected_draws += 1
        previous = time
        if first.is_empty() and time > 2.4 and time < 3.2:
            first = _pixels(view)
        if second.is_empty() and time > 7.4 and time < 8.2:
            second = _pixels(view)
        if wrapped and time > 0.3 and not first.is_empty() and not second.is_empty():
            var display := character.get_node_or_null("CorrectedSurface") as MeshInstance3D
            if display == null or display.mesh == null or display.mesh.get_surface_count() != 1:
                _finish("CORRECTED_DISPLAY")
                return
            var surface := display.mesh.surface_get_arrays(0)
            if (not surface[Mesh.ARRAY_VERTEX] is PackedVector3Array
                    or not surface[Mesh.ARRAY_NORMAL] is PackedVector3Array
                    or surface[Mesh.ARRAY_VERTEX].size() == 0
                    or surface[Mesh.ARRAY_VERTEX].size() != surface[Mesh.ARRAY_NORMAL].size()):
                _finish("CORRECTED_NORMAL_STREAM")
                return
            if (first == second or expected_draws < 10 or state.get("applied_frames", 0) < 10
                    or state.get("completed_wraps", 0) < 1):
                _finish("RENDERED_LOOP")
                return
            _finish("PRIVATE_GODOT_PLAYBACK_REOPENED", {
                "schema_version": 1, "native_animation_advanced": true, "native_loop_wrapped": true,
                "corrected_normal_stream_drawn": true, "rendered_motion_observed": true,
                "private_pixels_retained": false
            })
            return
    _finish("PLAYBACK_TIMEOUT")
