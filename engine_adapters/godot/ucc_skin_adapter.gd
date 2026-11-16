extends RefCounted
## Bounded V1 skin-buffer adapter. This does not admit rights or validate motion.
const PROFILE := "MPFB_GODOT_UNIT_SUM_SKIN_V1"
const POLICY := "UNIT_SUM_UNORM16_LARGEST_REMAINDER_V1"
const CORRESPONDENCE := "FLOAT32_POSITION_AND_IMPORTED_POSITIVE_BONE_CODES_V1"
const PLAN_META := "ucc_godot_skin_plan_sha256_v1"
const MAX_PLAN_BYTES := 64 * 1024 * 1024

static func _error(code: String, message: String) -> Dictionary:
    return {"status": "GODOT_SKIN_ADAPTER_REJECTED", "code": code, "message": message,
        "engine_import_verified": false}

static func _hash(bytes: PackedByteArray) -> String:
    var digest := HashingContext.new()
    digest.start(HashingContext.HASH_SHA256); digest.update(bytes)
    return digest.finish().hex_encode()

static func _integer(value: Variant, low: int, high: int) -> bool:
    return (typeof(value) == TYPE_FLOAT or typeof(value) == TYPE_INT) and is_finite(float(value)) and float(value) == floor(float(value)) and value >= low and value <= high

static func _key(point: Vector3, codes: Dictionary) -> String:
    var xyz := PackedFloat32Array([0.0 if point.x == 0.0 else point.x,
        0.0 if point.y == 0.0 else point.y, 0.0 if point.z == 0.0 else point.z])
    var names: Array = codes.keys(); names.sort()
    var parts := PackedStringArray()
    for name in names:
        parts.append(String(name) + "=" + str(int(codes[name])))
    return xyz.to_byte_array().hex_encode() + ":" + ";".join(parts)

static func apply(instance: MeshInstance3D, candidate_path: String, plan_path: String,
        expected_plan_sha256: String) -> Dictionary:
    if not is_instance_valid(instance):
        return _error("ENGINE_INSTANCE", "Require a live imported mesh instance")
    var version: Dictionary = Engine.get_version_info()
    if version["major"] != 4 or version["minor"] != 7:
        return _error("ENGINE_VERSION", "This skin encoding profile requires Godot 4.7")
    var hex := RegEx.create_from_string("^[0-9a-f]{64}$")
    if hex.search(expected_plan_sha256) == null:
        return _error("PLAN_HASH", "Require an exact independently bound plan SHA-256")
    # Bundle admission owns canonical filesystem checks. Inside Godot, accept
    # only project resources, with no path traversal or URL/network handling.
    for path in [candidate_path, plan_path]:
        if not path.begins_with("res://") or path.contains("..") or path.contains("\\") or path.contains("?"):
            return _error("RESOURCE_PATH", "Require bounded project-local resource paths")
    var file := FileAccess.open(plan_path, FileAccess.READ)
    if file == null or file.get_length() < 2 or file.get_length() > MAX_PLAN_BYTES:
        return _error("PLAN_SIZE", "Missing or oversized skin plan")
    var raw: PackedByteArray = file.get_buffer(MAX_PLAN_BYTES + 1); file.close()
    if raw.size() > MAX_PLAN_BYTES or _hash(raw) != expected_plan_sha256:
        return _error("PLAN_HASH", "Skin plan changed after independent inspection")
    var parsed: Variant = JSON.parse_string(raw.get_string_from_utf8())
    if not parsed is Dictionary:
        return _error("PLAN_JSON", "Malformed skin plan")
    var plan: Dictionary = parsed
    if not _integer(plan.get("schema_version"), 1, 1) or plan.get("profile") != PROFILE or plan.get("policy") != POLICY or plan.get("correspondence") != CORRESPONDENCE:
        return _error("PLAN_VERSION", "Unsupported skin-plan contract")
    if typeof(plan.get("candidate_sha256")) != TYPE_STRING or hex.search(plan["candidate_sha256"]) == null or FileAccess.get_sha256(candidate_path) != plan["candidate_sha256"]:
        return _error("CANDIDATE_HASH", "Imported candidate differs from the bound GLB")
    if not _integer(plan.get("vertex_count"), 1, 100000) or not plan.get("entries") is Dictionary or plan["entries"].size() < 1 or plan["entries"].size() > int(plan["vertex_count"]):
        return _error("PLAN_COVERAGE", "Invalid bounded vertex coverage")
    if not plan.get("bone_names") is Array or plan["bone_names"].is_empty() or plan["bone_names"].size() > 512:
        return _error("PLAN_BONES", "Missing bounded original bone names")
    var name_pattern := RegEx.create_from_string("^[A-Za-z0-9_.-]{1,128}$")
    var known: Dictionary = {}
    for name in plan["bone_names"]:
        if typeof(name) != TYPE_STRING or name_pattern.search(name) == null or known.has(name):
            return _error("PLAN_BONES", "Invalid or duplicate original bone name")
        known[name] = true
    var groups: Dictionary = plan["entries"]
    var target_groups: Dictionary = {}
    var total: int = 0
    var key_pattern := RegEx.create_from_string("^[0-9a-f]{24}:[A-Za-z0-9_.=;\\-]+$")
    for key in groups:
        var entry: Variant = groups[key]
        if typeof(key) != TYPE_STRING or key.length() > 1200 or key_pattern.search(key) == null or not entry is Dictionary or not _integer(entry.get("count"), 1, int(plan["vertex_count"])) or not entry.get("codes") is Dictionary:
            return _error("PLAN_ENTRY", "Malformed vertex correspondence entry")
        var codes: Dictionary = entry["codes"]
        if codes.is_empty() or codes.size() > 8:
            return _error("PLAN_CODES", "Invalid positive influence count")
        var sum_codes: int = 0
        for name in codes:
            if not known.has(name) or not _integer(codes[name], 1, 65535):
                return _error("PLAN_CODES", "Invalid code or missing original bone")
            sum_codes += int(codes[name])
        if sum_codes != 65535:
            return _error("PLAN_CODES", "Declared codes must sum exactly to 65535")
        # Position bytes are already canonical float32. Target signatures also
        # permit idempotent application, with multiplicities checked in full.
        var position_bytes: PackedByteArray = String(key).substr(0, 24).hex_decode()
        var xyz: PackedFloat32Array = position_bytes.to_float32_array()
        var point := Vector3(xyz[0], xyz[1], xyz[2])
        if not point.is_finite():
            return _error("PLAN_POSITION", "Nonfinite correspondence position")
        var target_key: String = _key(point, codes)
        if not target_groups.has(target_key):
            target_groups[target_key] = {"count": 0, "codes": codes}
        target_groups[target_key]["count"] += int(entry["count"])
        total += int(entry["count"])
    if total != int(plan["vertex_count"]):
        return _error("PLAN_COVERAGE", "Correspondence multiplicities do not cover the candidate")
    var mesh: ArrayMesh = instance.mesh as ArrayMesh
    var skeleton: Skeleton3D = instance.get_node_or_null(instance.skeleton) as Skeleton3D
    if mesh == null or mesh.get_surface_count() != 1 or instance.skin == null or skeleton == null:
        return _error("ENGINE_SKIN", "Require one actual registered skinned surface")
    var names: Array[String] = []
    var bound: Dictionary = {}
    for index in range(instance.skin.get_bind_count()):
        var name: String = String(instance.skin.get_bind_name(index))
        if name.is_empty():
            var bone: int = instance.skin.get_bind_bone(index)
            if bone < 0 or bone >= skeleton.get_bone_count():
                return _error("ENGINE_BONES", "Unresolved actual bind")
            name = String(skeleton.get_bone_name(bone))
        if not known.has(name) or bound.has(name):
            return _error("ENGINE_BONES", "Imported bind identities differ from the original")
        names.append(name); bound[name] = true
    if bound.size() != known.size():
        return _error("ENGINE_BONES", "An original bind was lost")
    var arrays: Array = mesh.surface_get_arrays(0)
    var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
    var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
    var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
    if vertices.size() != int(plan["vertex_count"]) or weights.size() != vertices.size()*8 or bones.size() != weights.size():
        return _error("ENGINE_COVERAGE", "Imported positions or eight-slot influences are incomplete")
    var format: int = mesh.surface_get_format(0)
    var stride: int = RenderingServer.mesh_surface_get_format_skin_stride(format, vertices.size())
    var bone_offset: int = RenderingServer.mesh_surface_get_format_offset(format, vertices.size(), Mesh.ARRAY_BONES)
    var weight_offset: int = RenderingServer.mesh_surface_get_format_offset(format, vertices.size(), Mesh.ARRAY_WEIGHTS)
    if stride != 32 or bone_offset != 0 or weight_offset != 16:
        return _error("ENGINE_LAYOUT", "Unsupported actual skin-buffer layout")
    var selected: Dictionary = target_groups if instance.get_meta(PLAN_META, "") == expected_plan_sha256 else groups
    var observed: Dictionary = {}
    var buffer := PackedByteArray(); buffer.resize(stride*vertices.size())
    var desired: Array[int] = []
    for index in range(vertices.size()):
        var actual: Dictionary = {}
        for slot in range(8):
            var bind: int = bones[index*8+slot]
            if bind < 0 or bind >= names.size():
                return _error("ENGINE_BONES", "Surface references a missing actual bind")
            var weight: float = weights[index*8+slot]
            if not is_finite(weight) or weight < 0.0 or weight > 1.0:
                return _error("ENGINE_WEIGHT", "Invalid actual engine weight")
            if weight > 0.0:
                if actual.has(names[bind]):
                    return _error("ENGINE_WEIGHT", "Duplicate actual positive influence")
                actual[names[bind]] = int(round(weight*65535.0))
        var key: String = _key(vertices[index], actual)
        if not selected.has(key):
            return _error("ENGINE_CORRESPONDENCE", "Imported vertex has no exact unambiguous correspondence")
        var codes: Dictionary = selected[key]["codes"]
        if codes.size() != actual.size():
            return _error("ENGINE_WEIGHT", "Positive influence set changed")
        observed[key] = int(observed.get(key, 0)) + 1
        for slot in range(8):
            var bind: int = bones[index*8+slot]
            var code: int = int(codes.get(names[bind], 0)) if weights[index*8+slot] > 0.0 else 0
            if weights[index*8+slot] > 0.0 and code <= 0:
                return _error("ENGINE_WEIGHT", "Never discard a positive influence")
            buffer.encode_u16(index*stride+slot*2, bind)
            buffer.encode_u16(index*stride+weight_offset+slot*2, code)
            desired.append(code)
    if observed.size() != selected.size():
        return _error("ENGINE_CORRESPONDENCE", "Imported correspondence coverage is incomplete")
    for key in selected:
        if int(observed[key]) != int(selected[key]["count"]):
            return _error("ENGINE_CORRESPONDENCE", "Imported vertex multiplicity changed")
    var copied: ArrayMesh = mesh.duplicate(true) as ArrayMesh
    copied.surface_set_material(0, mesh.surface_get_material(0))
    copied.surface_update_skin_region(0, 0, buffer)
    var changed: Array = copied.surface_get_arrays(0)
    for index in range(Mesh.ARRAY_MAX):
        if index != Mesh.ARRAY_WEIGHTS and changed[index] != arrays[index]:
            return _error("ENGINE_READBACK", "Skin update changed another vertex attribute")
    if copied.surface_get_blend_shape_arrays(0) != mesh.surface_get_blend_shape_arrays(0):
        return _error("ENGINE_READBACK", "Skin update changed original morphs")
    var packed: PackedFloat32Array = changed[Mesh.ARRAY_WEIGHTS]
    for index in range(packed.size()):
        if int(round(packed[index]*65535.0)) != desired[index]:
            return _error("ENGINE_READBACK", "Graphics backend did not retain exact declared codes")
    instance.mesh = copied
    instance.set_meta(PLAN_META, expected_plan_sha256)
    return {"status": "GODOT_SKIN_PLAN_APPLIED", "schema_version": 1, "policy": POLICY,
        "candidate_sha256": plan["candidate_sha256"], "plan_sha256": expected_plan_sha256,
        "matched_vertices": vertices.size(), "diagnostic_UV_required": false,
        "all_positive_influences_retained": true, "exact_integer_codes_rechecked": true,
        "original_resource_preserved": true, "engine_import_verified": false}
