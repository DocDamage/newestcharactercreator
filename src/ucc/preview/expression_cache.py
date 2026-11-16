"""Strict facial cache contract using the shared immutable GPU buffer type."""
from hashlib import sha256
import json
import math
from pathlib import Path

from ucc.core.errors import ValidationError
from ucc.core.expression_clip import CLIP_POLICY
from ucc.core.expression_library import canonical_digest
from ucc.core.expressions import is_sha256
from ucc.jobs.native_evidence import bound_file
from .motion_cache import MotionCache, decode_skin_buffers, _pairs

MAX_BYTES = 16*1024*1024


def read_json(path: Path, expected: str, limit: int) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValidationError('Expression evidence is missing, redirected or oversized')
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected:
        raise ValidationError('Expression evidence changed while reading')
    try:
        return json.loads(data, object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValidationError('Nonfinite expression evidence')))
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ValidationError('Invalid expression evidence JSON') from error


def validate_clip_report(report: object, bindings: dict) -> dict:
    fields = {'schema_version', 'policy', 'master_sha256', 'clip_sha256', 'motion_sha256',
              'neutral_state_sha256', 'world_matrix', 'hip_world', 'frame_count', 'fps', 'keyframes',
              'frames', 'exact_neutral_endpoints', 'visual_quality_approved', 'engine_import_verified'}
    if (type(report) is not dict or set(report) != fields or type(report['schema_version']) is not int
            or report['schema_version'] != 1 or report['policy'] != CLIP_POLICY
            or any(report[k] != bindings[k] for k in ('master_sha256', 'clip_sha256', 'motion_sha256'))
            or type(report['frame_count']) is not int or report['frame_count'] != 25
            or type(report['fps']) is not int or report['fps'] != 24 or type(report['keyframes']) is not list
            or any(type(v) is not int for v in report['keyframes']) or report['keyframes'] != [1, 13, 25]
            or not is_sha256(report['neutral_state_sha256']) or report['exact_neutral_endpoints'] is not True
            or report['visual_quality_approved'] is not False or report['engine_import_verified'] is not False
            or type(report['frames']) is not list or len(report['frames']) != 25):
        raise ValidationError('Expression report lacks complete source-bound 25-frame evidence')
    hash_fields = {'full_sha256', 'visible_sha256', 'fixed_state_sha256', 'local_vertices_sha256',
                   'triangles_sha256', 'skin_sha256', 'raw_sha256'}
    for frame, row in enumerate(report['frames'], 1):
        if (type(row) is not dict or set(row) != hash_fields|{'frame', 'maximum_displacement', 'moved_vertices_over_1um'}
                or type(row['frame']) is not int or row['frame'] != frame
                or not all(is_sha256(row[k]) for k in hash_fields)
                or type(row['maximum_displacement']) not in (int, float)
                or not 0 <= row['maximum_displacement'] <= .03 or not math.isfinite(row['maximum_displacement'])
                or type(row['moved_vertices_over_1um']) is not int or not 0 <= row['moved_vertices_over_1um'] <= 19158):
            raise ValidationError('Expression frame hashes, order or deformation bounds differ')
        if row['fixed_state_sha256'] != report['frames'][0]['fixed_state_sha256']:
            raise ValidationError('Expression frame changed original character state')
        # Blender may choose different diagonals for deformed quads. The
        # polygon topology is bound by fixed_state_sha256; each frame's actual
        # triangulation is separately bound to its independent surface below.
    first, last = report['frames'][0], report['frames'][-1]
    neutral_hashes = {'full_sha256', 'visible_sha256', 'fixed_state_sha256', 'local_vertices_sha256', 'skin_sha256'}
    if any(first[k] != last[k] for k in neutral_hashes) or any(r['maximum_displacement'] != 0
            or r['moved_vertices_over_1um'] != 0 for r in (first, last)):
        raise ValidationError('Expression endpoints are not exact neutral restorations')
    return report


def read_expression_cache(folder: Path, bindings: dict, proof: dict, report: dict,
                            *, cancel_check=lambda: None) -> MotionCache:
    expected = {'schema_version': 1, 'policy': CLIP_POLICY, 'bindings': bindings, 'verified_reopen': True,
                'reference_frames': 25, 'saved_frames': 25, 'cache_frames': 25, 'exact_neutral_endpoints': True,
                'visual_quality_approved': False, 'engine_import_verified': False}
    if canonical_digest(proof) != canonical_digest(expected):
        raise ValidationError('Expression cache lacks independent saved/reference/cache verification')
    validate_clip_report(report, bindings)
    manifest = read_json(folder/'expression_skin.json', bindings['cache_manifest_sha256'], 4*1024*1024)
    fields = {'schema_version', 'status', 'bindings', 'coordinate_space', 'world_matrix', 'fps', 'source_first_frame',
              'frame_count', 'vertex_count', 'triangle_count', 'frames', 'geometry',
              'animation_visual_quality_verified', 'engine_import_verified'}
    expected_bindings = {k: bindings[k] for k in ('master_sha256', 'clip_sha256', 'motion_sha256', 'motion_report_sha256')}
    if (type(manifest) is not dict or set(manifest) != fields or type(manifest['schema_version']) is not int
            or manifest['schema_version'] != 1 or manifest['status'] != 'VERIFIED_EXPRESSION_SKIN_CACHE_V1'
            or manifest['bindings'] != expected_bindings or manifest['coordinate_space'] != 'BLENDER_LOCAL_Z_UP'
            or manifest['world_matrix'] != report['world_matrix']
            or any(type(manifest[k]) is not int or manifest[k] != v for k, v in
                   (('fps', 24), ('source_first_frame', 1), ('frame_count', 25), ('vertex_count', 13380), ('triangle_count', 26756)))
            or manifest['animation_visual_quality_verified'] is not False or manifest['engine_import_verified'] is not False):
        raise ValidationError('Expression cache schema, bindings, full geometry or quality declarations differ')
    binary = bound_file(folder, manifest['geometry'], 'expression_skin.bin', MAX_BYTES, cancel_check=cancel_check)
    if manifest['geometry']['sha256'] != bindings['cache_sha256']:
        raise ValidationError('Expression cache binary differs from the independently verified file')
    cache = decode_skin_buffers(folder, manifest, skin_hashes=[r['skin_sha256'] for r in report['frames']],
        hip_positions=[report['hip_world']]*25, triangle_hashes=[r['triangles_sha256'] for r in report['frames']],
        geometry_name='expression_skin.bin', cancel_check=cancel_check)
    for index, row in enumerate(report['frames']):
        cancel_check(); vertices, triangles = cache.frame(index)
        if (sha256(vertices).hexdigest() != row['local_vertices_sha256']
                or sha256(vertices+triangles).hexdigest() != row['raw_sha256']):
            raise ValidationError('Expression buffers differ from the exact independent saved surface')
    return cache
