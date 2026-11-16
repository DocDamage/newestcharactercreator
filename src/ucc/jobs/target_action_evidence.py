"""Independent retained target-preview proof graph; no worker or UI execution.

Storage seals the complete inventory and current catalog/source/target authority
before and after this reader. Numerical admission reuses the native validators.
"""
from hashlib import sha256
import json
import math
import os
from pathlib import Path
from typing import Callable

from ucc.animations.fbx_catalog import measured_metadata
from ucc.animations.fbx_snapshot import read_snapshot
from ucc.animations.native_profile import read_native_profile
from ucc.core.errors import ValidationError
from ucc.core.target_action import TargetActionBinding
from ucc.core.target_action_format import SKIN_POLICY, require
from ucc.core.target_action_request import TargetActionRequest
from ucc.preview.motion_cache import MotionCache, read_motion_cache
from .native_evidence import read_native_timeline
from .native_skin_evidence import validate_reopen_report
from .neutral_master import checked_observation
from .private_render_evidence import verify_native_renders
from .protocol import JobRequest, JobResult


def _json(directory: Path, name: str, binding: TargetActionBinding, check: Callable,
          maximum: int = 2 * 1024 * 1024) -> dict:
    check()
    path = directory / name
    record = binding.file_map[name]
    require(record.bytes <= maximum, 'Target preview JSON exceeds its fixed reader bound')
    require(path.resolve() == path and path.is_file() and not path.is_symlink()
            and not any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)()
                        for p in path.parents), 'Target preview proof path is redirected')
    before = path.stat()
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        payload = stream.read(maximum + 1)
        finished = os.fstat(stream.fileno())
    after = path.stat()
    stamp = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    # Windows Python 3.12 path-stat and CRT fd-stat expose different ctime
    # semantics. Preserve exact ctime stability within each API, never fit it.
    require(stamp(before) == stamp(opened) == stamp(finished) == stamp(after)
            and before.st_ctime_ns == after.st_ctime_ns
            and opened.st_ctime_ns == finished.st_ctime_ns
            and len(payload) == record.bytes and sha256(payload).hexdigest() == record.sha256,
            'Target preview proof changed or differs from its sealed binding')
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise ValueError('Duplicate target proof field')
            result[key] = value
        return result
    def nonfinite(_):
        raise ValueError('Nonfinite target proof value')
    def finite_float(text):
        value = float(text)
        if not math.isfinite(value):
            raise ValueError('Overflowed target proof number')
        return value
    try:
        value = json.loads(payload, object_pairs_hook=pairs, parse_constant=nonfinite,
                           parse_float=finite_float)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ValidationError('Malformed target preview proof JSON') from error
    require(type(value) is dict, 'Target preview proof must be an object')
    check()
    return value


def _request_binding(request: TargetActionRequest, binding: TargetActionBinding) -> None:
    require(request.sha256 == binding.preparation_request_sha256
            and request.source == binding.source
            and request.project_id == binding.target.project_id
            and request.revision == binding.target.revision
            and request.project_sha256 == binding.target.project_sha256
            and request.master_sha256 == binding.target.master_sha256
            and request.mapping_sha256 == binding.mapping_sha256
            and request.root_motion_policy == binding.root_motion_policy
            and request.blender_executable_sha256 == binding.producer.blender_executable_sha256
            and request.worker_resources_sha256 == binding.producer.worker_resources_sha256,
            'Target preview preparation request and immutable lineage disagree')


def _worker(directory: Path, prefix: str, job_id: str, operation: str,
            options: dict, binding: TargetActionBinding, check: Callable,
            *, input_project: str | None = 'candidate.blend', neutral: str | None = None) -> dict:
    request_name = prefix + ('_request.json' if neutral else '/request.json')
    result_name = prefix + ('_result.json' if neutral else '/result.json')
    request = JobRequest.from_dict(_json(directory, request_name, binding, check))
    result = JobResult.from_dict(_json(directory, result_name, binding, check))
    expected = JobRequest(job_id, operation, input_project, options)
    # Dict equality alone equates bool/int; preserve actual finite JSON types.
    encode = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    require(encode(request.as_dict()) == encode(expected.as_dict())
            and result.job_id == job_id and result.operation == operation
            and type(result.protocol_version) is int and result.status == 'ok'
            and result.error is None, 'Retained target worker identity, operation or options differ')
    return result.details


def _neutral(directory: Path, binding: TargetActionBinding, check: Callable) -> dict:
    rows = []
    for label, job_id in zip(('first', 'second'), binding.producer.neutral_worker_job_ids):
        details = _worker(directory, 'neutral/' + label, job_id, 'inspect_mpfb_neutral_master',
                          {'master_sha256': binding.target.master_sha256}, binding, check, neutral=label)
        # Current-project context separately requires 12 keys iff expression
        # preparation is present; this reader checks the retained supported pair.
        count = details.get('expression_key_count')
        require(type(count) is int and count in (0, 12), 'Unsupported neutral target expression domain')
        rows.append(checked_observation(details, binding.target.master_sha256, count))
    require(rows[0] == rows[1] and rows[0]['state_sha256'] == binding.target.neutral_state_sha256
            and rows[0]['rest_sha256'] == binding.target.rest_sha256,
            'Neutral worker pair differs from the bound target state/rest')
    return rows[0]


def _validate_retained(directory: Path, binding: TargetActionBinding, *,
                       cancel_check: Callable[[], None]) -> MotionCache:
    """Validate nine actual worker proofs and return sealed immutable cache bytes.

    This does not resolve current catalog policy or authorize editing/export.
    The storage wrapper must guard those authorities and all file identities.
    """
    require(type(binding) is TargetActionBinding and callable(cancel_check),
            'Target preview needs typed lineage and a bounded cancellation guard')
    directory = Path(directory)
    require(directory.is_absolute() and directory.resolve() == directory and directory.is_dir(),
            'Retained target preview directory is not canonical')
    check = cancel_check
    raw = _json(directory, 'preparation_request.json', binding, check, 256 * 1024)
    request = TargetActionRequest.from_dict(raw)
    _request_binding(request, binding)
    neutral = _neutral(directory, binding, check)
    intake = []
    for label, job_id in zip(('first', 'second'), binding.producer.source_intake_worker_job_ids):
        intake.append(_worker(directory, 'source_intake_' + label, job_id, 'inspect_fbx_animation',
                              {'source_sha256': binding.source.source_sha256}, binding, check,
                              input_project=None))
    require(intake[0] == intake[1], 'Independent retained source intake workers disagree')
    source, _ = read_snapshot(directory, intake[0], binding.source.source_sha256, cancel_check=check)
    # Both original reports must independently name this one sealed snapshot.
    read_snapshot(directory, intake[1], binding.source.source_sha256, cancel_check=check)
    require(intake[0]['snapshot']['sha256'] == binding.source.snapshot_sha256
            == binding.file_map['source_snapshot.json'].sha256,
            'Target preview source snapshot is not the registered measured source')
    require((source['first_frame'], source['last_frame'], source['fps'], len(source['frames']))
            == (2, 301, 30, 300), 'Registered target preview requires exact source clock 2–301 at 30 FPS')
    metadata = measured_metadata(source, binding.source.source_sha256, cancel_check=check)
    require(metadata.skeleton_fingerprint == binding.source.skeleton_fingerprint,
            'Retained source rest skeleton differs from the registered catalog fingerprint')
    profile, mapping_sha = read_native_profile(directory/'native_mapping.json',
        binding.source.source_sha256, binding.source.snapshot_sha256, binding.target.master_sha256)
    require(mapping_sha == binding.mapping_sha256
            and profile.get('skin_deformation_policy') == SKIN_POLICY
            and profile.get('root_motion_policy', 'ARMATURE_ORIGIN_DISPLACEMENT_V1') == binding.root_motion_policy,
            'Target preview mapping or explicit root/skin policy differs')
    bindings = {'source_sha256': binding.source.source_sha256, 'snapshot_sha256': binding.source.snapshot_sha256,
                'mapping_sha256': binding.mapping_sha256, 'master_sha256': binding.target.master_sha256}
    data_rows = []; reports = []
    for label, job_id in zip(('first', 'second'), binding.producer.body_worker_job_ids):
        check()
        report = _worker(directory, 'body_' + label, job_id, 'verify_native_fbx_body',
                         {**bindings, 'render_private_frames': label == 'first'}, binding, check)
        data, _ = read_native_timeline(directory/('body_' + label), report, source, profile,
                                       bindings, cancel_check=check)
        require(data.get('skin_deformation_policy') == SKIN_POLICY
                and data.get('root_motion_policy', 'ARMATURE_ORIGIN_DISPLACEMENT_V1') == binding.root_motion_policy,
                'Retained target timeline uses a different body/root profile')
        require(data['source_first_frame'] == 2 and data['source_frame_count'] == 300 and data['fps'] == 30
                and all(row['evaluated_vertex_count'] == neutral['visible_vertex_count']
                        for row in data['full_timeline_frames']), 'Retained target body coverage differs')
        data_rows.append(data); reports.append(report)
    require({k: v for k, v in data_rows[0].items() if k != 'visual_review_blend'}
            == {k: v for k, v in data_rows[1].items() if k != 'visual_review_blend'},
            'Independent target workers disagree on complete target poses/skin/root')
    require(reports[0].get('private_review_renders') is not None
            and reports[1].get('private_review_renders') is None,
            'Retained private render evidence is missing or was unrequested')
    verify_native_renders(directory/'body_first', reports[0], data_rows[0])
    first = reports[0]; timeline = data_rows[0]
    options = {**bindings, 'review_sha256': first['visual_review_blend']['sha256'],
               'timeline_sha256': first['timeline']['sha256']}
    require(options['review_sha256'] == binding.file_map['body_first/review_motion.blend'].sha256
            and options['timeline_sha256'] == binding.file_map['body_first/target_timeline.json'].sha256,
            'Saved target Action/timeline differs from the immutable lineage')
    reopened = _worker(directory, 'body_reopen', binding.producer.body_reopen_job_id,
                       'reopen_native_fbx_body', options, binding, check)
    validate_reopen_report(reopened, options, timeline)
    playback = _worker(directory, 'playback', binding.producer.cache_job_id,
                       'cache_native_fbx_body', options, binding, check)
    manifest = _json(directory, 'playback/motion_skin.json', binding, check, 4 * 1024 * 1024)
    require(manifest.get('schema_version') == 2 and type(manifest.get('schema_version')) is int
            and 'surface_review' in playback, 'Target preview requires the full V2 surface-bound cache')
    contact_sha = binding.file_map['playback/motion_contacts.json'].sha256
    require(playback['surface_review'].get('sha256') == contact_sha,
            'Retained cache surface evidence differs from its sealed proof')
    surface = _worker(directory, 'surface_verify', binding.producer.surface_verification_job_id,
                      'verify_native_surface_review', {**options, 'surface_review_sha256': contact_sha}, binding, check)
    cache = read_motion_cache(directory/'playback', playback, options, timeline, cancel_check=check,
                              profile=profile, surface_verification=surface)
    require((cache.frame_count, cache.fps, cache.source_first_frame, cache.vertex_count)
            == (300, 30, 2, neutral['visible_vertex_count']) and cache.surface_review is not None,
            'Retained target cache differs from complete measured target playback')
    check()
    return cache


def validate_retained_target_action(directory: Path, binding: TargetActionBinding, *,
                                   cancel_check: Callable[[], None]) -> MotionCache:
    """Read sealed retained proofs; storage guards current authority externally."""
    try:
        return _validate_retained(directory, binding, cancel_check=cancel_check)
    except (KeyError, TypeError, IndexError, AttributeError, ValueError, RecursionError) as error:
        raise ValidationError('Malformed retained target preview proof graph') from error
