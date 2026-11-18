"""Closed Blender-only worker envelope for one registered Unity animation."""

from ucc.core.errors import ValidationError
from ucc.core.expressions import is_sha256
from ucc.core.target_action import TargetActionBinding


POLICY = 'UCC_REGISTERED_UNITY_ANIMATION_SOURCE_V1'
STAGE = 'stage_registered_unity_animation_source'
VERIFY = 'verify_registered_unity_animation_source'
OPERATIONS = frozenset({STAGE, VERIFY})
SOURCE_FRAMES = 300
FPS = 30
VIRTUAL_FRAME = SOURCE_FRAMES + 1
VERTICES = 13380
BONES = 163
INPUT_FILES = {
    'candidate.blend': 'master_sha256',
    'review_motion.blend': 'review_sha256',
    'target_timeline.json': 'timeline_sha256',
    'source_snapshot.json': 'snapshot_sha256',
    'native_mapping.json': 'mapping_sha256',
    'target_binding.json': 'target_binding_sha256',
}
REFERENCES = {
    'unity_animated_raw_positions.f32': SOURCE_FRAMES * VERTICES * 3 * 4,
    'unity_animated_corrected_positions.f32': SOURCE_FRAMES * VERTICES * 3 * 4,
    'unity_animated_corrected_normals.f32': SOURCE_FRAMES * VERTICES * 3 * 4,
    'unity_animated_world_bones.f32': SOURCE_FRAMES * BONES * 16 * 4,
}
FBX = 'animated_character.fbx'
BIND = 'unity_animated_bind.json'
WEIGHTS = 'source_weights.json'
STAGE_REPORT = 'unity_animated_source_stage.json'
VERIFY_REPORT = 'unity_animated_source_verification.json'
FBX_SNAPSHOT = 'unity_animated_fbx_readback.json'
OUTPUT_LIMITS = {FBX: 256 * 1024**2, BIND: 64 * 1024**2, WEIGHTS: 8 * 1024**2,
                 STAGE_REPORT: 64 * 1024, **REFERENCES}


def output_option(name: str) -> str:
    return name.replace('.', '_') + '_sha256'


def source_report(options: dict, files: dict, *, fbx_readback_sha256: str | None = None) -> dict:
    reopened = fbx_readback_sha256 is not None
    report = {
        'schema_version': 1,
        'policy': POLICY,
        'target_binding_sha256': options['target_binding_sha256'],
        'master_sha256': options['master_sha256'],
        'files': files,
        'source_samples': SOURCE_FRAMES,
        'fps': FPS,
        'virtual_endpoint': VIRTUAL_FRAME,
        'duration_seconds': SOURCE_FRAMES // FPS,
        'recomputed_source_references': reopened,
        'blender_fbx_reimport_verified': reopened,
        'engine_import_verified': False,
        'unity_playback_verified': False,
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
        raise ValidationError('Registered Unity source requires fixed staged filenames and exact SHA bindings')


def validate_binding(binding: TargetActionBinding, options: dict) -> None:
    if type(binding) is not TargetActionBinding:
        raise ValidationError('Registered Unity source requires a typed target binding')
    files = binding.file_map
    expected = {
        'target_binding_sha256': binding.sha256,
        'source_sha256': binding.source.source_sha256,
        'master_sha256': binding.target.master_sha256,
        'snapshot_sha256': binding.source.snapshot_sha256,
        'mapping_sha256': binding.mapping_sha256,
        'review_sha256': files['body_first/review_motion.blend'].sha256,
        'timeline_sha256': files['body_first/target_timeline.json'].sha256,
    }
    if any(options.get(key) != value for key, value in expected.items()):
        raise ValidationError('Unity animation input differs from the registered target Action binding')


def validate_result(operation: str, details: dict) -> None:
    fields = {'policy', 'files', 'engine_import_verified'}
    if operation == VERIFY:
        fields.update(('verification_sha256', 'fbx_readback_sha256'))
    if (set(details) != fields or details['policy'] != POLICY or details['engine_import_verified'] is not False
            or type(details['files']) is not dict or set(details['files']) != set(OUTPUT_LIMITS)
            or any(not is_sha256(value) for value in details['files'].values())
            or any(not is_sha256(details[key]) for key in fields if key.endswith('_sha256'))):
        raise ValidationError('Registered Unity worker result changed its output closure or approval scope')
