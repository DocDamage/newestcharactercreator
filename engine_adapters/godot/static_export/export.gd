extends SceneTree
## Trusted local exporter/checker. No @tool, network access or asset scripts.
const Inspect = preload("inspect.gd")
const Adapter = preload("ucc_skin_adapter.gd")
var base: String

func fail(message: String):
    push_error(message)
    quit(2)

func _initialize(): call_deferred("run")

func own_children(node: Node, owner_node: Node):
    for child in node.get_children():
        child.owner=owner_node
        own_children(child,owner_node)

func save_scene(node: Node,path: String) -> bool:
    var packed = PackedScene.new()
    return packed.pack(node)==OK and ResourceSaver.save(packed,path,ResourceSaver.FLAG_RELATIVE_PATHS|ResourceSaver.FLAG_BUNDLE_RESOURCES)==OK

func environment(parent: Node,center: Vector3,height: float):
    var world = WorldEnvironment.new(); world.environment=Environment.new()
    world.environment.background_mode=Environment.BG_COLOR
    world.environment.background_color=Color(.035,.045,.065,0.)
    world.environment.ambient_light_source=Environment.AMBIENT_SOURCE_COLOR
    world.environment.ambient_light_color=Color.WHITE
    world.environment.ambient_light_energy=.45
    parent.add_child(world);world.owner=parent
    var light = DirectionalLight3D.new();light.rotation_degrees=Vector3(-30,-25,0);light.light_energy=1.5
    parent.add_child(light);light.owner=parent
    var camera = Camera3D.new();camera.projection=Camera3D.PROJECTION_ORTHOGONAL;camera.size=height*1.15
    parent.add_child(camera);camera.owner=parent;camera.position=center+Vector3(0,0,height*2);camera.look_at(center,Vector3.UP);camera.current=true

func run():
    base=get_script().resource_path.get_base_dir()+"/"
    var args = OS.get_cmdline_user_args()
    if args.size()!=2 or args[0] not in ["build","verify"] or FileAccess.get_sha256(base+"request.json")!=args[1]: return fail("Static export request identity changed")
    var request: Variant = JSON.parse_string(FileAccess.get_file_as_string(base+"request.json"))
    if not request is Dictionary or request.get("policy")!="UCC_PRIVATE_STATIC_GODOT_EXPORT_V1" or request.get("schema_version")!=1: return fail("Unsupported static export request")
    var version = Engine.get_version_info()
    if version["major"]!=4 or version["minor"]!=7: return fail("This verified export profile needs Godot 4.7")
    for name in request["files"]:
        if name.contains("/") or name.contains("..") or FileAccess.get_sha256(base+name)!=request["files"][name]: return fail("Static export input changed: "+name)
    var viewport = SubViewport.new();viewport.size=Vector2i(512,512);viewport.own_world_3d=true;viewport.transparent_bg=true
    viewport.render_target_update_mode=SubViewport.UPDATE_ALWAYS;root.add_child(viewport)
    var filename = "character.glb" if args[0]=="build" else "character.tscn"
    var packed: PackedScene = load(base+filename) as PackedScene
    if packed==null: return fail("Actual imported/saved character scene is missing")
    var model = packed.instantiate();viewport.add_child(model)
    var meshes: Array=[];Inspect.nodes(model,"MeshInstance3D",meshes)
    if meshes.size()!=1: return fail("Expected one actual imported body surface")
    if args[0]=="build":
        var changed = Adapter.apply(meshes[0],base+"character.glb",base+"skin_plan.json",request["files"]["skin_plan.json"])
        if changed.get("status")!="GODOT_SKIN_PLAN_APPLIED": return fail("Unit-sum skin adapter rejected: "+JSON.stringify(changed))
    var observed: Dictionary = await Inspect.inspect(model,base,request)
    if observed.has("error"): return fail(observed["error"])
    if args[0]=="build":
        model.scene_file_path="";own_children(model,model)
        if not save_scene(model,base+"character.tscn"): return fail("Could not save the real rigged character")
    var box: AABB = meshes[0].get_aabb()
    var center: Vector3 = meshes[0].global_transform*box.get_center()
    environment(viewport,center,box.size.y)
    for frame in range(8): await process_frame
    await RenderingServer.frame_post_draw
    var image = viewport.get_texture().get_image()
    if image==null or image.is_empty() or image.save_png(base+"character.png")!=OK: return fail("Actual imported material rendering failed")
    var reference: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(base+"morph_reference.json"))
    var preview_index = meshes[0].find_blend_shape_by_name(reference["preview_shape"])
    if preview_index<0: return fail("Missing facial preview shape")
    meshes[0].set_blend_shape_value(preview_index,.5)
    for frame in range(4): await process_frame
    await RenderingServer.frame_post_draw
    image=viewport.get_texture().get_image()
    if image==null or image.is_empty() or image.save_png(base+"face-expression.png")!=OK: return fail("Actual facial shape rendering failed")
    meshes[0].set_blend_shape_value(preview_index,0.)
    if args[0]=="build":
        var preview = Node3D.new();root.add_child(preview)
        var saved: PackedScene = load(base+"character.tscn") as PackedScene
        var character = saved.instantiate();preview.add_child(character);character.owner=preview
        environment(preview,center,box.size.y)
        if not save_scene(preview,base+"character_preview.tscn"): return fail("Could not save the character preview scene")
    var result = {"schema_version":1,"status":"STATIC_GODOT_CHARACTER_VERIFIED_V1","mode":args[0],"request_sha256":args[1],
        "engine":version,"adapter":RenderingServer.get_video_adapter_name(),"rendering_method":RenderingServer.get_current_rendering_method(),
        "observed":observed,"saved_scene_sha256":FileAccess.get_sha256(base+"character.tscn"),
        "preview_scene_sha256":FileAccess.get_sha256(base+"character_preview.tscn"),"saved_scene_reopened_without_repair":args[0]=="verify",
        "visual_quality_approved":false,"distribution_license_review_complete":false}
    var output = FileAccess.open(base+"export_verification.json",FileAccess.WRITE)
    if output==null: return fail("Could not save engine verification evidence")
    output.store_string(JSON.stringify(result,"  ")+"\n");output.close()
    quit(0)
