extends RefCounted
## Bound MPFB body300 correction and point normals for Godot 4.7.1 Mobile/Vulkan.
##
## Inputs and outputs use Blender world axes. Position and normal W components
## are respectively 1 and 0. All ordered junctions refer to the original mesh
## before the importer splits vertices at UV seams.

const PROFILE := "GODOT_4_7_1_MOBILE_VULKAN_BODY300_V1"
const VERTICES := 13380
const CORNERS := 53512
const FACES := 13378
const WIDTH := 64
const FRAME_BYTES := VERTICES * 16
const SIZES := {
    "neighbor_ranges.u32": VERTICES * 8, "neighbors.u32": CORNERS * 4,
    "corner_ranges.u32": VERTICES * 8, "corner_indices.u32": CORNERS * 4,
    "corners.u32": CORNERS * 16, "offsets_vec4.f32": CORNERS * 16,
    "face_ranges.u32": FACES * 8, "face_vertices.u32": CORNERS * 4,
    "face_ids.u32": CORNERS * 4,
}
const PROGRAMS := [
    "smooth.glsl", "corners.glsl", "combine.glsl", "normal_faces.glsl", "normal_vertices.glsl",
]
const COMPUTE_HEADER := "#[compute]\n"

var _device: RenderingDevice
var _owned: Array[RID] = []
var _pipelines: Array[RID] = []
var _smoothing: Array[RID] = []
var _stages: Array[RID] = []
var _input: RID
var _positions: RID
var _normals: RID
var _ready := false


func _rejected(code: String) -> Dictionary:
    return {"status": "REJECTED", "code": code}


func setup(spec: Dictionary) -> Dictionary:
    cleanup()
    var version := Engine.get_version_info()
    if [version.major, version.minor, version.patch] != [4, 7, 1] or RenderingServer.get_current_rendering_method() != "mobile" or RenderingServer.get_current_rendering_driver_name() != "vulkan":
        return _rejected("DEVICE_PROFILE")
    if spec.get("profile") != PROFILE or spec.get("vertices") != VERTICES or spec.get("corners") != CORNERS or spec.get("frames") != 300 or spec.get("fps") != 30 or not spec.get("files") is Dictionary:
        return _rejected("BODY300_SPEC")
    var pins: Dictionary = spec["files"]
    var data: Dictionary = {}
    for name: String in SIZES:
        var value := _read(name, SIZES[name], pins.get(name))
        if value.size() != SIZES[name]:
            return _rejected("BINDING_FILE")
        data[name] = value
    if not _valid_binding(data):
        return _rejected("BINDING_TOPOLOGY")
    var programs: Array[String] = []
    for name: String in PROGRAMS:
        var text := _read(name, 32 * 1024, pins.get(name)).get_string_from_utf8()
        if not text.begins_with(COMPUTE_HEADER):
            return _rejected("COMPUTE_FILE")
        programs.append(text.substr(COMPUTE_HEADER.length()))
    if not _prepare_device(data, programs):
        cleanup()
        return _rejected("COMPUTE_SETUP")
    _ready = true
    return {"status": "READY"}


func _read(name: String, limit: int, expected: Variant) -> PackedByteArray:
    if not expected is String or expected.length() != 64:
        return PackedByteArray()
    var stream := FileAccess.open("res://" + name, FileAccess.READ)
    if stream == null or stream.get_length() < 1 or stream.get_length() > limit:
        return PackedByteArray()
    var size := stream.get_length()
    var value := stream.get_buffer(size)
    stream.close()
    if value.size() != size:
        return PackedByteArray()
    var digest := HashingContext.new()
    if digest.start(HashingContext.HASH_SHA256) != OK or digest.update(value) != OK:
        return PackedByteArray()
    return value if digest.finish().hex_encode() == expected else PackedByteArray()


func _valid_ranges(ranges: PackedInt32Array, minimum: int) -> bool:
    var cursor := 0
    for i in range(0, ranges.size(), 2):
        var length := ranges[i + 1]
        if ranges[i] != cursor or length < minimum or length > CORNERS - cursor:
            return false
        cursor += length
    return cursor == CORNERS


func _valid_binding(data: Dictionary) -> bool:
    var neighbors: PackedInt32Array = data["neighbors.u32"].to_int32_array()
    var neighbor_ranges: PackedInt32Array = data["neighbor_ranges.u32"].to_int32_array()
    var corners: PackedInt32Array = data["corners.u32"].to_int32_array()
    var corner_ranges: PackedInt32Array = data["corner_ranges.u32"].to_int32_array()
    var corner_order: PackedInt32Array = data["corner_indices.u32"].to_int32_array()
    var face_ranges: PackedInt32Array = data["face_ranges.u32"].to_int32_array()
    var face_vertices: PackedInt32Array = data["face_vertices.u32"].to_int32_array()
    var face_ids: PackedInt32Array = data["face_ids.u32"].to_int32_array()
    var offsets: PackedFloat32Array = data["offsets_vec4.f32"].to_float32_array()
    if not _valid_ranges(neighbor_ranges, 1) or not _valid_ranges(corner_ranges, 1) or not _valid_ranges(face_ranges, 3):
        return false
    for vertex in range(VERTICES):
        var start := neighbor_ranges[vertex * 2]
        for i in range(start, start + neighbor_ranges[vertex * 2 + 1]):
            if neighbors[i] < 0 or neighbors[i] >= VERTICES or neighbors[i] == vertex:
                return false
    for face in range(FACES):
        var start := face_ranges[face * 2]
        var size := face_ranges[face * 2 + 1]
        for local in range(size):
            var i := start + local
            var current := face_vertices[i]
            var previous := face_vertices[start + ((local + size - 1) % size)]
            var next := face_vertices[start + ((local + 1) % size)]
            var o := i * 4
            if current < 0 or current >= VERTICES or previous == current or next == current or face_ids[i] != face:
                return false
            if corners[o] != previous or corners[o + 1] != current or corners[o + 2] != next or corners[o + 3] != 0:
                return false
            if not Vector3(offsets[o], offsets[o + 1], offsets[o + 2]).is_finite() or offsets[o + 3] != 1.0:
                return false
    var seen := PackedByteArray()
    seen.resize(CORNERS)
    for vertex in range(VERTICES):
        var start := corner_ranges[vertex * 2]
        for i in range(start, start + corner_ranges[vertex * 2 + 1]):
            var corner := corner_order[i]
            if corner < 0 or corner >= CORNERS or seen[corner] != 0 or corners[corner * 4 + 1] != vertex:
                return false
            seen[corner] = 1
    return true


func _prepare_device(data: Dictionary, programs: Array[String]) -> bool:
    _device = RenderingServer.create_local_rendering_device()
    if _device == null:
        return false
    var buffers: Dictionary = {}
    for name: String in SIZES:
        buffers[name] = _buffer(SIZES[name], data[name])
        if not buffers[name].is_valid():
            return false
    _input = _buffer(FRAME_BYTES)
    _positions = _buffer(FRAME_BYTES)
    _normals = _buffer(FRAME_BYTES)
    var alternate := _buffer(FRAME_BYTES)
    var contributions := _buffer(CORNERS * 16)
    var face_normals := _buffer(FACES * 16)
    var shaders: Array[RID] = []
    for program in programs:
        var shader := _pipeline(program)
        if not shader.is_valid():
            return false
        shaders.append(shader)
    var neighbor_ranges: RID = buffers["neighbor_ranges.u32"]
    var neighbors: RID = buffers["neighbors.u32"]
    var corner_ranges: RID = buffers["corner_ranges.u32"]
    var corner_order: RID = buffers["corner_indices.u32"]
    var corners: RID = buffers["corners.u32"]
    _smoothing = [
        _bind(shaders[0], [_input, neighbor_ranges, neighbors, alternate]),
        _bind(shaders[0], [alternate, neighbor_ranges, neighbors, _input]),
    ]
    _stages = [
        _bind(shaders[1], [alternate, corners, buffers["offsets_vec4.f32"], contributions]),
        _bind(shaders[2], [alternate, corner_ranges, corner_order, contributions, _positions]),
        _bind(shaders[3], [_positions, buffers["face_ranges.u32"], buffers["face_vertices.u32"], face_normals]),
        _bind(shaders[4], [_positions, corners, corner_ranges, corner_order, face_normals, buffers["face_ids.u32"], _normals]),
    ]
    for handle in _smoothing + _stages:
        if not handle.is_valid():
            return false
    return true


func _retain(handle: RID) -> RID:
    if handle.is_valid():
        _owned.append(handle)
    return handle


func _buffer(size: int, data := PackedByteArray()) -> RID:
    return _retain(_device.storage_buffer_create(size, data))


func _pipeline(program: String) -> RID:
    var source := RDShaderSource.new()
    source.source_compute = program
    var bytecode := _device.shader_compile_spirv_from_source(source)
    if bytecode == null or not bytecode.compile_error_compute.is_empty():
        return RID()
    var shader := _retain(_device.shader_create_from_spirv(bytecode))
    if not shader.is_valid():
        return RID()
    var pipeline := _retain(_device.compute_pipeline_create(shader))
    if not pipeline.is_valid():
        return RID()
    _pipelines.append(pipeline)
    return shader


func _bind(shader: RID, buffers: Array[RID]) -> RID:
    var uniforms: Array[RDUniform] = []
    for i in range(buffers.size()):
        if not buffers[i].is_valid():
            return RID()
        var uniform := RDUniform.new()
        uniform.uniform_type = RenderingDevice.UNIFORM_TYPE_STORAGE_BUFFER
        uniform.binding = i
        uniform.add_id(buffers[i])
        uniforms.append(uniform)
    return _retain(_device.uniform_set_create(uniforms, shader, 0))


func _dispatch(list: int, pipeline: RID, set: RID, count: int) -> void:
    var push := PackedByteArray()
    push.resize(16)
    push.encode_u32(0, count)
    _device.compute_list_bind_compute_pipeline(list, pipeline)
    _device.compute_list_bind_uniform_set(list, set, 0)
    _device.compute_list_set_push_constant(list, push, push.size())
    _device.compute_list_dispatch(list, ceili(float(count) / WIDTH), 1, 1)


func _valid_frame(frame: PackedFloat32Array, w: float, unit: bool = false) -> bool:
    if frame.size() != VERTICES * 4:
        return false
    for i in range(0, frame.size(), 4):
        var point := Vector3(frame[i], frame[i + 1], frame[i + 2])
        if not point.is_finite() or frame[i + 3] != w or (unit and absf(point.length_squared() - 1.0) > 0.00002):
            return false
    return true


func correct(raw: PackedFloat32Array) -> Dictionary:
    if not _ready:
        return _rejected("NOT_READY")
    if not _valid_frame(raw, 1.0):
        return _rejected("RAW_FRAME")
    if _device.buffer_update(_input, 0, FRAME_BYTES, raw.to_byte_array()) != OK:
        return _rejected("POSITION_UPLOAD")
    var list := _device.compute_list_begin()
    for step in range(5):
        _dispatch(list, _pipelines[0], _smoothing[step % 2], VERTICES)
        _device.compute_list_add_barrier(list)
    var counts := [CORNERS, VERTICES, FACES, VERTICES]
    for stage in range(_stages.size()):
        _dispatch(list, _pipelines[stage + 1], _stages[stage], counts[stage])
        if stage + 1 < _stages.size():
            _device.compute_list_add_barrier(list)
    _device.compute_list_end()
    _device.submit()
    _device.sync()
    var positions := _device.buffer_get_data(_positions).to_float32_array()
    var normals := _device.buffer_get_data(_normals).to_float32_array()
    if not _valid_frame(positions, 1.0) or not _valid_frame(normals, 0.0, true):
        return _rejected("COMPUTE_READBACK")
    return {"status": "OK", "positions": positions, "normals": normals}


func cleanup() -> void:
    _ready = false
    if _device == null:
        return
    # Free uniform sets and pipelines before the resources they reference.
    for i in range(_owned.size() - 1, -1, -1):
        _device.free_rid(_owned[i])
    _stages.clear()
    _smoothing.clear()
    _pipelines.clear()
    _owned.clear()
    _device.free()
    _device = null
