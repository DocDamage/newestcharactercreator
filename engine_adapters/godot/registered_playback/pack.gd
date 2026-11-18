extends SceneTree
## Package the exact approved imported rig without its build resources.

const Adapter = preload("ucc_skin_adapter.gd")
const Playback = preload("playback.gd")
const TRACK_TYPES := [Animation.TYPE_POSITION_3D, Animation.TYPE_ROTATION_3D,
	Animation.TYPE_SCALE_3D, Animation.TYPE_BLEND_SHAPE]
const OUTPUT := "res://character.tscn"

func _initialize() -> void:
	call_deferred("_pack")

func _find(node: Node, kind: String, found: Array[Node]) -> void:
	if node.is_class(kind):
		found.append(node)
	for child in node.get_children():
		_find(child, kind, found)

func _own(node: Node, target: Node) -> void:
	for child in node.get_children():
		child.owner = target
		_own(child, target)

func _fail(stage: String):
	push_error("Private skeletal pack rejected: " + stage)
	quit(2)

func _key(point: Vector3) -> String:
	return PackedFloat32Array([0.0 if point.x == 0.0 else point.x,
		0.0 if point.y == 0.0 else point.y, 0.0 if point.z == 0.0 else point.z]).to_byte_array().hex_encode()

func _source_ids(mesh: MeshInstance3D, expected_sha256: String) -> PackedInt32Array:
	var file := FileAccess.open("res://bind_source_indices.json", FileAccess.READ)
	var limit := 4 * 1024 * 1024
	if file == null or file.get_length() < 2 or file.get_length() > limit:
		return PackedInt32Array()
	var raw := file.get_buffer(limit + 1)
	file.close()
	var hashing := HashingContext.new()
	if raw.size() > limit or hashing.start(HashingContext.HASH_SHA256) != OK \
			or hashing.update(raw) != OK or hashing.finish().hex_encode() != expected_sha256:
		return PackedInt32Array()
	var parsed: Variant = JSON.parse_string(raw.get_string_from_utf8())
	if not parsed is Dictionary or parsed.size() != Playback.VERTICES:
		return PackedInt32Array()
	var bind: PackedVector3Array = mesh.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	var covered := PackedByteArray()
	covered.resize(Playback.VERTICES)
	var ids := PackedInt32Array()
	for point in bind:
		var value: Variant = parsed.get(_key(point), -1)
		if not (value is float or value is int) or value < 0 or value >= Playback.VERTICES or int(value) != value:
			return PackedInt32Array()
		var id := int(value)
		ids.append(id)
		covered[id] = 1
	return ids if covered.count(1) == Playback.VERTICES else PackedInt32Array()

func _pack():
	var args := OS.get_cmdline_user_args()
	if (args.size() != 4 or FileAccess.get_sha256("res://character.glb") != args[0]
			or FileAccess.get_sha256("res://skin_plan.json") != args[1]
			or FileAccess.get_sha256("res://playback.json") != args[2] or FileAccess.file_exists(OUTPUT)):
		return _fail("inputs")
	var imported := load("res://character.glb") as PackedScene
	if imported == null:
		return _fail("actual_glb_import")
	var scene := Node3D.new()
	scene.name = "PrivateCharacter"
	var model := imported.instantiate()
	scene.add_child(model)
	model.scene_file_path = ""
	var meshes: Array[Node] = []
	var rigs: Array[Node] = []
	var players: Array[Node] = []
	_find(model, "MeshInstance3D", meshes)
	_find(model, "Skeleton3D", rigs)
	_find(model, "AnimationPlayer", players)
	if meshes.size() != 1 or rigs.size() != 1 or players.size() != 1:
		return _fail("native_nodes")
	var mesh := meshes[0] as MeshInstance3D
	var rig := rigs[0] as Skeleton3D
	var player := players[0] as AnimationPlayer
	if (mesh.skin == null or mesh.get_node_or_null(mesh.skeleton) != rig or rig.get_bone_count() != 163
			or mesh.mesh.get_blend_shape_count() != 12):
		return _fail("native_skin")
	var skin: Dictionary = Adapter.apply(mesh, "res://character.glb", "res://skin_plan.json", args[1])
	if (skin.get("status") != "GODOT_SKIN_PLAN_APPLIED" or skin.get("all_positive_influences_retained") != true
			or skin.get("exact_integer_codes_rechecked") != true):
		return _fail("unit_sum_skin")
	var ids := _source_ids(mesh, args[3])
	if ids.is_empty():
		return _fail("exact_source_correspondence")
	var names: Array[String] = []
	for name in player.get_animation_list():
		if name != "RESET":
			names.append(name)
	if names.size() != 1 or not player.has_animation_library(""):
		return _fail("animation_membership")
	var name := names[0]
	var original := player.get_animation(name)
	if original == null or absf(original.length - 299.0 / 30.0) > 0.00002:
		return _fail("import_clock")
	var clip := original.duplicate(true) as Animation
	clip.length = 10.0
	clip.loop_mode = Animation.LOOP_LINEAR
	var rotation_tracks: int = 0
	for index in range(clip.get_track_count()):
		var kind := clip.track_get_type(index)
		var keys := clip.track_get_key_count(index)
		if kind not in TRACK_TYPES or keys <= 0 or not is_zero_approx(clip.track_get_key_time(index, 0)):
			return _fail("native_track_shape")
		if kind == Animation.TYPE_ROTATION_3D and keys == 300:
			for sample in range(300):
				if absf(clip.track_get_key_time(index, sample) - float(sample) / 30.0) > 0.00002:
					return _fail("native_rotation_clock")
			rotation_tracks += 1
		if clip.track_insert_key(index, 10.0, clip.track_get_key_value(index, 0)) < 0:
			return _fail("virtual_seam_key")
	if rotation_tracks < 1:
		return _fail("dense_rotation_tracks")
	var library := player.get_animation_library("")
	library.remove_animation(name)
	if library.add_animation(name, clip) != OK:
		return _fail("native_animation_library")
	player.callback_mode_process = AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_IDLE
	player.autoplay = name
	mesh.hide()
	scene.set_script(Playback)
	scene.set("manifest_sha256", args[2])
	scene.set("player_path", scene.get_path_to(player))
	scene.set("skeleton_path", scene.get_path_to(rig))
	scene.set("source_path", scene.get_path_to(mesh))
	scene.set("source_vertex_ids", ids)
	_own(scene, scene)
	var packed := PackedScene.new()
	if packed.pack(scene) != OK or ResourceSaver.save(packed, OUTPUT,
			ResourceSaver.FLAG_BUNDLE_RESOURCES | ResourceSaver.FLAG_RELATIVE_PATHS) != OK:
		return _fail("portable_save")
	scene.free()
	print("PRIVATE_SKELETAL_SCENE_PACKED")
	quit(0)
