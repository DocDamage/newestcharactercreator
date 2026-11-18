"""Candidate same-rig mapping for an authenticated original MPFB idle only.

Call ONLY after the host's current-source/policy/three-worker candidate loader.
Exact payload hashes and successful result records do not prove execution or
authorship by themselves. This pure builder performs no file I/O, catalog write,
native execution or usable/loop approval. Existing nine-worker admission remains
mandatory, including all its unchanged weight, palm, surface and strain guards.
"""
from hashlib import sha256
import json
import math

from ucc.core.authored_idle import AuthoredIdleRequest
from ucc.core.errors import ValidationError
from ucc.core.target_action_format import checked_sha, checked_uuid, closed
from .authored_idle_mapping_math import check_same_rig_full_clock, need
from .fbx_snapshot import validate_snapshot
from .native_palms import validate_palm_hierarchy
from .native_profile import CONVENTION, validate_native_profile

SOURCE_PROFILE = 'UCC_ORIGINAL_MPFB_IDLE_SOURCE_V1'
FRAME_PROFILE = 'UCC_MEASURED_MPFB_IDLE_ANATOMY_V1'
VERIFY = 'verify_authored_idle_source'
STATUS = 'ORIGINAL_IDLE_FRESH_REOPEN_FULL300_VERIFIED_NOT_USABLE_APPROVED'
QUALITY = frozenset({'human_visual_review_approved', 'loop_quality_approved', 'usable_action_approved',
    'engine_import_verified', 'sprite_use_authorized', 'source_redistribution_authorized',
    'quality_measurements_verified', 'source_authorship_proven'})


def _json(payload: bytes, expected_sha: str, limit: int) -> dict:
    checked_sha(expected_sha)
    need(type(payload) is bytes and 0 < len(payload) <= limit
         and sha256(payload).hexdigest() == expected_sha,
         'Original idle mapping input bytes differ from their admitted pin or bound')
    def pairs(items):
        result = {}
        for key,value in items:
            need(key not in result, 'Duplicate original idle mapping evidence key')
            result[key] = value
        return result
    def invalid(_):
        raise ValueError('Nonfinite mapping evidence')
    def finite_float(token):
        value = float(token)
        need(math.isfinite(value), 'Nonfinite original idle mapping evidence number')
        return value
    try:
        result = json.loads(payload, object_pairs_hook=pairs, parse_constant=invalid, parse_float=finite_float)
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ValidationError('Malformed original idle mapping evidence') from error
    need(type(result) is dict, 'Original idle mapping evidence must be an object')
    return result


def _false_quality(value: dict) -> None:
    need(all(value.get(key) is False for key in QUALITY),
         'Original idle mapping cannot promote quality, rights or authorship')


def _record(record: object, name: str, payload: bytes) -> None:
    item = closed(record, {'name','bytes','sha256'})
    need(item['name'] == name and type(item['bytes']) is int and item['bytes'] == len(payload)
         and item['sha256'] == sha256(payload).hexdigest(),
         'Actual verification result does not bind the exact mapping evidence bytes')


def _pairs() -> list[dict]:
    # Actual default MPFB digits, not the Hips-family metacarpal aliases.
    rows = [('@ARMATURE','root',None,'BODY'),
        ('spine05','spine05','spine03','FORWARD'),
        ('spine03','spine03','spine01','FORWARD'),
        ('spine01','spine01','neck01','FORWARD'),
        ('neck01','neck01','neck02','FORWARD'),
        ('neck02','neck02','head','FORWARD'), ('head','head',None,'FORWARD')]
    for side in ('L','R'):
        for name,tip,axis in (('clavicle','upperarm01','FORWARD'),
                ('upperarm01','lowerarm01','FORWARD'), ('lowerarm01','wrist','FORWARD'),
                ('wrist','finger3-1','FORWARD'), ('upperleg01','lowerleg01','FORWARD'),
                ('lowerleg01','foot','FORWARD'), ('foot','toe3-1','UP')):
            rows.append((name+'.'+side,name+'.'+side,tip+'.'+side,axis))
    for side in ('L','R'):
        for digit in range(1,6):
            for joint in range(1,4):
                name = f'finger{digit}-{joint}.{side}'
                tip = f'finger{digit}-{joint+1}.{side}' if joint < 3 else None
                rows.append((name,name,tip,'PALM_LEFT_V1' if side == 'L' else 'PALM_RIGHT_V1'))
    return [{'source':source,'target':target,'source_tip':tip,'target_tip':tip,'secondary':axis}
            for source,target,tip,axis in rows]


def _build_original_idle_profile(request: AuthoredIdleRequest, *, frame_json: bytes,
        recipe_json: bytes, snapshot_json: bytes, verification_json: bytes,
        worker_request_json: bytes, worker_result_json: bytes,
        source_sha256: str, review_sha256: str, recipe_sha256: str,
        snapshot_sha256: str, worker_request_sha256: str, worker_result_sha256: str,
        inspection_job_id: str, verification_job_id: str, cancel_check) -> dict:
    """Build an explicit 51-pair profile, never an automatic family fallback.

    Host supplies the exact admitted candidate byte buffers and actual verifier
    request/result pins. Inspection, author and verifier identities are distinct.
    The caller must keep that candidate receipt/current-policy guard live while
    consuming the returned map through existing target-action preparation.
    """
    cancel_check()
    need(type(request) is AuthoredIdleRequest, 'Original idle mapping needs the actual typed authoring intent')
    for pin in (source_sha256,review_sha256,recipe_sha256,snapshot_sha256):
        checked_sha(pin)
    checked_uuid(inspection_job_id); checked_uuid(verification_job_id)
    need(len({inspection_job_id,request.job_id,verification_job_id}) == 3,
         'Original idle mapping needs distinct actual inspection, author and verifier workers')
    frame = _json(frame_json, request.anatomical_frame_sha256, 16*1024*1024)
    recipe = _json(recipe_json, recipe_sha256, 16*1024*1024)
    cancel_check()
    snapshot = _json(snapshot_json, snapshot_sha256, 64*1024*1024)
    cancel_check()
    worker = _json(worker_request_json, worker_request_sha256, 256*1024)
    result = _json(worker_result_json, worker_result_sha256, 256*1024)
    closed(worker, {'protocol_version','job_id','operation','input_project','options'})
    need(type(worker['protocol_version']) is int and worker['protocol_version'] == 1
         and worker['job_id'] == verification_job_id and worker['operation'] == VERIFY
         and worker['input_project'] == 'candidate.blend'
         and worker['options'] == {'request_sha256':request.sha256,'source_sha256':source_sha256,
                                  'review_sha256':review_sha256,'recipe_sha256':recipe_sha256},
         'Original idle mapping verifier request has different phase or source bindings')
    closed(result, {'protocol_version','job_id','operation','status','details','error'})
    need(type(result['protocol_version']) is int and result['protocol_version'] == 1
         and result['job_id'] == verification_job_id and result['operation'] == VERIFY
         and result['status'] == 'ok' and result['error'] is None,
         'Original idle mapping lacks a successful matching verifier result')
    summary = closed(result['details'], {'schema_version','status','operation','request_sha256','target',
        'anatomical_frame_sha256','source_profile','skeleton_fingerprint','bone_count','outputs',
        'sample_count','source_first_frame','source_last_frame','fps',*QUALITY})
    _false_quality(summary)
    need(type(summary['schema_version']) is int and summary['schema_version'] == 1
         and summary['status'] == STATUS and summary['operation'] == VERIFY
         and summary['request_sha256'] == request.sha256 and summary['target'] == request.target.to_dict()
         and summary['anatomical_frame_sha256'] == request.anatomical_frame_sha256
         and summary['source_profile'] == SOURCE_PROFILE,
         'Original idle mapping verifier summary lost actual target/recipe lineage')
    need(all(type(summary[key]) is int and summary[key] == value for key,value in
         (('bone_count',163),('sample_count',300),('source_first_frame',2),('source_last_frame',301),('fps',30))),
         'Original idle mapping needs the complete measured MPFB clock')
    need(type(summary['outputs']) is list and len(summary['outputs']) == 2,
         'Original idle verifier output closure differs')
    _record(summary['outputs'][0], 'authored_idle_source_snapshot.json', snapshot_json)
    _record(summary['outputs'][1], 'authored_idle_verification.json', verification_json)
    verification = _json(verification_json, summary['outputs'][1]['sha256'], 16*1024*1024)
    closed(verification, {'schema_version','status','authoring_request_sha256','anatomical_frame_sha256',
        'target','skeleton_fingerprint','direct_recipe','saved_review','actual_fbx_source',
        'original_inputs_preserved','private_geometry_metrics_not_for_model_output','required_quality_execution',
        'independent_root_nine_worker_and_human_review_required',*QUALITY})
    _false_quality(verification)
    need(type(verification['schema_version']) is int and verification['schema_version'] == 1
         and verification['status'] == STATUS and verification['authoring_request_sha256'] == request.sha256
         and verification['anatomical_frame_sha256'] == request.anatomical_frame_sha256
         and verification['target'] == request.target.to_dict() and verification['original_inputs_preserved'] is True
         and verification['independent_root_nine_worker_and_human_review_required'] is True,
         'Original idle raw verification differs from its admitted candidate')
    execution = verification['required_quality_execution']
    measured = {'root_neutral_measured','lower_chain_neutral_measured','neutral_sole_drift_measured',
        'full300_finite_zero_translation_unit_scale','analytic_seam_value_measured',
        'analytic_seam_first_derivative_measured','wrapped_same_interval_velocities_measured'}
    unrun = {'palmar_skin_surface_normal_verified','hand_digit_body_clearance_measured',
        'human_visual_review_performed','complete_required_quality_verified'}
    closed(execution, measured | unrun)
    need(all(execution[key] is True for key in measured) and all(execution[key] is False for key in unrun),
         'Original idle verification omitted measurements or upgraded unrun quality')
    _record(verification['actual_fbx_source']['source_snapshot'], 'authored_idle_source_snapshot.json', snapshot_json)
    need(all(type(row[key]) is int and row[key] == 300 for row,key in (
            (verification['direct_recipe'],'direct_samples'),
            (verification['saved_review'],'saved_review_samples'),
            (verification['actual_fbx_source'],'source_samples')))
         and verification['actual_fbx_source']['actual_source_frames'] == [2,301]
         and verification['actual_fbx_source']['armature_only'] is True
         and verification['actual_fbx_source']['automatic_retarget_family_admission'] is False,
         'Original idle verification omitted saved/source frames')
    closed(frame, {'schema_version','profile','target','source_profile','skeleton_fingerprint','anatomy','sole_patches','neutral'})
    need(type(frame['schema_version']) is int and frame['schema_version'] == 1
         and frame['profile'] == FRAME_PROFILE and frame['source_profile'] == SOURCE_PROFILE
         and frame['target'] == request.target.to_dict(), 'Original idle measured target/frame family differs')
    closed(frame['anatomy'], {'axes','hands','bones'})
    need(type(frame['anatomy']['bones']) is list and len(frame['anatomy']['bones']) == 163,
         'Original idle frame lacks the complete supported anatomy')
    closed(recipe, {'schema_version','profile','authoring_request_sha256','anatomical_frame_sha256','target',
        'skeleton_fingerprint','construction','source_samples','source_first_frame','source_last_frame','fps',
        'review_first_frame','review_last_frame','virtual_source_frame302_stored','existing_motion_read',
        'armature_only_source',*QUALITY})
    fingerprint = sha256(json.dumps({'profile':SOURCE_PROFILE,
        'bones':[{'name':row['name'],'parent':row['parent']} for row in frame['anatomy']['bones']]},
        sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    need(all(value == fingerprint for value in (frame['skeleton_fingerprint'],
         summary['skeleton_fingerprint'],verification['skeleton_fingerprint'],recipe['skeleton_fingerprint'])),
         'Original idle measured topology fingerprint differs across its actual proofs')
    need(type(recipe['schema_version']) is int and recipe['schema_version'] == 1
         and recipe['profile'] == SOURCE_PROFILE and recipe['authoring_request_sha256'] == request.sha256
         and recipe['anatomical_frame_sha256'] == request.anatomical_frame_sha256
         and recipe['target'] == request.target.to_dict() and recipe['source_samples'] == 300
         and recipe['source_first_frame'] == 2 and recipe['source_last_frame'] == 301
         and recipe['fps'] == 30 and recipe['virtual_source_frame302_stored'] is False
         and recipe['existing_motion_read'] is False and recipe['armature_only_source'] is True,
         'Original idle mapping recipe changed source clock, measured target or original scope')
    _false_quality(recipe)
    observed = validate_snapshot(snapshot, source_sha256, cancel_check=cancel_check)
    need((observed['frame_count'], observed['first_frame'], observed['last_frame'], observed['fps']) == (300,2,301,30.),
         'Original idle mapping source clock differs')
    pairs = _pairs()
    check_same_rig_full_clock(snapshot, frame, {row['source'] for row in pairs if row['source'] != '@ARMATURE'},
                              cancel_check=cancel_check)
    landmarks = {key:{'source':name,'target':name} for key,name in (
        ('left_hip','upperleg01.L'),('right_hip','upperleg01.R'),('head','head'),
        ('left_hand','wrist.L'),('right_hand','wrist.R'),('left_foot','foot.L'),('right_foot','foot.R'))}
    planes = {side:{key:{'source':name+'.'+suffix,'target':name+'.'+suffix}
        for key,name in (('index','finger2-1'),('pinky','finger5-1'))}
        for side,suffix in (('left','L'),('right','R'))}
    profile = {'schema_version':1,'convention':CONVENTION,
        'source_sha256':source_sha256,'snapshot_sha256':snapshot_sha256,'master_sha256':request.target.master_sha256,
        'root_motion_policy':'ARMATURE_ORIGIN_DISPLACEMENT_V1','skin_deformation_policy':'BOUND_CORRECTIVE_SMOOTH_V1',
        'mesh_strain_reference':'TRUE_NEUTRAL_BIND_V2','landmarks':landmarks,'pairs':pairs,
        'hand_reference_planes':{'schema_version':2,'planes':planes}}
    validate_native_profile(profile,source_sha256,snapshot_sha256,request.target.master_sha256)
    parents = {row['name']:row['parent'] for row in snapshot['bones']}
    validate_palm_hierarchy(profile,parents,'source')
    validate_palm_hierarchy(profile,parents,'target')
    return profile


def build_original_idle_profile(request: AuthoredIdleRequest, *, cancel_check=lambda: None, **evidence) -> dict:
    """Checked pure boundary; see the implementation's explicit evidence inputs.

    Missing/malformed nested evidence rejects without exposing private numeric
    data. It does not turn a candidate's hashes into execution or rights proof.
    """
    try:
        return _build_original_idle_profile(request, cancel_check=cancel_check, **evidence)
    except ValidationError:
        raise
    except (KeyError, TypeError, ValueError, IndexError, OverflowError, RecursionError) as error:
        raise ValidationError('Malformed or incomplete admitted original idle mapping inputs') from error
