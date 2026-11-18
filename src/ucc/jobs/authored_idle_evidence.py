"""Closed idle phase evidence; private geometry is never included in errors."""
from hashlib import sha256
import json
import math
import re

from ucc.animations.fbx_snapshot import validate_snapshot
from ucc.core.authored_idle import AuthoredIdleInspectionRequest
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.storage import _nonfinite_project_number
from ucc.core.target_action import TargetActionTarget
from ucc.core.target_action_format import checked_sha, checked_text, closed, document_sha256
from .godot_candidate_inputs import identity
from .target_action_context import protected
from .master_preview import _digest
from .authored_idle_io import private_bytes as canonical_bytes, private_sha

INSPECT = 'inspect_authored_idle_target'
AUTHOR = 'author_original_idle_source'
VERIFY = 'verify_authored_idle_source'
PROFILE = 'UCC_ORIGINAL_MPFB_IDLE_SOURCE_V1'
FRAME_PROFILE = 'UCC_MEASURED_MPFB_IDLE_ANATOMY_V1'
QUALITY = {'human_visual_review_approved': False, 'loop_quality_approved': False,
    'usable_action_approved': False, 'engine_import_verified': False, 'sprite_use_authorized': False,
    'source_redistribution_authorized': False, 'quality_measurements_verified': False,
    'source_authorship_proven': False}
OUTPUTS = {INSPECT: ('idle_anatomical_frame.json', 'idle_inspection_report.json'),
    AUTHOR: ('original_idle.fbx', 'authored_idle_review.blend', 'authored_idle_recipe.json', 'authored_idle_report.json'),
    VERIFY: ('authored_idle_source_snapshot.json', 'authored_idle_verification.json')}
STATUS = {INSPECT: 'ACTUAL_NEUTRAL_IDLE_ANATOMY_MEASURED',
    AUTHOR: 'ORIGINAL_IDLE_SOURCE_AUTHORED_PENDING_INDEPENDENT_REOPEN',
    VERIFY: 'ORIGINAL_IDLE_FRESH_REOPEN_FULL300_VERIFIED_NOT_USABLE_APPROVED'}
LIMITS = {'original_idle.fbx': 512*1024*1024, 'authored_idle_review.blend': 512*1024*1024,
          'original_walk.fbx': 512*1024*1024, 'original_walk.blend': 512*1024*1024,
          'authored_walk_source_snapshot.json': 64*1024*1024,
          'authored_idle_source_snapshot.json': 64*1024*1024, 'candidate.blend': 2*1024*1024*1024}
QUALITY_EXECUTION = {key: True for key in ('root_neutral_measured', 'lower_chain_neutral_measured',
    'neutral_sole_drift_measured', 'full300_finite_zero_translation_unit_scale',
    'analytic_seam_value_measured', 'analytic_seam_first_derivative_measured',
    'wrapped_same_interval_velocities_measured')}
QUALITY_EXECUTION.update({key: False for key in ('palmar_skin_surface_normal_verified',
    'hand_digit_body_clearance_measured', 'human_visual_review_performed', 'complete_required_quality_verified')})


def need(value, message):
    if not value:
        raise ValidationError(message)


def record(path, budget, maximum=None):
    budget.check(); protected(path)
    maximum = maximum or LIMITS.get(path.name, 16*1024*1024)
    need(path.is_file() and path.stat().st_nlink == 1 and 0 < path.stat().st_size <= maximum,
         'Idle evidence is missing, shared or exceeds its file limit')
    before = identity(path); digest = sha256(); size = 0
    with path.open('rb') as stream:
        while True:
            budget.check(); block = stream.read(min(1024*1024, maximum-size+1))
            if not block: break
            size += len(block)
            need(size <= maximum, 'Idle evidence grew beyond its finite file limit')
            digest.update(block)
    need(identity(protected(path)) == before and path.stat().st_nlink == 1 and size == before[2],
         'Idle evidence changed during hashing')
    return {'name': path.name, 'bytes': before[2], 'sha256': digest.hexdigest()}


def read_idle_json(path, budget, expected=None, *, canonical=True, maximum=16*1024*1024):
    row = record(path, budget, maximum)
    with path.open('rb') as stream:
        payload = stream.read(maximum+1)
    need(len(payload) <= maximum and sha256(payload).hexdigest() == row['sha256']
         and (expected is None or row['sha256'] == expected), 'Idle JSON bytes changed or differ from their bound digest')
    try:
        def unique(pairs):
            value = {}
            for key, item in pairs:
                if key in value: raise ValueError('Duplicate private idle JSON field')
                value[key] = item
            return value
        value = json.loads(payload, object_pairs_hook=unique, parse_constant=_nonfinite_project_number)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ValidationError('Malformed private idle evidence JSON') from None
    need(type(value) is dict and (not canonical or canonical_bytes(value) == payload),
         'Idle evidence must be one canonical JSON object')
    return value


def _false_quality(raw):
    need(all(raw[key] is False for key in QUALITY), 'Idle evidence upgraded unreviewed quality or use rights')


def checked_summary(raw, operation, request, folder, budget):
    raw = closed(raw, {'schema_version', 'status', 'operation', 'request_sha256', 'target',
        'anatomical_frame_sha256', 'source_profile', 'skeleton_fingerprint', 'bone_count', 'outputs',
        'sample_count', 'source_first_frame', 'source_last_frame', 'fps', *QUALITY})
    inspect = operation == INSPECT
    need(type(raw['schema_version']) is int and raw['schema_version'] == 1
        and raw['status'] == STATUS[operation] and raw['operation'] == operation
        and raw['request_sha256'] == request.sha256 and raw['source_profile'] == PROFILE
        and type(raw['bone_count']) is int and raw['bone_count'] == 163
        and type(raw['sample_count']) is int and raw['sample_count'] == (0 if inspect else 300)
        and all(raw[key] is None if inspect else type(raw[key]) is int and raw[key] == expected
                for key, expected in (('source_first_frame', 2), ('source_last_frame', 301), ('fps', 30))),
        'Idle worker summary lost its exact phase, target family or complete clock')
    _false_quality(raw)
    checked_sha(raw['anatomical_frame_sha256']); checked_sha(raw['skeleton_fingerprint'])
    target = TargetActionTarget.from_dict(raw['target']); project = request.project
    need((target.project_id, target.revision, target.project_sha256, target.master_sha256) ==
        (project.project_id, project.revision, document_sha256(project.to_dict()),
         dict(request.to_dict()['consumed_sources'])['master_and_derived_rig']),
        'Actual idle target is not bound to the saved inspection snapshot and master')
    if not inspect:
        need(target == request.target and raw['anatomical_frame_sha256'] == request.anatomical_frame_sha256,
             'Idle phase remeasured a different target or anatomical frame')
    rows = raw['outputs']; names = OUTPUTS[operation]
    need(type(rows) is list and len(rows) == len(names), 'Idle output manifest is incomplete')
    for row, name in zip(rows, names):
        closed(row, {'name', 'bytes', 'sha256'}); checked_sha(row['sha256'])
        need(row['name'] == name and type(row['bytes']) is int and row == record(folder/name, budget),
             'Idle output manifest differs from actual fixed owned files')
    return target


def _vector(value, size=3):
    need(type(value) is list and len(value) == size and all(type(x) in (int, float)
        and math.isfinite(x) and abs(x) < 10000 for x in value), 'Idle anatomy has invalid bounded numeric values')


def _scalar(value, maximum):
    need(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= maximum,
         'Idle numeric report exceeds its declared finite error bound')


def checked_frame(frame, target, expected_sha, summary):
    closed(frame, {'schema_version', 'profile', 'target', 'source_profile', 'skeleton_fingerprint',
                   'anatomy', 'sole_patches', 'neutral'})
    need(type(frame['schema_version']) is int and frame['schema_version'] == 1 and frame['profile'] == FRAME_PROFILE
        and frame['target'] == target.to_dict() and frame['source_profile'] == PROFILE
        and private_sha(frame) == expected_sha, 'Idle anatomical frame differs from its actual measured target')
    anatomy = closed(frame['anatomy'], {'axes', 'hands', 'bones'})
    axes = closed(anatomy['axes'], {'right', 'up', 'forward'})
    for value in axes.values():
        _vector(value); need(abs(sum(x*x for x in value)-1) < 1e-6, 'Idle anatomical axes are not unit vectors')
    right, up, forward = (axes[key] for key in ('right', 'up', 'forward'))
    cross = [up[1]*right[2]-up[2]*right[1], up[2]*right[0]-up[0]*right[2], up[0]*right[1]-up[1]*right[0]]
    need(max(abs(a-b) for a, b in zip(cross, forward)) < 1e-6, 'Idle frame does not corroborate the public anterior convention')
    closed(anatomy['hands'], {'L', 'R'})
    for hand in anatomy['hands'].values():
        closed(hand, {'direction', 'normal', 'flex_axis'})
        for value in hand.values(): _vector(value)
    bones = anatomy['bones']; need(type(bones) is list and len(bones) == summary['bone_count'], 'Idle full rest hierarchy is incomplete')
    names = set(); topology = []
    for row in bones:
        closed(row, {'name', 'parent', 'head_world', 'tail_world', 'rest_local', 'rest_world'})
        checked_text(row['name'], 128)
        need(row['name'] not in names and (row['parent'] is None or row['parent'] in names), 'Idle rest hierarchy is duplicated or unordered')
        names.add(row['name']); topology.append({'name': row['name'], 'parent': row['parent']})
        for key in ('head_world', 'tail_world'): _vector(row[key])
        for key in ('rest_local', 'rest_world'): _vector(row[key], 16)
    fingerprint = sha256(json.dumps({'profile': PROFILE, 'bones': topology}, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    need(frame['skeleton_fingerprint'] == summary['skeleton_fingerprint'] == fingerprint, 'Idle measured family fingerprint differs from actual hierarchy')
    neutral = closed(frame['neutral'], {'rig_name', 'human_name', 'rig_world', 'human_world', 'stable_invariants_sha256',
        'full_vertex_count', 'full_skin_sha256', 'visible_skin_sha256', 'weights_sha256', 'key_state_sha256'})
    for key in ('rig_name', 'human_name'): checked_text(neutral[key], 128)
    for key in ('rig_world', 'human_world'): _vector(neutral[key], 16)
    need(type(neutral['full_vertex_count']) is int and neutral['full_vertex_count'] == 19158, 'Idle neutral complete skin profile differs')
    for key in ('stable_invariants_sha256', 'full_skin_sha256', 'visible_skin_sha256', 'weights_sha256', 'key_state_sha256'): checked_sha(neutral[key])
    patches = closed(frame['sole_patches'], {'L', 'R'})
    for patch in patches.values():
        closed(patch, {'indices', 'neutral_world'}); indices = patch['indices']
        need(type(indices) is list and 3 <= len(indices) <= 2048 and len(set(indices)) == len(indices)
            and all(type(i) is int and 0 <= i < neutral['full_vertex_count'] for i in indices)
            and type(patch['neutral_world']) is list and len(patch['neutral_world']) == len(indices), 'Idle neutral sole patches are incomplete')
        for point in patch['neutral_world']: _vector(point)
    return frame


def checked_inspection(folder, request, summary, budget):
    frame = read_idle_json(folder/'idle_anatomical_frame.json', budget, summary['anatomical_frame_sha256'])
    target = TargetActionTarget.from_dict(summary['target'])
    checked_frame(frame, target, summary['anatomical_frame_sha256'], summary)
    report = read_idle_json(folder/'idle_inspection_report.json', budget)
    expected = {'schema_version': 1, 'status': STATUS[INSPECT], 'inspection_request_sha256': request.sha256,
        'target': target.to_dict(), 'anatomical_frame': summary['outputs'][0], 'source_profile': PROFILE,
        'skeleton_fingerprint': summary['skeleton_fingerprint'], 'bone_count': summary['bone_count'],
        'existing_action_count': 0, 'existing_motion_read': False, 'authoring_performed': False, **QUALITY}
    need(canonical_bytes(report) == canonical_bytes(expected), 'Idle inspection raw report differs from its exact summary and neutral-only scope')
    return target, frame


def checked_numeric(value):
    closed(value, {'direct_samples', 'maximum_neutral_sole_drift_m', 'analytic_virtual_seam_quaternion_residual',
        'analytic_virtual_seam_first_derivative_residual_rad_s', 'virtual_seam_was_stored', 'human_review_approved'})
    need(type(value['direct_samples']) is int and value['direct_samples'] == 300
        and value['virtual_seam_was_stored'] is False and value['human_review_approved'] is False,
        'Idle direct reference is partial or overclaims approval')
    for name, maximum in (('maximum_neutral_sole_drift_m', .001), ('analytic_virtual_seam_quaternion_residual', 1e-6),
                          ('analytic_virtual_seam_first_derivative_residual_rad_s', 1e-12)):
        _scalar(value[name], maximum)


def checked_recipe(folder, request, summary, frame, budget):
    recipe = read_idle_json(folder/'authored_idle_recipe.json', budget)
    closed(recipe, {'schema_version', 'profile', 'authoring_request_sha256', 'anatomical_frame_sha256', 'target',
        'skeleton_fingerprint', 'construction', 'source_samples', 'source_first_frame', 'source_last_frame', 'fps',
        'review_first_frame', 'review_last_frame', 'virtual_source_frame302_stored', 'existing_motion_read', 'armature_only_source', *QUALITY})
    expected = {'schema_version': 1, 'profile': PROFILE, 'authoring_request_sha256': request.sha256,
        'anatomical_frame_sha256': request.anatomical_frame_sha256, 'target': request.target.to_dict(),
        'skeleton_fingerprint': summary['skeleton_fingerprint'], 'source_samples': 300, 'source_first_frame': 2,
        'source_last_frame': 301, 'fps': 30, 'review_first_frame': 1, 'review_last_frame': 300,
        'virtual_source_frame302_stored': False, 'existing_motion_read': False, 'armature_only_source': True, **QUALITY}
    need(canonical_bytes({key: recipe[key] for key in expected}) == canonical_bytes(expected), 'Idle recipe clock, origin scope or use flags changed')
    construction = closed(recipe['construction'], {'baseline_quaternions', 'periodic_axes', 'baseline_max_anatomical_direction_residual'})
    names = {row['name'] for row in frame['anatomy']['bones']}
    need(type(construction['baseline_quaternions']) is dict and set(construction['baseline_quaternions']) == names, 'Idle recipe omitted full hierarchy baseline')
    for name, quaternion in construction['baseline_quaternions'].items():
        _vector(quaternion, 4); need(abs(sum(x*x for x in quaternion)-1) <= 1e-5, 'Idle baseline quaternion is not normalized')
        if not re.fullmatch(r'(?:upperarm01|lowerarm01|wrist)\.[LR]|finger[1-5]-[1-3]\.[LR]', name):
            need(abs(abs(quaternion[0])-1) <= 1e-6 and max(abs(x) for x in quaternion[1:]) <= 1e-6,
                 'Idle baseline changed an unaddressed helper or metacarpal')
    axes = construction['periodic_axes']
    need(type(axes) is dict and set(axes) == {'spine03', 'head', 'lowerarm01.L', 'lowerarm01.R'}, 'Idle periodic recipe addresses unexpected bones')
    for name, row in axes.items():
        closed(row, {'kind', 'axis'}); _vector(row['axis'])
        need(row['kind'] == ('torso' if name == 'spine03' else 'head' if name == 'head' else 'elbow')
            and abs(sum(x*x for x in row['axis'])-1) <= 1e-5, 'Idle periodic axis or semantic role changed')
    _scalar(construction['baseline_max_anatomical_direction_residual'], 1e-4)
    return recipe


def checked_author(folder, request, summary, frame, budget):
    recipe = checked_recipe(folder, request, summary, frame, budget)
    report = read_idle_json(folder/'authored_idle_report.json', budget)
    closed(report, {'schema_version', 'status', 'authoring_request_sha256', 'anatomical_frame_sha256', 'target',
        'skeleton_fingerprint', 'sample_count', 'numeric_observations', 'files', 'saved_reopen_verified',
        'private_geometry_metrics_not_for_model_output', *QUALITY})
    expected = {'schema_version': 1, 'status': STATUS[AUTHOR], 'authoring_request_sha256': request.sha256,
        'anatomical_frame_sha256': request.anatomical_frame_sha256, 'target': request.target.to_dict(),
        'skeleton_fingerprint': summary['skeleton_fingerprint'], 'sample_count': 300,
        'files': summary['outputs'][:3], 'saved_reopen_verified': False,
        'private_geometry_metrics_not_for_model_output': True, **QUALITY}
    need(canonical_bytes({key: report[key] for key in expected}) == canonical_bytes(expected), 'Idle author raw report differs from its actual outputs and pending scope')
    checked_numeric(report['numeric_observations'])
    return recipe


def _velocity(value, world_error):
    closed(value, {'position_m_s', 'rotation_matrix_s'})
    for number in value.values(): _scalar(number, world_error*60+1e-12)


def checked_verification(folder, request, summary, frame, budget, source_sha):
    report = read_idle_json(folder/'authored_idle_verification.json', budget)
    closed(report, {'schema_version', 'status', 'authoring_request_sha256', 'anatomical_frame_sha256',
        'target', 'skeleton_fingerprint', 'direct_recipe', 'saved_review', 'actual_fbx_source',
        'original_inputs_preserved', 'private_geometry_metrics_not_for_model_output', 'required_quality_execution',
        'independent_root_nine_worker_and_human_review_required', *QUALITY})
    expected = {'schema_version': 1, 'status': STATUS[VERIFY], 'authoring_request_sha256': request.sha256,
        'anatomical_frame_sha256': request.anatomical_frame_sha256, 'target': request.target.to_dict(),
        'skeleton_fingerprint': summary['skeleton_fingerprint'], 'original_inputs_preserved': True,
        'private_geometry_metrics_not_for_model_output': True, 'required_quality_execution': QUALITY_EXECUTION,
        'independent_root_nine_worker_and_human_review_required': True, **QUALITY}
    need(canonical_bytes({key: report[key] for key in expected}) == canonical_bytes(expected),
         'Idle independent verification changed its exact partial quality scope or input binding')
    checked_numeric(report['direct_recipe'])
    review = closed(report['saved_review'], {'saved_review_samples', 'maximum_recipe_world_matrix_residual',
        'maximum_saved_neutral_sole_drift_m', 'actual_stored_review_frames', 'wrapped_same_interval_velocity_residual'})
    need(type(review['saved_review_samples']) is int and review['saved_review_samples'] == 300
        and review['actual_stored_review_frames'] == [1, 300], 'Saved idle review is not the complete stored clock')
    _scalar(review['maximum_recipe_world_matrix_residual'], 1e-5)
    _scalar(review['maximum_saved_neutral_sole_drift_m'], .001)
    _velocity(review['wrapped_same_interval_velocity_residual'], review['maximum_recipe_world_matrix_residual'])
    source = closed(report['actual_fbx_source'], {'source_samples', 'actual_source_frames', 'fps',
        'maximum_source_recipe_world_matrix_residual', 'wrapped_same_interval_velocity_residual',
        'source_bone_count', 'source_snapshot', 'armature_only', 'automatic_retarget_family_admission'})
    need(type(source['source_samples']) is int and source['source_samples'] == 300
        and source['actual_source_frames'] == [2, 301] and type(source['fps']) is int and source['fps'] == 30
        and type(source['source_bone_count']) is int and source['source_bone_count'] == summary['bone_count']
        and source['source_snapshot'] == summary['outputs'][0] and source['armature_only'] is True
        and source['automatic_retarget_family_admission'] is False, 'Actual idle FBX import is partial or claims a retarget family')
    _scalar(source['maximum_source_recipe_world_matrix_residual'], 1e-4)
    _velocity(source['wrapped_same_interval_velocity_residual'], source['maximum_source_recipe_world_matrix_residual'])
    snapshot = read_idle_json(folder/'authored_idle_source_snapshot.json', budget,
        summary['outputs'][0]['sha256'], canonical=False, maximum=64*1024*1024)
    validate_snapshot(snapshot, source_sha, cancel_check=budget.check)
    need((snapshot['first_frame'], snapshot['last_frame'], snapshot['fps']) == (2, 301, 30)
        and len(snapshot['frames']) == 300 and len(snapshot['bones']) == summary['bone_count']
        and {row['name']: row['parent'] for row in snapshot['bones']} ==
            {row['name']: row['parent'] for row in frame['anatomy']['bones']},
        'Actual idle source snapshot differs from its measured full hierarchy or source clock')
    return report
