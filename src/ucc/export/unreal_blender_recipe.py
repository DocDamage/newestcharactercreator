"""Closed Blender source operations for the admitted static Unreal profile."""
from ucc.core.errors import ValidationError
from ucc.core.expressions import is_sha256
from ucc.core.skin_material import SkinMaterialSpec
from .unreal_contract import UnrealExportRequest
from .godot_candidate_contract import canonical_bytes

POLICY = 'UCC_UNREAL_BLENDER_SOURCE_V1'
STAGE = 'stage_mpfb_unreal_source'
VERIFY = 'verify_mpfb_unreal_source'
NORMAL_BYTES = 26756 * 3 * 3 * 4
FILES = {'character.fbx': 512 * 1024 * 1024, 'source_reference.json': 64 * 1024 * 1024,
    'source_corner_normals.bin': NORMAL_BYTES, 'source_corner_normals.json': 128 * 1024,
    'unreal_source_stage.json': 128 * 1024}
VERIFICATION_FILE = 'unreal_source_verification.json'
EXPORT_OPTIONS = {'check_existing': False, 'use_selection': True,
    'object_types': ['ARMATURE', 'MESH'], 'apply_unit_scale': True,
    'apply_scale_options': 'FBX_SCALE_UNITS', 'global_scale': 1.,
    'axis_forward': '-X', 'axis_up': 'Z', 'use_space_transform': True,
    'bake_space_transform': False, 'add_leaf_bones': False,
    'use_armature_deform_only': False, 'armature_nodetype': 'NULL',
    'primary_bone_axis': 'Y', 'secondary_bone_axis': 'X', 'bake_anim': False,
    'mesh_smooth_type': 'FACE', 'use_mesh_modifiers': False, 'use_tspace': False,
    'use_custom_props': False, 'path_mode': 'AUTO', 'embed_textures': False}


def recipe(request: UnrealExportRequest, spec: SkinMaterialSpec) -> dict:
    if type(request) is not UnrealExportRequest or type(spec) is not SkinMaterialSpec:
        raise ValidationError('Unreal source recipe needs reviewed source and material contracts')
    # SkinMaterialSpec itself closes this profile to opaque, nonmetallic,
    # texture-free first-party parameters.
    return {'schema_version': 1, 'policy': POLICY,
            'export_request': request.to_dict(), 'material_spec': spec.to_dict()}


def validate_recipe(raw: dict) -> tuple[UnrealExportRequest, SkinMaterialSpec]:
    if type(raw) is not dict or set(raw) != {'schema_version', 'policy', 'export_request', 'material_spec'}:
        raise ValidationError('Malformed Unreal source recipe')
    request = UnrealExportRequest.from_dict(raw['export_request'])
    spec = SkinMaterialSpec.from_dict(raw['material_spec'])
    if canonical_bytes(raw) != canonical_bytes(recipe(request, spec)):
        raise ValidationError('Unreal source recipe changed its version, capabilities or material')
    return request, spec


def validate_job(operation: str, input_project: str, options: dict) -> None:
    fields = {'master_sha256', 'recipe_sha256'}
    if operation == VERIFY:
        fields |= {name.replace('.', '_') + '_sha256' for name in FILES}
    if (operation not in {STAGE, VERIFY} or input_project != 'candidate.blend'
            or type(options) is not dict or set(options) != fields
            or any(not is_sha256(value) for value in options.values())):
        raise ValidationError('Unreal source job needs fixed staged filenames and complete SHA bindings')
