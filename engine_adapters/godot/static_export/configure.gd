extends SceneTree
## Only an isolated fresh import; no user-project import settings are touched.
func _initialize():
    var base = get_script().resource_path.get_base_dir() + "/"
    var config = ConfigFile.new()
    if config.load(base + "character.glb.import") != OK: return quit(2)
    config.set_value("params", "meshes/force_disable_compression", true)
    if config.save(base + "character.glb.import") != OK: return quit(2)
    quit(0)
