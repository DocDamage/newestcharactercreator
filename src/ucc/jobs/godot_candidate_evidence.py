"""Independently inspect completed candidate reports and all private images."""
import math
from pathlib import Path
from threading import Event

from ucc.core.errors import ValidationError
from ucc.export.godot_candidate_contract import GodotCandidateRequest
from .godot_candidate_inputs import read_json, regular_file, check_cancel
from .master_preview import _digest
from .private_render_evidence import png_measurements


def configuration(folder: Path, request: GodotCandidateRequest, cancel: Event | None,
                  *, after_reimport: bool = False) -> dict:
    raw = read_json(folder/'configuration.json', 256*1024)
    if (raw.get('status') != 'GODOT_CANDIDATE_IMPORT_CONFIGURED_V1'
            or raw.get('job_id') != request.job_id or raw.get('request_sha256') != request.sha256
            or raw.get('import_profile') != request.to_dict()['import_profile']
            or raw.get('engine_import_verified') is not False):
        raise ValidationError('Godot did not configure the exact bound animation import profile')
    for filename, field in [('character.glb.import', 'import_options_sha256'),
                            ('original_import_options.cfg', 'original_options_sha256')]:
        path = regular_file(folder/filename, folder, 4*1024*1024)
        if filename == 'character.glb.import' and after_reimport:
            # The editor normalizes ConfigFile serialization during reimport.
            # Final semantic settings and their new exact hash are independently
            # checked by the actual verifier and bound below before publication.
            continue
        if _digest(path, cancel) != raw.get(field):
            raise ValidationError('Godot import configuration evidence changed')
    return raw


def verification(folder: Path, request: GodotCandidateRequest, cancel: Event | None) -> dict:
    raw = read_json(folder/'verification.json', 4*1024*1024)
    if (raw.get('verified_import_profile') != request.to_dict()['import_profile']
            or _digest(regular_file(folder/'character.glb.import', folder, 4*1024*1024), cancel)
            != raw.get('import_options_sha256')):
        raise ValidationError('Final Godot import settings changed after actual verification')
    if (raw.get('status') != 'GODOT_CANDIDATE_DEFORMATION_AND_RENDER_VERIFIED_V1'
            or raw.get('job_id') != request.job_id or raw.get('request_sha256') != request.sha256
            or raw.get('project_id') != request.project_id or type(raw.get('revision')) is not int
            or raw['revision'] != request.revision or raw.get('master_sha256') != request.master_sha256
            or raw.get('engine_import_verified') is not False or raw.get('visual_quality_approved') is not False
            or raw.get('vertex_shader_positions_directly_verified') is not False
            or raw.get('material_appearance_verified') is not False
            or raw.get('imported_diagnostic_skeletal_channels_verified') is not True
            or raw.get('rendered_combined_samples_verified') is not True
            or raw.get('engine_baked_combined_deformation_verified') is not True):
        raise ValidationError('Godot candidate has no complete bound deformation/render evidence')
    version = raw.get('godot_version', {})
    if type(version) is not dict or version.get('major') != 4 or version.get('minor') != 7:
        raise ValidationError('Candidate was checked in another unsupported Godot version')
    if (raw.get('source_vertices') != 13380 or raw.get('bones') != 163 or raw.get('morphs') != 12
            or type(raw.get('skeletal_rotation_tracks')) is not int or raw['skeletal_rotation_tracks'] < 5
            or not isinstance(raw.get('rendering_device'), str) or not raw['rendering_device'].strip()):
        raise ValidationError('Actual candidate rig, morphs, motion or graphics backend are incomplete')
    adapter = raw.get('skin_adapter')
    if (type(adapter) is not dict or adapter.get('status') != 'GODOT_SKIN_PLAN_APPLIED'
            or adapter.get('candidate_sha256') != dict(request.files)['character.glb']
            or adapter.get('plan_sha256') != dict(request.files)['skin_plan.json']
            or adapter.get('all_positive_influences_retained') is not True
            or adapter.get('exact_integer_codes_rechecked') is not True
            or adapter.get('diagnostic_UV_required') is not False
            or adapter.get('original_resource_preserved') is not True):
        raise ValidationError('Candidate lacks exact independent skin-code verification')
    frames = raw.get('frames')
    if type(frames) is not list or len(frames) != request.frame_count:
        raise ValidationError('Candidate is missing complete timeline samples')
    maximum = 0.
    png_hashes = set(); pixel_hashes = set()
    for index, frame in enumerate(frames):
        check_cancel(cancel)
        if type(frame) is not dict or type(frame.get('frame')) is not int or frame['frame'] != index:
            raise ValidationError('Candidate has duplicated or missing frame evidence')
        error = frame.get('max_world_error_m')
        if type(error) not in (float, int) or not math.isfinite(error) or not 0 <= error <= 1e-5:
            raise ValidationError('Candidate exceeds the unchanged full-surface deformation limit')
        maximum = max(maximum, error)
        image = regular_file(folder/f'combined_{index:02d}.png', folder, 2*1024*1024)
        digest = _digest(image, cancel)
        if digest != frame.get('png_sha256'):
            raise ValidationError('Actual private rendered candidate image changed')
        decoded = png_measurements(image.read_bytes(), include_pixel_hash=True)
        pixel = frame.get('rgba_sha256')
        if type(pixel) is not str or len(pixel) != 64 or any(c not in '0123456789abcdef' for c in pixel):
            raise ValidationError('Candidate has no bound rendered pixel evidence')
        if pixel != decoded['rgba_sha256']:
            raise ValidationError('Candidate rendered pixel hash differs from independently decoded PNG bytes')
        png_hashes.add(digest); pixel_hashes.add(pixel)
    if len(png_hashes) < 2 or len(pixel_hashes) < 2:
        raise ValidationError('Candidate rendered motion did not change')
    if type(raw.get('max_combined_world_error_m')) not in (int, float) or raw['max_combined_world_error_m'] != maximum:
        raise ValidationError('Candidate aggregate error differs from complete frame observations')
    if type(raw.get('distinct_rendered_frames')) is not int or raw['distinct_rendered_frames'] != len(pixel_hashes):
        raise ValidationError('Candidate aggregate image count differs from actual frames')
    return raw
