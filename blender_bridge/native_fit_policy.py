"""Independent worker-side intake for a bounded, SHA-bound target fit."""
import math
from blender_bridge.native_inputs import read_json
from blender_bridge.native_hand_fit import POLICY as HAND_POLICY,rotations,orient

POLICY='BOUNDED_NATIVE_ARM_IK_V1'
BODY_POLICY='BOUNDED_NATIVE_BODY_SHAPE_IK_V3'
BASE_HASHES={'source_sha256','snapshot_sha256','mapping_sha256','master_sha256','review_sha256','timeline_sha256'}
OPERATIONS={'fit_native_fbx_body':{'fit_sha256'},
            'measure_native_fit':{'fit_sha256','fitted_sha256'},
            'verify_native_fit':{'fit_sha256','fitted_sha256','fit_report_sha256'},
            'cache_native_fit':{'fit_sha256','fitted_sha256','fit_report_sha256'}}


def job_hashes(operation):
    if operation not in OPERATIONS:raise ValueError('Unknown native fitting operation')
    return BASE_HASHES|OPERATIONS[operation]


def checked_job(job):
    fields=job_hashes(job['operation']);options=job['options']
    from blender_bridge.native_symmetric_policy import BASE_FIT_HASHES
    if type(options) is dict and BASE_FIT_HASHES & set(options):fields |= BASE_FIT_HASHES
    if (job['input_project']!='candidate.blend' or type(options) is not dict or set(options)!=fields or
        any(type(v) is not str or len(v)!=64 or any(c not in '0123456789abcdef' for c in v) for v in options.values())):
        raise ValueError('Native fitting requires exact input hashes and fixed staged filenames')
    return options


def parse_fit(data,bindings,baseline,profile,parents):
    required={'schema_version','policy','bindings','coordinate_space','chain','fps','frames'}
    if (type(data) is not dict or set(data)-{'render_frames'}!=required or
        type(data['schema_version']) is not int or data['schema_version']!=1 or type(data['policy']) is not str or data['policy'] not in (POLICY,HAND_POLICY,BODY_POLICY) or
        data['coordinate_space']!='BLENDER_WORLD_METERS' or data['bindings']!=bindings or
        profile.get('skin_deformation_policy')!='BOUND_CORRECTIVE_SMOOTH_V1' or
        profile.get('mesh_strain_reference')!='TRUE_NEUTRAL_BIND_V2'):
        raise ValueError('Invalid native fit policy, source identity or skin reference')
    targets=[p['target'] for p in profile['pairs']];known=set(targets)|set(baseline['neutral_target_helpers'])
    if (type(parents) is not dict or set(parents)!=known or len(known)>256 or
        any(type(n) is not str or (p is not None and (type(p) is not str or p not in known)) for n,p in parents.items()) or
        sum(p is None for p in parents.values())!=1):
        raise ValueError('Native fitting needs the complete actual target hierarchy')
    paths={}
    for name in parents:
        path=[];current=name
        while current is not None:
            if current in path:raise ValueError('Cyclic native fit target hierarchy')
            path.append(current);current=parents[current]
        paths[name]=path
    chain=data['chain']
    if (type(chain) is not dict or set(chain)!={'side','upper_arm','forearm','hand'} or
        type(chain['side']) is not str or chain['side'] not in {'left','right'} or
        any(type(chain[k]) is not str or chain[k] not in targets for k in ('upper_arm','forearm','hand'))):
        raise ValueError('Invalid explicit native fitting arm')
    upper,lower,hand=(chain[k] for k in ('upper_arm','forearm','hand'))
    if (len({upper,lower,hand})!=3 or targets[0] in (upper,lower,hand) or
        hand!=profile['landmarks'][chain['side']+'_hand']['target'] or
        [n for n in paths[hand][1:] if n in targets][:2]!=[lower,upper]):
        raise ValueError('Native fitting arm crosses its declared mapped hand hierarchy')
    count=baseline['source_frame_count'];fps=data['fps']
    def number(v):return type(v) in (float,int) and -1e6<=v<=1e6 and math.isfinite(v)
    if (type(count) is not int or not 5<=count<=2000 or not number(fps) or not 1<=fps<=240 or fps!=baseline['fps'] or
        type(data['frames']) is not list or len(data['frames'])!=count):
        raise ValueError('Native fitting requires the complete renderable source timeline and FPS')
    landmarks=baseline['target_anatomical_landmarks']
    feet=[(landmarks['left_foot'][i]+landmarks['right_foot'][i])/2 for i in range(3)]
    span=math.dist(landmarks['head'],feet)
    if not .1<span<10:raise ValueError('Invalid native fitting body span')
    maximum=min(.08,.05*span) if data['policy']==BODY_POLICY else min(.03,.02*span)
    offsets=[];hand_policy=data['policy'] in (HAND_POLICY,BODY_POLICY)
    for frame,row in enumerate(data['frames'],1):
        if type(row) is not dict or set(row)!=({'frame','offset_world'}|({'hand_rotation_local_degrees'} if hand_policy else set())) or type(row['frame']) is not int or row['frame']!=frame:
            raise ValueError('Incomplete or reordered native fit trajectory')
        vector=row['offset_world']
        if type(vector) is not list or len(vector)!=3 or any(not number(v) for v in vector) or math.hypot(*vector)>maximum+1e-12:
            raise ValueError('Native fit offset exceeds fixed finite displacement limits')
        offsets.append(tuple(vector))
    if offsets[0]!=(0.,0.,0.) or offsets[-1]!=(0.,0.,0.) or not any(math.hypot(*v)>1e-7 for v in offsets):
        raise ValueError('Native fit must have unchanged endpoints and a nonzero bounded correction')
    velocity=[(0.,0.,0.)]+[tuple((b[i]-a[i])*fps for i in range(3)) for a,b in zip(offsets,offsets[1:])]+[(0.,0.,0.)]
    if (any(math.hypot(*v)>.3+1e-9 for v in velocity) or
        any(math.hypot(*(b[i]-a[i] for i in range(3)))*fps>5.+1e-9 for a,b in zip(velocity,velocity[1:]))):
        raise ValueError('Native fit correction velocity/acceleration exceeds fixed limits')
    samples=data.get('render_frames')
    if 'render_frames' in data and (type(samples) is not list or len(samples)!=5 or
        any(type(f) is not int or not 1<=f<=count for f in samples) or samples!=sorted(set(samples))):
        raise ValueError('Native fitting renders need five explicit ordered clip frames')
    if samples and not any(math.hypot(*offsets[f-1])>1e-7 for f in samples):
        raise ValueError('Native fitting renders omit every actual target correction')
    return {'targets':targets,'chain':(upper,lower,hand),'descendants':[n for n in targets if hand in paths[n]],
            'offsets':offsets,'maximum':maximum,'fps':fps,'render_frames':samples,'policy':data['policy'],
            'hand_rotations':rotations(data['frames'],fps) if hand_policy else ()}


def load_fit(root,options,baseline,profile,parents):
    if 'base_fit_policy_sha256' in options:
        from blender_bridge.native_symmetric_policy import load_symmetric
        plan=load_symmetric(root,options,baseline,profile,parents)
        report=read_json(root/'base_fitted_timeline.json',options['base_fit_report_sha256'],64*1024*1024)
        if type(report.get('frames')) is not list or len(report['frames'])!=baseline['source_frame_count']:
            raise ValueError('Symmetric layer lacks complete canonical base poses')
        plan['base_frames']=report['frames']
        return plan
    bindings={k:options[k] for k in BASE_HASHES}
    return parse_fit(read_json(root/'contact_fit.json',options['fit_sha256'],512*1024),bindings,baseline,profile,parents)


def _arm_world_poses(plan,poses,frame):
    """Blender quaternion/vector solve, independent of the application matrix solver."""
    from mathutils import Matrix,Vector
    matrices={name:Matrix([m[i:i+4] for i in range(0,16,4)]) for name,m in zip(plan['targets'],poses)}
    offset=Vector(plan['offsets'][frame-1])
    if offset.length==0:return matrices
    upper,lower,hand=plan['chain'];s,e,w=(matrices[n].translation.copy() for n in (upper,lower,hand))
    a,b=(e-s).length,(w-e).length;target=w+offset;direction=target-s;distance=direction.length
    if min(a,b)<1e-5 or not abs(a-b)+1e-7<distance<a+b-1e-7:
        raise ValueError('Native fitting endpoint is unreachable without scaling/clamping')
    axis=direction.normalized();pole=e-s-axis*(e-s).dot(axis)
    if pole.length<min(a,b)*1e-4:raise ValueError('Native fitting has an ambiguous straight-arm elbow pole')
    along=(a*a+distance*distance-b*b)/(2*distance)
    elbow=s+axis*along+pole.normalized()*math.sqrt(max(0.,a*a-along*along))
    if (elbow-e).length>plan['maximum']+1e-9:raise ValueError('Native fitting elbow exceeds displacement bound')
    for name,old,new,head in ((upper,e-s,elbow-s,s),(lower,w-e,target-elbow,elbow)):
        delta=old.rotation_difference(new)
        if math.degrees(delta.angle)>15.+1e-5:raise ValueError('Native fitting exceeds angular correction bound')
        matrices[name]=Matrix.LocRotScale(head,delta@matrices[name].to_quaternion(),Vector((1,1,1)))
    for name in plan['descendants']:matrices[name].translation+=offset
    return matrices


def fitted_world_poses(plan,poses,frame):
    from blender_bridge.native_symmetric_policy import POLICY as SYMMETRIC_POLICY
    if plan['policy']==SYMMETRIC_POLICY:
        from blender_bridge.native_symmetric_math import symmetric_world_poses
        return symmetric_world_poses(plan,poses,plan['base_frames'][frame-1]['target_global_poses'],frame)
    matrices=_arm_world_poses(plan,poses,frame)
    return orient(plan,matrices,frame) if plan.get('hand_rotations') else matrices
