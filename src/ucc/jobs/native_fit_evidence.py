"""Independent application checks for fitted results; source FK stays separate."""
from hashlib import sha256
import json
from pathlib import Path

from ucc.core.errors import ValidationError
from ucc.animations.contact_fit import POLICY,BODY_POLICY,HASHES,read_contact_fit,verify_fitted_sequence
from ucc.animations.hand_fit import POLICY as HAND_POLICY
from ucc.animations.symmetric_fit import POLICY as SYMMETRIC_POLICY
from ucc.animations.source_rest_frames import is_sha256
from ucc.animations import native_math as nm
from ucc.preview.surface_review import validate_surface_data
from .native_evidence import bound_file
from .native_skin_evidence import validate_reopen_report
from .motion_quality_evidence import validate_motion_quality

FLAGS={'contact_quality_verified','animation_visual_quality_verified','engine_import_verified'}


def number(v,low,high):
    return type(v) in (int,float) and low<=v<=high


def read_json_record(folder: Path,record: dict,name: str,maximum: int,*,cancel_check=lambda:None):
    path=bound_file(folder,record,name,maximum,cancel_check=cancel_check)
    with path.open('rb') as stream:payload=stream.read(maximum+1)
    if len(payload)!=record['bytes'] or sha256(payload).hexdigest()!=record['sha256']:
        raise ValidationError('Fitted evidence changed while reading')
    def unique(rows):
        result={}
        for k,v in rows:
            if k in result:raise ValueError('Duplicate fitted evidence field')
            result[k]=v
        return result
    def nonfinite(_v):raise ValueError('Nonfinite fitted evidence')
    try:return json.loads(payload,object_pairs_hook=unique,parse_constant=nonfinite),path
    except (ValueError,UnicodeError,RecursionError) as error:raise ValidationError('Invalid fitted evidence JSON') from error


def rest_parents(rest,baseline):
    known={p['target'] for p in baseline['mapped_pairs']}|set(baseline['neutral_target_helpers'])
    if type(rest) is not dict or set(rest)!=known or len(rest)>256:
        raise ValidationError('Fitted evidence lacks the complete original target rest frames')
    parents={}
    for name,row in rest.items():
        if (type(row) is not dict or set(row)!={'parent','matrix'} or
            (row['parent'] is not None and (type(row['parent']) is not str or row['parent'] not in known))):
            raise ValidationError('Invalid fitted target rest-frame identity')
        checked_matrix(row['matrix']);parents[name]=row['parent']
    if sum(p is None for p in parents.values())!=1:raise ValidationError('Fitted rest hierarchy needs one actual root')
    for name in parents:
        seen=set()
        while name is not None:
            if name in seen:raise ValidationError('Fitted rest hierarchy is cyclic')
            seen.add(name);name=parents[name]
    return parents


def checked_matrix(values):
    if type(values) is not list or len(values)!=16 or any(not number(v,-1e6,1e6) for v in values):
        raise ValidationError('Invalid bounded fitted matrix evidence')
    nm.rotation(values,target_noise=True)


def validate_fit_stage(report,options,baseline):
    fields={'status','bindings','frames','original_review_verification','fitted_scene','target_rest_frames',
            'max_ik_residual','max_unkeyed_translation','max_scale_error'}|FLAGS
    if (type(report) is not dict or set(report)!=fields or report['status']!='REAL_NATIVE_FIT_ACTION_STAGED' or
        report['bindings']!=options or type(report['frames']) is not int or report['frames']!=baseline['source_frame_count'] or
        any(report[k] is not False for k in FLAGS) or not number(report['max_ik_residual'],0,1e-4) or
        not number(report['max_unkeyed_translation'],0,1e-5) or not number(report['max_scale_error'],0,1e-4)):
        raise ValidationError('Fitted Action staging identity, bounds or approval differs')
    validate_reopen_report(report['original_review_verification'],{k:options[k] for k in HASHES},baseline)
    rest_parents(report['target_rest_frames'],baseline)


def validate_fitted_data(data,options,baseline,profile,policy_path,stage_rest,*,cancel_check=lambda:None):
    fields={'schema_version','policy','bindings','measurement','frame_count','source_first_frame','fps',
            'target_rest_frames','source_polygon_sha256','mesh_world','rig_world','original_review_verification',
            'bind_edge_strain','master_edge_strain','frames','joint_motion_metrics','surface_review',
            'angular_correction_metrics','originals_unchanged'}|FLAGS
    count=baseline['source_frame_count']
    if (type(data) is not dict or set(data)!=fields or type(data['schema_version']) is not int or data['schema_version']!=1 or
        type(data['policy']) is not str or data['policy'] not in (POLICY,HAND_POLICY,BODY_POLICY,SYMMETRIC_POLICY) or data['bindings']!=options or data['measurement']!='FRESH_SAVED_ACTION_V1' or
        type(data['frame_count']) is not int or data['frame_count']!=count or type(data['source_first_frame']) is not int or
        data['source_first_frame']!=baseline['source_first_frame'] or type(data['fps']) not in (float,int) or data['fps']!=baseline['fps'] or
        any(data[k] is not False for k in FLAGS) or data['originals_unchanged'] is not True or
        not is_sha256(data['source_polygon_sha256'])):
        raise ValidationError('Fitted measurement identity, complete coverage or approval differs')
    validate_reopen_report(data['original_review_verification'],{k:options[k] for k in HASHES},baseline)
    parents=rest_parents(data['target_rest_frames'],baseline)
    if data['target_rest_frames']!=stage_rest:raise ValidationError('Fitted canonical measurement changed actual original rest/roll')
    for key in ('mesh_world','rig_world'):checked_matrix(data[key])
    if data['rig_world']!=baseline['target_armature_world']:raise ValidationError('Fitted rig world differs from original source FK')
    if data['bind_edge_strain']!=baseline['bind_edge_strain'] or data['master_edge_strain']!=baseline['master_bind_edge_strain']:
        raise ValidationError('Fitted original/bound neutral topology differs')
    if 'base_fit_policy_sha256' in options:
        from .symmetric_fit_evidence import read_layer_plan
        plan,bases=read_layer_plan(policy_path,options,baseline,profile,stage_rest,cancel_check=cancel_check)
    else:
        plan=read_contact_fit(policy_path,options['fit_sha256'],{k:options[k] for k in HASHES},baseline,profile,parents,cancel_check=cancel_check)
    if data['policy']!=plan.policy:raise ValidationError('Fitted measurement policy differs from its bound trajectory')
    frames=data['frames']
    if type(frames) is not list or len(frames)!=count:raise ValidationError('Incomplete fitted geometry sequence')
    diagonal=baseline['model_baseline_diagonal_local'];vertex_count=triangle_count=None
    row_fields={'frame','source_frame','target_global_poses','skin_sha256','raw_skin_sha256','triangle_sha256',
                'vertex_count','triangle_count','moved_vertices','max_displacement_local','max_bind_displacement_local',
                'adjacent_max_displacement_local','bind_strain','master_strain','skin_correction'}
    for frame,row in enumerate(frames,1):
        cancel_check()
        if (type(row) is not dict or set(row)!=row_fields or type(row['frame']) is not int or row['frame']!=frame or
            type(row['source_frame']) is not int or row['source_frame']!=data['source_first_frame']+frame-1 or
            any(not is_sha256(row[k]) for k in ('skin_sha256','raw_skin_sha256','triangle_sha256')) or
            type(row['vertex_count']) is not int or not 100<row['vertex_count']<=100000 or
            type(row['triangle_count']) is not int or not 100<row['triangle_count']<=200000):
            raise ValidationError('Fitted skin/topology frame identity or workload differs')
        if vertex_count is None:vertex_count,triangle_count=row['vertex_count'],row['triangle_count']
        if row['vertex_count']!=vertex_count or row['triangle_count']!=triangle_count:
            raise ValidationError('Fitted evaluated topology count changed')
        if (type(row['moved_vertices']) is not int or not 0<=row['moved_vertices']<=vertex_count or
            not number(row['max_displacement_local'],0,diagonal*1.5) or not number(row['max_bind_displacement_local'],0,diagonal*1.5) or
            not number(row['adjacent_max_displacement_local'],0,diagonal*.8)):
            raise ValidationError('Fitted geometry has extreme/discontinuous movement')
        if frame==1 and (row['moved_vertices']!=0 or row['max_displacement_local']>1e-6 or row['adjacent_max_displacement_local']>1e-6):
            raise ValidationError('Fitted first pose is not its displacement reference')
        for key in ('bind_strain','master_strain'):
            measure=row[key]
            if (type(measure) is not dict or set(measure)!={'min_edge_length_ratio','max_edge_stretch_ratio'} or
                not number(measure['min_edge_length_ratio'],.05,4) or not number(measure['max_edge_stretch_ratio'],.05,4) or
                measure['min_edge_length_ratio']>measure['max_edge_stretch_ratio']):
                raise ValidationError('Fitted geometry violates the unchanged neutral/master strain bounds')
        correction=row['skin_correction']
        if (type(correction) is not dict or set(correction)!={'corrected_vertices','max_correction_local'} or
            type(correction['corrected_vertices']) is not int or not 0<=correction['corrected_vertices']<=vertex_count or
            not number(correction['max_correction_local'],0,diagonal*.03) or
            (correction['corrected_vertices']==0)!=(correction['max_correction_local']<=1e-6)):
            raise ValidationError('Fitted corrective skin exceeds existing original-skin bounds')
    originals=[r['target_global_poses'] for r in baseline['full_timeline_frames']]
    observed=[r['target_global_poses'] for r in frames]
    if plan.policy==SYMMETRIC_POLICY:
        from ucc.animations.symmetric_math import verify_symmetric_sequence
        audit=verify_symmetric_sequence(plan,originals,bases,observed,cancel_check=cancel_check)
        angular={'frames':audit['frames'],'tracked_joints':audit['tracked_joints'],
                 'max_correction_angular_speed_degrees_s':audit['max_speed_degrees_s'],
                 'max_correction_angular_acceleration_degrees_s2':audit['max_acceleration_degrees_s2']}
    else:angular=verify_fitted_sequence(plan,originals,observed)
    metric=data['angular_correction_metrics']
    if (type(metric) is not dict or set(metric)!={'max_speed_degrees_s','max_acceleration_degrees_s2'} or
        not number(metric['max_speed_degrees_s'],0,90.01) or not number(metric['max_acceleration_degrees_s2'],0,900.1)):
        raise ValidationError('Fitted angular correction evidence exceeds bounded worker numerical limits')
    if plan.policy in (HAND_POLICY,BODY_POLICY,SYMMETRIC_POLICY) and (
        abs(metric['max_speed_degrees_s']-angular['max_correction_angular_speed_degrees_s'])>.1 or
        abs(metric['max_acceleration_degrees_s2']-angular['max_correction_angular_acceleration_degrees_s2'])>2.):
        raise ValidationError('Fitted hand angular evidence differs from the independent full-sequence audit '
            f"(worker speed/acceleration {metric['max_speed_degrees_s']:.6g}/{metric['max_acceleration_degrees_s2']:.6g}; "
            f"core {angular['max_correction_angular_speed_degrees_s']:.6g}/{angular['max_correction_angular_acceleration_degrees_s2']:.6g})")
    quality={'motion_quality_schema_version':2,'target_pose_environment_checked':True,'mesh_edge_strain':data['bind_edge_strain'],
             'source_frame_count':count,'full_timeline_frames':[r['bind_strain'] for r in frames],
             'joint_motion_metrics':data['joint_motion_metrics'],'max_bone_quaternion_step_degrees':{}}
    joints=data['joint_motion_metrics'];names=[p['target'] for p in profile['pairs'][1:]]
    if type(joints) is not list or len(joints)!=len(names):raise ValidationError('Incomplete fitted joint safety evidence')
    for n,row in zip(names,joints):
        if type(row) is not dict or set(row)!={'bone','frames_measured','max_swing_degrees','max_swing_frame','max_twist_degrees','max_twist_frame','max_step_degrees','max_step_frame'}:
            raise ValidationError('Invalid fitted joint safety fields')
        quality['max_bone_quaternion_step_degrees'][n]=row['max_step_degrees']
    validate_motion_quality(quality,names,neutral_reference=True)
    surface_timeline={'source_frame_count':count,'full_timeline_frames':[{'evaluated_sha256':r['skin_sha256']} for r in frames],
                      'mapped_pairs':profile['pairs'],'neutral_target_helpers':baseline['neutral_target_helpers']}
    surface=validate_surface_data(data['surface_review'],options,surface_timeline,profile,triangle_count,vertex_count,cancel_check=cancel_check)
    if surface.triangle_hashes!=tuple(r['triangle_sha256'] for r in frames):raise ValidationError('Fitted surface/topology binding differs')
    return plan,surface,angular


def read_fitted_timeline(folder,report,options,baseline,profile,policy_path,stage_rest,*,cancel_check=lambda:None):
    if (type(report) is not dict or set(report)!={'status','bindings','frames','timeline'}|FLAGS or
        report['status']!='REAL_NATIVE_FIT_MEASURED' or report['bindings']!=options or
        type(report['frames']) is not int or report['frames']!=baseline['source_frame_count'] or any(report[k] is not False for k in FLAGS)):
        raise ValidationError('Fitted measurement worker did not produce the requested unapproved result')
    data,path=read_json_record(folder,report['timeline'],'fitted_timeline.json',64*1024*1024,cancel_check=cancel_check)
    plan,surface,angular=validate_fitted_data(data,options,baseline,profile,policy_path,stage_rest,cancel_check=cancel_check)
    return data,path,plan,surface,angular
