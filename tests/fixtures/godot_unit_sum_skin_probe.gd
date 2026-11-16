extends RefCounted
## Private adapter experiment only. UV2 source IDs are diagnostic metadata.
## Retain every influence; apportion UNORM16 codes to a sum of exactly 65535.
const POLICY := "DIAGNOSTIC_UNIT_SUM_UNORM16_LARGEST_REMAINDER_V1"

static func apply(instance: MeshInstance3D, reference: Array) -> Dictionary:
    var mesh: ArrayMesh = instance.mesh as ArrayMesh
    if mesh == null or mesh.get_surface_count() != 1 or instance.skin == null:
        return {"error": "Require one independently verified skinned surface"}
    var arrays: Array = mesh.surface_get_arrays(0)
    var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
    var uv: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV2]
    var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
    var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
    if uv.size() != vertices.size() or bones.size() != vertices.size()*8 or weights.size() != bones.size():
        return {"error": "Incomplete diagnostic correspondence or eight-slot skin"}
    var format: int = mesh.surface_get_format(0)
    var stride: int = RenderingServer.mesh_surface_get_format_skin_stride(format, vertices.size())
    var bone_offset: int = RenderingServer.mesh_surface_get_format_offset(format, vertices.size(), Mesh.ARRAY_BONES)
    var weight_offset: int = RenderingServer.mesh_surface_get_format_offset(format, vertices.size(), Mesh.ARRAY_WEIGHTS)
    if stride != 32 or bone_offset != 0 or weight_offset != 16:
        return {"error": "Unsupported actual skin-buffer layout"}
    var names: Array[String] = []
    var skeleton: Skeleton3D = instance.get_node_or_null(instance.skeleton) as Skeleton3D
    if skeleton == null:
        return {"error": "Missing original skeleton"}
    for index in range(instance.skin.get_bind_count()):
        var name: String = String(instance.skin.get_bind_name(index))
        if name.is_empty():
            var bone: int = instance.skin.get_bind_bone(index)
            if bone < 0 or bone >= skeleton.get_bone_count():
                return {"error": "Unresolved original bind"}
            name = String(skeleton.get_bone_name(bone))
        names.append(name)
    var buffer := PackedByteArray()
    buffer.resize(stride * vertices.size())
    var desired: Array[int] = []
    var maximum: float = 0.0
    for index in range(vertices.size()):
        var source_id: int = int(round(uv[index].x*255.0)) + 256*int(round((1.0-uv[index].y)*255.0))
        if source_id < 0 or source_id >= reference.size() or not reference[source_id] is Dictionary:
            return {"error": "Missing independently decoded GLB weight row"}
        var row: Dictionary = reference[source_id]
        var total: float = 0.0
        for value in row.values():
            if not is_finite(float(value)) or float(value) <= 0.0:
                return {"error": "Invalid independently decoded GLB weight"}
            total += float(value)
        if abs(total-1.0) > 0.000001:
            return {"error": "GLB row is not normalized within the unchanged serialization bound"}
        var codes: Array[int] = []; var order: Array = []
        var sum_codes: int = 0
        var observed: Dictionary = {}
        for slot in range(8):
            var bind: int = bones[index*8+slot]
            if bind < 0 or bind >= names.size():
                return {"error": "Skin references an invalid actual bind"}
            buffer.encode_u16(index*stride + slot*2, bind)
            var scaled: float = 0.0
            if weights[index*8+slot] > 0.0:
                var name: String = names[bind]
                if not row.has(name) or observed.has(name):
                    return {"error": "Imported positive bone set differs from original GLB"}
                observed[name] = true
                scaled = float(row[name])/total*65535.0
                order.append({"slot": slot, "fraction": scaled-floor(scaled), "name": name})
            var code: int = int(floor(scaled))
            codes.append(code); sum_codes += code
        if observed.size() != row.size():
            return {"error": "Imported positive influence was lost before apportionment"}
        var deficit: int = 65535-sum_codes
        if deficit < 0 or deficit > order.size():
            return {"error": "Invalid unit-sum apportionment"}
        order.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
            return a["fraction"] > b["fraction"] if a["fraction"] != b["fraction"] else a["name"] < b["name"])
        for offset in range(deficit):
            codes[int(order[offset]["slot"])] += 1
        for slot in range(8):
            var code: int = codes[slot]
            if weights[index*8+slot] > 0.0:
                if code <= 0:
                    return {"error": "Positive influence cannot be represented; never prune"}
                var error: float = abs(float(code)/65535.0 - float(row[names[bones[index*8+slot]]])/total)
                if error > 1.0/65535.0 + 0.000000000001:
                    return {"error": "Apportionment exceeded one UNORM16 quantum"}
                maximum = max(maximum, error)
            desired.append(code)
            buffer.encode_u16(index*stride + weight_offset + slot*2, code)
    # Commit only a private in-memory resource copy after all rows validate.
    var copied: ArrayMesh = mesh.duplicate(true) as ArrayMesh
    copied.surface_update_skin_region(0, 0, buffer)
    var changed: Array = copied.surface_get_arrays(0)
    if changed[Mesh.ARRAY_VERTEX] != vertices or changed[Mesh.ARRAY_BONES] != bones:
        return {"error": "Skin buffer update changed geometry or bone identities"}
    var packed: PackedFloat32Array = changed[Mesh.ARRAY_WEIGHTS]
    for index in range(packed.size()):
        if int(round(packed[index]*65535.0)) != desired[index]:
            return {"error": "Actual engine buffer did not retain exact declared codes"}
    instance.mesh = copied
    return {"policy": POLICY, "vertices": vertices.size(), "all_positive_influences_retained": true,
        "all_integer_code_sums_65535": true, "max_relative_encoding_error": maximum,
        "exact_engine_codes_rechecked": true, "original_import_resource_preserved": true}
