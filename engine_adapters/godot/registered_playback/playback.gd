extends Node3D
## Display the live, corrected surface of the embedded native skeletal animation.

const Kernel = preload("res://runtime_kernel.gd")
const POLICY := "UCC_FIRST_PARTY_GODOT_PLAYBACK_V1"
const VERTICES := 13380
const CORNERS := 53512
const MAX_MANIFEST_BYTES := 16 * 1024
const AXIS := Basis(Vector3.RIGHT, Vector3.FORWARD, Vector3.UP)

@export var manifest_sha256: String
@export var player_path: NodePath
@export var skeleton_path: NodePath
@export var source_path: NodePath
@export var source_vertex_ids: PackedInt32Array

var _kernel := Kernel.new()
var _source: MeshInstance3D
var _rig: Skeleton3D
var _player: AnimationPlayer
var _display: MeshInstance3D
var _camera: Camera3D
var _triangles: PackedInt32Array
var _applied: int = 0
var _wraps: int = 0
var _last: float = -1.0
var _failed := false


func playback_status() -> Dictionary:
	return {"applied_frames": _applied, "completed_wraps": _wraps, "last_position": _last,
		"corrected_surface_visible": is_instance_valid(_display) and _display.visible and _display.mesh != null,
		"failed": _failed}


func _manifest() -> Dictionary:
	var file := FileAccess.open("res://playback.json", FileAccess.READ)
	if file == null or file.get_length() < 2 or file.get_length() > MAX_MANIFEST_BYTES:
		return {}
	var raw := file.get_buffer(MAX_MANIFEST_BYTES + 1)
	file.close()
	var hashing := HashingContext.new()
	if hashing.start(HashingContext.HASH_SHA256) != OK or hashing.update(raw) != OK \
			or hashing.finish().hex_encode() != manifest_sha256:
		return {}
	var spec: Variant = JSON.parse_string(raw.get_string_from_utf8())
	if (not spec is Dictionary or spec.size() != 8 or spec.get("schema_version") != 1 or spec.get("policy") != POLICY
			or spec.get("profile") != Kernel.PROFILE or spec.get("vertices") != VERTICES
			or spec.get("corners") != CORNERS or spec.get("frames") != 300 or spec.get("fps") != 30
			or not spec.get("files") is Dictionary):
		return {}
	var names: Array = ["project.godot", "playback.gd", "runtime_kernel.gd"]
	names.append_array(Kernel.PROGRAMS)
	names.append_array(Kernel.SIZES.keys())
	var pins: Dictionary = spec["files"]
	if pins.size() != names.size():
		return {}
	for name: String in names:
		var expected: Variant = pins.get(name)
		var path := "res://" + name
		var length := FileAccess.get_size(path)
		if (not expected is String or expected.length() != 64 or length < 1 or length > 2 * 1024 * 1024
				or FileAccess.get_sha256(path) != expected):
			return {}
	return spec


func _fail(reason: String) -> void:
	_failed = true
	if is_instance_valid(_display):
		_display.hide()
	if is_instance_valid(_player):
		_player.pause()
	_kernel.cleanup()
	push_error("Private Godot skeletal playback stopped: " + reason)


func _ready() -> void:
	_source = get_node_or_null(source_path) as MeshInstance3D
	_rig = get_node_or_null(skeleton_path) as Skeleton3D
	_player = get_node_or_null(player_path) as AnimationPlayer
	if is_instance_valid(_source):
		_source.hide()
	if (_source == null or _rig == null or _player == null or _source.mesh == null or _source.skin == null
			or _source.get_node_or_null(_source.skeleton) != _rig or _rig.get_bone_count() != 163
			or _source.mesh.get_surface_count() != 1 or _source.mesh.get_blend_shape_count() != 12):
		_fail("embedded skin or animation association is invalid")
		return
	var arrays: Array = _source.mesh.surface_get_arrays(0)
	_triangles = arrays[Mesh.ARRAY_INDEX]
	var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	if vertices.size() != source_vertex_ids.size() or _triangles.is_empty() or _triangles.size() % 3 != 0:
		_fail("embedded surface correspondence is invalid")
		return
	var covered := PackedByteArray()
	covered.resize(VERTICES)
	for index in source_vertex_ids:
		if index < 0 or index >= VERTICES:
			_fail("embedded source vertex identity is invalid")
			return
		covered[index] = 1
	if covered.count(1) != VERTICES:
		_fail("embedded source coverage is incomplete")
		return
	var spec := _manifest()
	if spec.is_empty() or _kernel.setup(spec).get("status") != "READY":
		_fail("choose Godot 4.7.1 Mobile/Vulkan and preserve the exact playback resources")
		return
	_setup_scene()
	call_deferred("_play")


func _setup_scene() -> void:
	_display = MeshInstance3D.new()
	_display.name = "CorrectedSurface"
	_display.hide()
	var material := StandardMaterial3D.new()
	material.shading_mode = BaseMaterial3D.SHADING_MODE_PER_PIXEL
	material.albedo_color = Color(0.80, 0.72, 0.62)
	material.roughness = 1.0
	material.metallic = 0.0
	_display.material_override = material
	add_child(_display)
	_camera = Camera3D.new()
	_camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	add_child(_camera)
	_camera.make_current()
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-40, 35, 0)
	light.light_energy = 2.0
	light.shadow_enabled = false
	add_child(light)


func _raw_skin() -> PackedFloat32Array:
	_rig.force_update_all_bone_transforms()
	var baked := _source.bake_mesh_from_current_skeleton_pose()
	if baked == null or baked.get_surface_count() != 1:
		return PackedFloat32Array()
	var points: PackedVector3Array = baked.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
	if points.size() != source_vertex_ids.size():
		return PackedFloat32Array()
	var raw := PackedFloat32Array()
	raw.resize(VERTICES * 4)
	var visited := PackedByteArray()
	visited.resize(VERTICES)
	for vertex in range(points.size()):
		var point := AXIS.inverse() * (_source.global_transform * points[vertex])
		if not point.is_finite():
			return PackedFloat32Array()
		var id := source_vertex_ids[vertex]
		var offset := id * 4
		if visited[id] == 1:
			if point.distance_to(Vector3(raw[offset], raw[offset+1], raw[offset+2])) > 0.000001:
				return PackedFloat32Array()
		else:
			raw[offset] = point.x
			raw[offset+1] = point.y
			raw[offset+2] = point.z
			raw[offset+3] = 1.0
			visited[id] = 1
	return raw


func _show_corrected(positions: PackedFloat32Array, normals: PackedFloat32Array) -> bool:
	if positions.size() != VERTICES * 4 or normals.size() != positions.size():
		return false
	var vertices := PackedVector3Array()
	var directions := PackedVector3Array()
	vertices.resize(source_vertex_ids.size())
	directions.resize(source_vertex_ids.size())
	for vertex in range(VERTICES):
		if positions[vertex*4+3] != 1.0 or normals[vertex*4+3] != 0.0:
			return false
	for vertex in range(source_vertex_ids.size()):
		var i := source_vertex_ids[vertex] * 4
		vertices[vertex] = AXIS * Vector3(positions[i], positions[i+1], positions[i+2])
		directions[vertex] = AXIS * Vector3(normals[i], normals[i+1], normals[i+2])
	var arrays: Array = []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = directions
	arrays[Mesh.ARRAY_INDEX] = _triangles
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	if mesh.get_surface_count() != 1:
		return false
	if _applied == 0:
		var bounds := mesh.get_aabb()
		if not bounds.size.is_finite() or bounds.size.y <= 0.1 or bounds.size.y > 4.0:
			return false
		var center := bounds.get_center()
		_camera.size = 1.20 * maxf(bounds.size.x, bounds.size.y)
		_camera.position = center + Vector3(1.8, 0.18, 3.0) * bounds.size.y
		_camera.look_at(center, Vector3.UP)
	_display.mesh = mesh
	_display.show()
	return true


func _play() -> void:
	while is_inside_tree() and not _failed:
		await RenderingServer.frame_post_draw
		if not is_inside_tree() or _failed:
			return
		if not _player.is_playing():
			_fail("the embedded AnimationPlayer lost its loop")
			return
		var time := _player.current_animation_position
		if not is_finite(time) or time < 0.0 or time > 10.0:
			_fail("the embedded animation clock is invalid")
			return
		if time == _last:
			continue
		var raw := _raw_skin()
		if raw.is_empty():
			_fail("native skin readback or source correspondence failed")
			return
		var result: Dictionary = _kernel.correct(raw)
		if result.get("status") != "OK" or not _show_corrected(result["positions"], result["normals"]):
			_fail("corrected mesh or normals could not be displayed")
			return
		if _last >= 0.0 and time < _last:
			_wraps += 1
		_last = time
		_applied += 1


func _exit_tree() -> void:
	_kernel.cleanup()
