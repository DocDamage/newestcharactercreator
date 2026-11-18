"""Closed Blender worker envelope for one registered Unreal animation."""

from ucc.core.errors import ValidationError
from ucc.core.expressions import is_sha256
from .unity_animation_recipe import (
    BONES, CORRECTION_INPUTS, FPS, INPUT_FILES, SOURCE_FRAMES, VERTICES, VIRTUAL_FRAME,
    output_option, validate_binding,
)
from .unreal_contract import PROFILE


POLICY = 'UCC_REGISTERED_UNREAL_ANIMATION_SOURCE_V1'
STAGE = 'stage_registered_unreal_animation_source'
VERIFY = 'verify_registered_unreal_animation_source'
OPERATIONS = frozenset({STAGE, VERIFY})
REFERENCES = {
    'unreal_animated_raw_positions.f32': SOURCE_FRAMES * VERTICES * 3 * 4,
    'unreal_animated_corrected_positions.f32': SOURCE_FRAMES * VERTICES * 3 * 4,
    'unreal_animated_corrected_normals.f32': SOURCE_FRAMES * VERTICES * 3 * 4,
    'unreal_animated_world_bones.f32': SOURCE_FRAMES * BONES * 16 * 4,
}
FBX = 'animated_character.fbx'
BIND = 'unreal_animated_bind.json'
STAGE_REPORT = 'unreal_animated_source_stage.json'
VERIFY_REPORT = 'unreal_animated_source_verification.json'
FBX_SNAPSHOT = 'unreal_animated_fbx_readback.json'
OUTPUT_LIMITS = {
    FBX: 256 * 1024**2, BIND: 64 * 1024**2, STAGE_REPORT: 64 * 1024,
    **REFERENCES, **CORRECTION_INPUTS,
}


def source_report(options: dict, files: dict, *, fbx_readback_sha256: str | None = None) -> dict:
    reopened = fbx_readback_sha256 is not None
    report = {
        'schema_version': 1, 'policy': POLICY, 'fbx_profile': PROFILE,
        'target_binding_sha256': options['target_binding_sha256'],
        'master_sha256': options['master_sha256'], 'files': files,
        'source_samples': SOURCE_FRAMES, 'fps': FPS, 'virtual_endpoint': VIRTUAL_FRAME,
        'duration_seconds': SOURCE_FRAMES // FPS,
        'recomputed_source_references': reopened, 'blender_fbx_reimport_verified': reopened,
        'engine_import_verified': False, 'unreal_playback_verified': False,
        'corrective_runtime_verified': False,
    }
    if reopened:
        report['fbx_readback_sha256'] = fbx_readback_sha256
    return report


def validate_job(operation: str, input_project: str, options: dict) -> None:
    fields = {*INPUT_FILES.values(), 'source_sha256'}
    if operation == VERIFY:
        fields.update(output_option(name) for name in OUTPUT_LIMITS)
    if (type(operation) is not str or operation not in OPERATIONS or input_project != 'candidate.blend'
            or type(options) is not dict or set(options) != fields
            or any(not is_sha256(value) for value in options.values())):
        raise ValidationError('Registered Unreal source requires fixed staged filenames and exact SHA bindings')


def validate_result(operation: str, details: dict) -> None:
    fields = {'policy', 'files', 'engine_import_verified'}
    if operation == VERIFY:
        fields.update(('verification_sha256', 'fbx_readback_sha256'))
    if (operation not in OPERATIONS or type(details) is not dict or set(details) != fields
            or details['policy'] != POLICY or details['engine_import_verified'] is not False
            or type(details['files']) is not dict or set(details['files']) != set(OUTPUT_LIMITS)
            or any(not is_sha256(value) for value in details['files'].values())
            or any(not is_sha256(details[key]) for key in fields if key.endswith('_sha256'))):
        raise ValidationError('Registered Unreal worker result changed its output closure or approval scope')
