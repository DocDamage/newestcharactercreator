extends SceneTree
var kernel: RefCounted
func _initialize() -> void: call_deferred("_run")
func _nodes(node: Node,kind: String,result: Array) -> void:
    if node.is_class(kind):result.append(node)
    for child in node.get_children():_nodes(child,kind,result)
func _key(point: Vector3) -> String:
    return PackedFloat32Array([0.0 if point.x==0.0 else point.x,0.0 if point.y==0.0 else point.y,0.0 if point.z==0.0 else point.z]).to_byte_array().hex_encode()
func _fail(error: String) -> Dictionary:return {"status":"RUNTIME_ENGINE_CS_REJECTED","error":error,"engine_import_verified":false,"visual_quality_approved":false}
func _validate() -> Dictionary:
    var spec: Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://spec.json"))
    for name in spec["files"]:
        if FileAccess.get_sha256("res://"+name)!=spec["files"][name]:return _fail("Changed runtime input: "+name)
    var count: int=int(spec["vertices"]);var expected:=FileAccess.get_file_as_bytes("res://expected_vec4.f32").to_float32_array()
    if expected.size()!=spec["cases"].size()*count*4:return _fail("Incomplete corrected reference")
    var normal_reference:=FileAccess.get_file_as_bytes("res://expected_normals_vec4.f32").to_float32_array()
    if FileAccess.get_sha256("res://request.json")!=spec["bundle_request_sha256"]:return _fail("Bundle request changed")
    var bundle_request: Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://request.json"))
    for name in bundle_request["files"]:
        if spec["files"].get(name)!=bundle_request["files"][name]:return _fail("Bundle file/request identity differs")
    if bundle_request["runtime_execution_verified"]!=false or bundle_request["distribution_license_review_complete"]!=false:return _fail("Unapproved bundle flags changed")
    kernel=load("res://runtime_kernel.gd").new()
    var ready: Dictionary=kernel.setup(spec)
    if ready.get("status")!="READY":return _fail(JSON.stringify(ready))
    var viewport:=SubViewport.new();viewport.size=Vector2i(256,384);viewport.own_world_3d=true
    viewport.transparent_bg=true;viewport.render_target_update_mode=SubViewport.UPDATE_ALWAYS;root.add_child(viewport)
    var scene: Node=load("res://character.glb").instantiate();viewport.add_child(scene)
    var meshes: Array=[];var players: Array=[];var skeletons: Array=[]
    _nodes(scene,"MeshInstance3D",meshes);_nodes(scene,"AnimationPlayer",players);_nodes(scene,"Skeleton3D",skeletons)
    if meshes.size()!=1 or players.size()!=1 or skeletons.size()!=1:return _fail("Incomplete actual imported rig/morph source")
    var instance: MeshInstance3D=meshes[0];var skeleton: Skeleton3D=skeletons[0];var player: AnimationPlayer=players[0]
    if skeleton.get_bone_count()!=163 or instance.mesh.get_blend_shape_count()!=12:return _fail("Imported family or canonical morphs changed")
    var skin: Dictionary=load("res://ucc_skin_adapter.gd").apply(instance,"res://character.glb","res://skin_plan.json",spec["plan_sha256"])
    if skin.get("status")!="GODOT_SKIN_PLAN_APPLIED":return _fail(JSON.stringify(skin))
    var arrays: Array=instance.mesh.surface_get_arrays(0)
    var vertices: PackedVector3Array=arrays[Mesh.ARRAY_VERTEX];var bones: PackedInt32Array=arrays[Mesh.ARRAY_BONES]
    var weights: PackedFloat32Array=arrays[Mesh.ARRAY_WEIGHTS]
    var indices: Dictionary=JSON.parse_string(FileAccess.get_file_as_string("res://bind_source_indices.json"))
    var ids: Array[int]=[];var covered: Dictionary={}
    for point in vertices:
        var key: String=_key(point)
        if not indices.has(key):return _fail("Missing exact source bind identity")
        var index: int=int(indices[key]);ids.append(index);covered[index]=true
    if covered.size()!=count:return _fail("Complete source coverage lost")
    var source_uv: PackedVector2Array=arrays[Mesh.ARRAY_TEX_UV]
    if source_uv.size()!=vertices.size():return _fail("Imported source UV coverage is incomplete")
    var uv_files: Dictionary={"imported_uv.f32":source_uv.to_byte_array(),
        "imported_uv_source_ids.u32":PackedInt32Array(ids).to_byte_array(),
        "imported_uv_triangles.u32":arrays[Mesh.ARRAY_INDEX].to_byte_array()}
    var uv_hashes: Dictionary={}
    for name in uv_files:
        var stream:=FileAccess.open("res://"+name,FileAccess.WRITE)
        if stream==null:return _fail("Cannot retain imported UV evidence")
        stream.store_buffer(uv_files[name]);stream.close()
        uv_hashes[name]=FileAccess.get_sha256("res://"+name)
    var skin_bytes:=PackedByteArray();skin_bytes.resize(vertices.size()*32)
    for index in range(vertices.size()):
        for slot in range(8):
            skin_bytes.encode_u16(index*32+slot*2,bones[index*8+slot])
            skin_bytes.encode_u16(index*32+16+slot*2,int(round(weights[index*8+slot]*65535.0)))
    var clips: Array=[]
    for name in player.get_animation_list():
        if String(name)!="RESET":clips.append(name)
    if clips.size()!=1:return _fail("Native source clip split or missing")
    var clip: Animation=player.get_animation(clips[0])
    if abs(clip.length-299.0/30.0)>0.000001:return _fail("Native source clip duration changed")
    player.callback_mode_process=AnimationMixer.ANIMATION_CALLBACK_MODE_PROCESS_MANUAL;player.play(clips[0]);player.advance(0.)
    var morphs: Dictionary={}
    for index in range(12):morphs[String(instance.mesh.get_blend_shape_name(index))]=index
    var probe:=MeshInstance3D.new();scene.add_child(probe);probe.visible=false
    instance.visible=false
    var displayed:=MeshInstance3D.new();viewport.add_child(displayed)
    var material:=ShaderMaterial.new();material.shader=load("res://clay.gdshader");displayed.material_override=material
    var camera:=Camera3D.new();viewport.add_child(camera);camera.position=Vector3(0,1,4);camera.current=true;camera.projection=Camera3D.PROJECTION_ORTHOGONAL
    var output_arrays: Array=arrays.duplicate(true);output_arrays[Mesh.ARRAY_BONES]=null;output_arrays[Mesh.ARRAY_WEIGHTS]=null
    var rows: Array=[];var maximum: float=0.;var pixel_hashes: Dictionary={}
    var output:=FileAccess.open("res://actual_corrected_world.f32",FileAccess.WRITE)
    var normals_output:=FileAccess.open("res://actual_normals_vec4.f32",FileAccess.WRITE)
    for sample in range(spec["cases"].size()):
        var query: Dictionary=spec["cases"][sample]
        var time_value: float=PackedFloat32Array([(float(query["frame"])-1.0+float(query["subframe"]))/30.0])[0]
        player.seek(time_value,true)
        var face: Dictionary=query["facial_parameters"]
        for role in spec["roles"]:
            for family in spec["race_mix"]:
                var name: String="UCC_EXPR_V1_"+String(role)+"_"+String(family)
                if not morphs.has(name):return _fail("Canonical control missing")
                var value: float=PackedFloat32Array([float(face.get(role,0.))*float(spec["race_mix"][family])])[0]
                instance.set_blend_shape_value(morphs[name],value)
        skeleton.force_update_all_bone_transforms();await process_frame;await RenderingServer.frame_post_draw
        var morph: ArrayMesh=instance.bake_mesh_from_current_blend_shape_mix();morph.surface_update_skin_region(0,0,skin_bytes)
        probe.mesh=morph;probe.skin=instance.skin;probe.skeleton=probe.get_path_to(skeleton);probe.global_transform=instance.global_transform
        await process_frame;await RenderingServer.frame_post_draw
        var baked: ArrayMesh=probe.bake_mesh_from_current_skeleton_pose()
        var raw_positions: PackedVector3Array=baked.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
        if raw_positions.size()!=vertices.size():return _fail("Actual raw engine topology changed")
        var raw:=PackedFloat32Array();raw.resize(count*4)
        var visited:=PackedByteArray();visited.resize(count)
        for index in range(raw_positions.size()):
            var point: Vector3=probe.global_transform*raw_positions[index];point=Vector3(point.x,-point.z,point.y)
            var id: int=ids[index];var offset: int=id*4
            if visited[id]!=0:
                if point.distance_to(Vector3(raw[offset],raw[offset+1],raw[offset+2]))>0.000001:return _fail("UV seam source positions disagree")
            else:
                raw[offset]=point.x;raw[offset+1]=point.y;raw[offset+2]=point.z;raw[offset+3]=1.;visited[id]=1
        var corrected: Dictionary=kernel.correct(raw)
        if corrected.get("status")!="OK":return _fail(JSON.stringify(corrected))
        var values: PackedFloat32Array=corrected["positions"];output.store_buffer(values.to_byte_array())
        var error: float=0.
        for vertex in range(count):
            var offset: int=vertex*4;var reference: int=(sample*count+vertex)*4
            var point:=Vector3(values[offset],values[offset+1],values[offset+2])
            var target:=Vector3(expected[reference],expected[reference+1],expected[reference+2])
            if not point.is_finite():return _fail("Nonfinite actual runtime result")
            error=max(error,point.distance_to(target))
        maximum=max(maximum,error)
        if error>0.00001:return _fail("Imported runtime correction exceeds fixed limit: "+JSON.stringify({"sample":sample,"case":query,"error_m":error}))
        var normal_values: PackedFloat32Array=corrected["normals"];normals_output.store_buffer(normal_values.to_byte_array())
        var max_angle: float=0.;var normal_error: float=0.
        for vertex in range(count):
            var offset: int=vertex*4;var reference: int=(sample*count+vertex)*4
            var n:=Vector3(normal_values[offset],normal_values[offset+1],normal_values[offset+2])
            var target:=Vector3(normal_reference[reference],normal_reference[reference+1],normal_reference[reference+2])
            if not n.is_finite() or abs(n.length()-1.)>0.00001:return _fail("Nonfinite or nonunit corrected normal")
            normal_error=max(normal_error,n.distance_to(target))
            max_angle=max(max_angle,rad_to_deg(acos(clamp(n.normalized().dot(target.normalized()),-1.,1.))))
        if max_angle>0.1 or normal_error>0.002:return _fail("Normal exceeds declared limit: "+JSON.stringify({"sample":sample,"angle_degrees":max_angle,"vector_error":normal_error}))
        var normals:=PackedVector3Array();normals.resize(vertices.size())
        for index in range(vertices.size()):
            var offset: int=ids[index]*4;normals[index]=Vector3(normal_values[offset],normal_values[offset+2],-normal_values[offset+1])
        output_arrays[Mesh.ARRAY_NORMAL]=normals
        var positions:=PackedVector3Array();positions.resize(vertices.size())
        var bounds: AABB
        for index in range(vertices.size()):
            var offset: int=ids[index]*4;var point:=Vector3(values[offset],values[offset+2],-values[offset+1]);positions[index]=point
            if index==0:bounds=AABB(point,Vector3.ZERO)
            else:bounds=bounds.expand(point)
        output_arrays[Mesh.ARRAY_VERTEX]=positions
        var rendered:=ArrayMesh.new();rendered.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES,output_arrays)
        var rendered_uv: PackedVector2Array=rendered.surface_get_arrays(0)[Mesh.ARRAY_TEX_UV]
        if rendered_uv.to_byte_array()!=uv_files["imported_uv.f32"]:return _fail("Runtime corrected mesh changed source UVs")
        displayed.mesh=rendered
        var view: Dictionary=spec["views"][sample];var center:=Vector3(view["center"][0],view["center"][2],-view["center"][1])
        camera.size=view["size"];camera.position=center+Vector3(0,0,view["distance"]);camera.look_at(center)
        await process_frame;await RenderingServer.frame_post_draw
        var image:=viewport.get_texture().get_image();image.convert(Image.FORMAT_RGBA8)
        var pixels:=image.get_data();var visible: int=0
        for offset in range(3,pixels.size(),4):
            if pixels[offset]>0:visible+=1
        if visible<100:return _fail("Runtime corrected character did not draw")
        var hasher:=HashingContext.new();hasher.start(HashingContext.HASH_SHA256);hasher.update(pixels)
        var sha: String=hasher.finish().hex_encode();pixel_hashes[sha]=true
        var path: String="res://runtime_%04d.png"%sample
        if image.save_png(path)!=OK:return _fail("Cannot retain actual corrected draw")
        rows.append({"sample":sample,"case":query,"max_world_error_m":error,"compute_microseconds":corrected["microseconds"],
            "max_normal_angle_degrees":max_angle,"max_normal_vector_error":normal_error,"rgba_sha256":sha,"png_sha256":FileAccess.get_sha256(path),"visible_pixels":visible})
    output.close();normals_output.close()
    return {"status":"ACTUAL_IMPORTED_GODOT_RUNTIME_CS_AND_FACE_SAMPLES_VERIFIED","samples":rows,
        "max_world_error_m":maximum,"distinct_rendered_frames":pixel_hashes.size(),"source_vertices":count,"imported_vertices":vertices.size(),
        "bones":163,"canonical_morphs":12,"GPU_runtime_correction_applied":true,"runtime_corrected_geometry_rendered":true,
        "uv_runtime_meshes_checked":rows.size(),"uv_readback_sha256":uv_hashes,
        "godot_version":Engine.get_version_info(),"rendering_device":RenderingServer.get_video_adapter_name(),"skin_adapter":skin,
        "unshaded_visibility_probe_only":false,"defined_Lambert_clay_shader":true,"actual_materials_verified":false,"material_appearance_verified":false,"vertex_shader_positions_directly_verified":false,
        "engine_import_verified":false,"shipping_runtime_implemented":false,"visual_quality_approved":false}
func _run() -> void:
    var report: Dictionary=await _validate()
    if kernel!=null:kernel.cleanup()
    var file:=FileAccess.open("res://measurement.json",FileAccess.WRITE);file.store_string(JSON.stringify(report,"  ")+"\n");file.close()
    print(report["status"]);quit(0 if report["status"]=="ACTUAL_IMPORTED_GODOT_RUNTIME_CS_AND_FACE_SAMPLES_VERIFIED" else 13)
