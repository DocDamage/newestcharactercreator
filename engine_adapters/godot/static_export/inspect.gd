extends RefCounted
const Adapter = preload("ucc_skin_adapter.gd")

static func nodes(node: Node, kind: String, result: Array):
    if node.is_class(kind): result.append(node)
    for child in node.get_children(): nodes(child, kind, result)

static func key(point: Vector3, uv: Vector2) -> String:
    var values = PackedFloat32Array([0.0 if point.x == 0.0 else point.x, 0.0 if point.y == 0.0 else point.y,
        0.0 if point.z == 0.0 else point.z, 0.0 if uv.x == 0.0 else uv.x, 0.0 if uv.y == 0.0 else uv.y])
    return values.to_byte_array().hex_encode()

static func skin(instance: MeshInstance3D, skeleton: Skeleton3D, plan: Dictionary) -> Dictionary:
    if instance.skin == null: return {"error":"Missing saved skin"}
    var names: Array[String] = []
    for index in range(instance.skin.get_bind_count()):
        var name = String(instance.skin.get_bind_name(index))
        if name.is_empty():
            var bone = instance.skin.get_bind_bone(index)
            if bone < 0 or bone >= skeleton.get_bone_count(): return {"error":"Unresolved skin bind"}
            name = String(skeleton.get_bone_name(bone))
        if name not in plan["bone_names"] or name in names or skeleton.find_bone(name)<0: return {"error":"Missing or duplicate original bind"}
        names.append(name)
    if names.size() != 163: return {"error":"Incomplete original binds"}
    var groups: Dictionary = {}
    for original in plan["entries"]:
        var entry = plan["entries"][original]
        var target = original.substr(0,24) + ":"
        var codes: Dictionary = entry["codes"]
        var ordered = codes.keys(); ordered.sort()
        var parts = PackedStringArray()
        for name in ordered: parts.append(String(name) + "=" + str(int(codes[name])))
        target += ";".join(parts)
        groups[target] = int(groups.get(target,0)) + int(entry["count"])
    var arrays = instance.mesh.surface_get_arrays(0)
    var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
    var bones: PackedInt32Array = arrays[Mesh.ARRAY_BONES]
    var weights: PackedFloat32Array = arrays[Mesh.ARRAY_WEIGHTS]
    if bones.size()!=vertices.size()*8 or weights.size()!=bones.size(): return {"error":"Eight-influence skin missing"}
    var observed: Dictionary = {}
    for index in range(vertices.size()):
        var codes: Dictionary = {}; var total = 0
        for slot in range(8):
            var bind = bones[index*8+slot]; var value = weights[index*8+slot]
            if bind<0 or bind>=names.size() or not is_finite(value) or value<0.0 or value>1.0: return {"error":"Invalid saved skin slot"}
            var code = int(round(value*65535.0)); total += code
            if code>0:
                if codes.has(names[bind]): return {"error":"Duplicate positive saved influence"}
                codes[names[bind]]=code
        if total!=65535: return {"error":"Saved skin codes do not sum to one"}
        var target = Adapter._key(vertices[index],codes)
        if not groups.has(target): return {"error":"Saved skin differs from the admitted exact correspondence"}
        observed[target]=int(observed.get(target,0))+1
    if observed!=groups: return {"error":"Saved skin multiplicities changed"}
    return {"unit_sum_verified":true,"positive_influences_retained":true,"vertices":vertices.size()}

static func inspect(model: Node, base: String, request: Dictionary) -> Dictionary:
    var meshes: Array = []; var skeletons: Array = []; var players: Array = []
    nodes(model,"MeshInstance3D",meshes); nodes(model,"Skeleton3D",skeletons); nodes(model,"AnimationPlayer",players)
    if meshes.size()!=1 or skeletons.size()!=1 or skeletons[0].get_bone_count()!=163: return {"error":"Imported rig structure differs"}
    for player in players:
        for name in player.get_animation_list():
            if name!="RESET": return {"error":"Static character cannot include animation clips"}
    var instance: MeshInstance3D = meshes[0]
    var mesh: ArrayMesh = instance.mesh as ArrayMesh
    if mesh==null or mesh.get_surface_count()!=1 or mesh.get_blend_shape_count()!=12: return {"error":"Imported mesh/facial controls differ"}
    if instance.material_override!=null or instance.get_surface_override_material(0)!=null: return {"error":"Material overrides are forbidden"}
    var material: StandardMaterial3D = mesh.surface_get_material(0) as StandardMaterial3D
    if material==null: return {"error":"Owned imported material missing"}
    var spec: Dictionary = request["material_spec"]; var expected: Array = spec["base_color_srgb"]
    var color: Color = material.albedo_color
    var color_error = maxf(maxf(absf(color.r-expected[0]),absf(color.g-expected[1])),maxf(absf(color.b-expected[2]),absf(color.a-1.0)))
    if color_error>1e-6 or absf(material.roughness-spec["roughness"])>1e-6 or material.metallic!=0.0 or material.transparency!=BaseMaterial3D.TRANSPARENCY_DISABLED or material.cull_mode!=BaseMaterial3D.CULL_BACK:
        return {"error":"Imported owned PBR fields differ"}
    for slot in range(BaseMaterial3D.TEXTURE_MAX):
        if material.get_texture(slot)!=null: return {"error":"Unexpected texture in color-only export"}
    var plan: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(base+"skin_plan.json"))
    var skin_result = skin(instance,skeletons[0],plan)
    if skin_result.has("error"): return skin_result
    var reference: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(base+"morph_reference.json"))
    var values: PackedFloat32Array = FileAccess.get_file_as_bytes(base+"morph_reference.bin").to_float32_array()
    if values.size()!=int(reference["entries"])*39: return {"error":"Incomplete facial reference data"}
    var arrays = mesh.surface_get_arrays(0)
    var vertices: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
    var uv: PackedVector2Array = arrays[Mesh.ARRAY_TEX_UV]
    var triangles: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
    if vertices.size()!=14517 or uv.size()!=vertices.size() or triangles.size()!=26756*3: return {"error":"Visible surface/UV coverage differs"}
    var ids: Array[int] = []
    for index in range(vertices.size()):
        var lookup = key(vertices[index],uv[index])
        if not reference["lookup"].has(lookup): return {"error":"Exact position/UV correspondence missing"}
        ids.append(int(reference["lookup"][lookup]))
    await model.get_tree().process_frame
    var rest_mesh = instance.bake_mesh_from_current_skeleton_pose()
    if rest_mesh==null: return {"error":"Actual rest-skin baking failed"}
    var rest: PackedVector3Array = rest_mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
    if rest.size()!=vertices.size(): return {"error":"Incomplete actual rest skin"}
    var rest_error = 0.0
    for index in range(rest.size()):
        var error = rest[index].distance_to(vertices[index])
        if not is_finite(error) or error>1e-5: return {"error":"Actual bind/rest skin differs from the saved surface"}
        rest_error=maxf(rest_error,error)
    var maximum = 0.0
    for shape in range(12):
        if String(mesh.get_blend_shape_name(shape))!=String(reference["names"][shape]): return {"error":"Facial control identity/order changed"}
        instance.set_blend_shape_value(shape,1.0)
        await model.get_tree().process_frame
        var baked = instance.bake_mesh_from_current_blend_shape_mix()
        if baked==null: return {"error":"Actual Godot facial baking failed"}
        var points: PackedVector3Array = baked.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
        if points.size()!=vertices.size(): return {"error":"Baked face geometry is incomplete"}
        for index in range(points.size()):
            var offset = ids[index]*39
            var basis = Vector3(values[offset],values[offset+1],values[offset+2])
            offset += (shape+1)*3
            var delta = Vector3(values[offset],values[offset+1],values[offset+2])
            var error = points[index].distance_to(basis+delta)
            if not is_finite(error) or error>float(reference["morph_limit_m"]): return {"error":"Actual facial shape differs from original GLB deltas"}
            maximum=maxf(maximum,error)
        instance.set_blend_shape_value(shape,0.0)
    await model.get_tree().process_frame
    return {"bones":163,"morphs":12,"animation_clips":0,"vertices":vertices.size(),"triangles":26756,
        "exact_position_UV_correspondence":true,"maximum_rest_skin_error_m":rest_error,"maximum_morph_error_m":maximum,"skin":skin_result,
        "material":{"base_color_srgb":[color.r,color.g,color.b],"roughness":material.roughness,"metallic":material.metallic,
            "maximum_color_error":color_error,"textures":0,"override":false}}
