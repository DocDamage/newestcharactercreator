"""Actual derived-only author import stage. No expected geometry enters observer."""
import sys
sys.dont_write_bytecode = True
import unreal
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from capture_common import identity, apply, capture
control, root, profile = identity('STAGE')
assets = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)
if not not assets.does_asset_exist('/Game/UCC/Character'):
    raise RuntimeError('Unreal fixed recipe or source binding rejected')
if not not assets.does_asset_exist('/Game/UCC/SkinMaterial'):
    raise RuntimeError('Unreal fixed recipe or source binding rejected')
options = unreal.FbxImportUI()
apply(options, profile['fbx_import_ui'])
apply(options.get_editor_property('skeletal_mesh_import_data'), profile['skeletal_mesh_import_data'])
task = unreal.AssetImportTask()
task.set_editor_property('filename', control['source_fbx_path'])
task.set_editor_property('destination_path', '/Game/UCC')
task.set_editor_property('destination_name', 'Character')
task.set_editor_property('automated', True)
task.set_editor_property('replace_existing', False)
task.set_editor_property('save', False)
task.set_editor_property('factory', unreal.FbxFactory())
task.set_editor_property('options', options)
tools = unreal.AssetToolsHelpers.get_asset_tools()
tools.import_asset_tasks([task])
meshes = [obj for obj in task.get_objects() if isinstance(obj, unreal.SkeletalMesh)]
if not len(meshes) == 1:
    raise RuntimeError('Unreal fixed recipe or source binding rejected')
mesh = meshes[0]
if not mesh.get_path_name() == '/Game/UCC/Character.Character':
    raise RuntimeError('Unreal fixed recipe or source binding rejected')
subsystem = unreal.get_editor_subsystem(unreal.SkeletalMeshEditorSubsystem)
settings = subsystem.get_lod_build_settings(mesh, 0)
apply(settings, profile['stage_owned_lod0_build_settings'])
subsystem.set_lod_build_settings(mesh, 0, settings)
nanite = mesh.get_editor_property('nanite_settings')
nanite.set_editor_property('enabled', False)
mesh.set_editor_property('nanite_settings', nanite)
mesh.set_editor_property('positive_bounds_extension', unreal.Vector(0, 0, 0))
mesh.set_editor_property('negative_bounds_extension', unreal.Vector(0, 0, 0))
material = tools.create_asset('SkinMaterial', '/Game/UCC', unreal.Material, unreal.MaterialFactoryNew())
if not material is not None:
    raise RuntimeError('Unreal fixed recipe or source binding rejected')
material.set_editor_property('blend_mode', unreal.BlendMode.BLEND_OPAQUE)
material.set_editor_property('two_sided', False)

def linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
spec = root['material_spec']
color = unreal.MaterialEditingLibrary.create_material_expression(material, unreal.MaterialExpressionVectorParameter, -400, 0)
color.set_editor_property('parameter_name', 'UccBaseColorLinear')
color.set_editor_property('default_value', unreal.LinearColor(*[linear(c) for c in spec['base_color_srgb']], 1))
rough = unreal.MaterialEditingLibrary.create_material_expression(material, unreal.MaterialExpressionScalarParameter, -400, 150)
rough.set_editor_property('parameter_name', 'UccRoughness')
rough.set_editor_property('default_value', spec['roughness'])
metal = unreal.MaterialEditingLibrary.create_material_expression(material, unreal.MaterialExpressionScalarParameter, -400, 300)
metal.set_editor_property('parameter_name', 'UccMetallic')
metal.set_editor_property('default_value', spec['metallic'])
for node, name in ((color, 'MP_BASE_COLOR'), (rough, 'MP_ROUGHNESS'), (metal, 'MP_METALLIC')):
    if not unreal.MaterialEditingLibrary.connect_material_property(node, '', getattr(unreal.MaterialProperty, name)):
        raise RuntimeError('Unreal fixed recipe or source binding rejected')
try:
    unreal.MaterialEditingLibrary.recompile_material(material)
except RuntimeError as error:
    expected = "MaterialEditingLibrary: Cannot compile material '/Game/UCC/SkinMaterial.SkinMaterial': this editor has no renderer, so materials can't be compiled. Run without -nullrhi, or pass -AllowCommandletRendering to a commandlet."
    if str(error) != expected:
        raise
    unreal.log_warning('UCC_PRIVATE_SHADER_COMPILATION_UNAVAILABLE_UNVERIFIED_NULLRHI')
slots = mesh.get_editor_property('materials')
if not len(slots) == 1:
    raise RuntimeError('Unreal fixed recipe or source binding rejected')
slot = slots[0].copy()
slot.set_editor_property('material_interface', material)
slots[0] = slot
mesh.set_editor_property('materials', slots)
if not unreal.EditorLevelLibrary.new_level('/Game/UCC/CharacterScene'):
    raise RuntimeError('Unreal fixed recipe or source binding rejected')
actor = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector(0, 0, 0), unreal.Rotator(0, 0, 0))
component = actor.get_editor_property('skeletal_mesh_component')
component.set_skeletal_mesh_asset(mesh)
actor.set_actor_scale3d(unreal.Vector(1, 1, 1))
for obj in (material, mesh, mesh.get_editor_property('skeleton')):
    if not assets.save_loaded_asset(obj, only_if_is_dirty=False):
        raise RuntimeError('Unreal fixed recipe or source binding rejected')
if not unreal.EditorLevelLibrary.save_current_level():
    raise RuntimeError('Unreal fixed recipe or source binding rejected')
capture('STAGE', control, root, profile, mesh)
