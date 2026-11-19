"""Preview-only axial alignment of direct measured leg and arm chains."""
import math

from ucc.core.errors import ValidationError

from . import native_math as nm
from .native_skin_policy import CORRECTIVE_POLICIES


_SIDES = ('left', 'right')
_MAX_FRAMES = 300
_MAX_UPPER_DEGREES = 5.5
_MAX_UPPER_STEP = 4.
_MAX_UPPER_TURNS = 32
_MAX_FOREARM_TENTHS = 60
_MAX_FOREARM_STEP_TENTHS = 15


def validate_limb_alignment(profile: dict) -> None:
    if 'limb_alignment' not in profile:
        return
    if (any(key in profile for key in ('wrist_transitions', 'forearm_roll', 'planted_knee'))
            or profile.get('root_motion_policy') != 'SOURCE_HIP_MIDPOINT_V1'
            or profile.get('mesh_strain_reference') != 'TRUE_NEUTRAL_BIND_V2'
            or profile.get('skin_deformation_policy') not in CORRECTIVE_POLICIES):
        raise ValidationError('Limb alignment requires a standalone hip-anchored preview with both neutral skin references')
    rule = profile['limb_alignment']
    if (type(rule) is not dict or set(rule) != {'schema_version', 'first_frame', 'upper_arm_turns', 'forearm_angle_tenths'}
            or type(rule['schema_version']) is not int or rule['schema_version'] != 1
            or type(rule['first_frame']) is not int or abs(rule['first_frame']) > 100_000):
        raise ValidationError('Invalid versioned limb alignment declaration')
    forearm = rule['forearm_angle_tenths']
    if type(forearm) is not dict or set(forearm) != set(_SIDES):
        raise ValidationError('Limb alignment requires a bilateral forearm schedule')
    for turns in forearm.values():
        if (type(turns) is not list or not 5 <= len(turns) <= _MAX_FRAMES
                or any(type(t) is not int or abs(t) > _MAX_FOREARM_TENTHS for t in turns)
                or turns[0] or turns[-1]
                or any(abs(b-a) > _MAX_FOREARM_STEP_TENTHS for a,b in zip(turns,turns[1:]))):
            raise ValidationError('Limb alignment forearm turns exceed the bounded schedule')
    count=len(forearm['left'])
    first=rule['first_frame']
    upper=rule['upper_arm_turns']
    if (count != len(forearm['right']) or type(upper) is not list or not 1 <= len(upper) <= _MAX_UPPER_TURNS
            or not any(t for turns in forearm.values() for t in turns)):
        raise ValidationError('Limb alignment requires a shared clock and sparse arm turns')
    sparse={side:{} for side in _SIDES}
    previous=(first,'')
    for row in upper:
        if (type(row) is not dict or set(row) != {'side', 'frame', 'angle_degrees'}
                or row['side'] not in _SIDES or type(row['frame']) is not int
                or not first < row['frame'] < first+count-1
                or type(row['angle_degrees']) not in (float,int)
                or not 0 < abs(row['angle_degrees']) <= _MAX_UPPER_DEGREES):
            raise ValidationError('Limb alignment upper-arm turn is outside its clock or bound')
        order=(row['frame'],row['side'])
        if order <= previous:
            raise ValidationError('Limb alignment upper-arm turns must be increasing and unique')
        previous=order
        sparse[row['side']][row['frame']]=row['angle_degrees']
    for turns in sparse.values():
        for frame,angle in turns.items():
            if any(abs(angle-turns.get(frame+step,0.)) > _MAX_UPPER_STEP for step in (-1,1)):
                raise ValidationError('Limb alignment upper-arm turn has a discontinuous handoff')


def _dot(a, b):
    return sum(x*y for x,y in zip(a,b,strict=True))


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def _sub(a, b):
    return tuple(x-y for x,y in zip(a,b,strict=True))


def _skew(axis):
    x,y,z=axis
    return ((0.,-z,y),(z,0.,-x),(-y,x,0.))


def _around(axis, theta):
    skew=_skew(axis)
    sine,cosine=math.sin(theta),math.cos(theta)
    return [[(i==j)*cosine + skew[i][j]*sine + axis[i]*axis[j]*(1-cosine)
             for j in range(3)] for i in range(3)]


def _shortest_arc(a, b):
    a,b=nm.unit(a),nm.unit(b)
    cosine=max(-1.,min(1.,_dot(a,b)))
    if cosine <= -.999999:
        raise ValidationError('Limb alignment thigh ray has an ambiguous shortest arc')
    skew=_skew(_cross(a,b))
    square=nm.product(skew,skew)
    return [[(i==j)+skew[i][j]+square[i][j]/(1+cosine) for j in range(3)] for i in range(3)]


def _head(pose):
    return (pose[3],pose[7],pose[11])


def _rotate_pose(pose, rotation):
    arm=nm.rows(pose)
    rotated=nm.product(rotation,[row[:3] for row in arm[:3]])
    return [value for i,row in enumerate(rotated) for value in (*row,arm[i][3])]+arm[3]


def _rotate_about_limb_ray(pose, tip, degrees):
    """Turn the measured bone about its head-to-child axis, retaining its origin and scale."""
    axis=nm.unit(_sub(_head(tip),_head(pose)))
    return _rotate_pose(pose,_around(axis,math.radians(degrees)))


def _canonical_thigh(pose, knee, rest_ray, rest_rotation):
    measured=_sub(_head(knee),_head(pose))
    axis=nm.unit(measured)
    desired=nm.product(_shortest_arc(rest_ray,measured),rest_rotation)
    raw=nm.rotation(pose)[0]

    def projected(matrix, column):
        value=[row[column] for row in matrix]
        axial=_dot(value,axis)
        return [v-axial*w for v,w in zip(value,axis,strict=True)]

    candidates=[projected(raw,j) for j in range(3)]
    column=max(range(3),key=lambda j:(math.hypot(*candidates[j]),j))
    a,b=nm.unit(candidates[column]),nm.unit(projected(desired,column))
    delta=math.atan2(_dot(axis,_cross(a,b)),_dot(a,b))
    return _rotate_pose(pose,_around(axis,delta))


def _measured_chains(source, profile):
    bones=source['bones']
    names={bone['name']:i for i,bone in enumerate(bones)}
    parent={bone['name']:bone['parent'] for bone in bones}
    children={}
    for name,owner in parent.items():
        children.setdefault(owner,set()).add(name)
    paired={pair['source']:pair for pair in profile['pairs']}

    def direct_pair(bone, child):
        if (bone not in paired or child not in paired or bone not in names or child not in names
                or parent[child] != bone or children.get(bone) != {child}
                or paired[bone]['source_tip'] != child or paired[bone]['target_tip'] != paired[child]['target']):
            raise ValidationError('Limb alignment requires direct matching measured and mapped chains')
        return names[bone],names[child]

    def declared_landmark(role):
        row=profile['landmarks'][role]
        pair=paired.get(row['source'])
        if pair is None or pair['target'] != row['target']:
            raise ValidationError('Limb alignment landmark disagrees with the matching map')
        return row['source']

    result={}
    channels=set()
    for side in _SIDES:
        hip=declared_landmark(side+'_hip')
        foot=declared_landmark(side+'_foot')
        wrist=declared_landmark(side+'_hand')
        knee,forearm=parent.get(foot),parent.get(wrist)
        upper=parent.get(forearm)
        thigh_i,knee_i=direct_pair(hip,knee)
        _,foot_i=direct_pair(knee,foot)
        upper_i,forearm_i=direct_pair(upper,forearm)
        _,wrist_i=direct_pair(forearm,wrist)
        if parent.get(hip) is not None:
            raise ValidationError('Limb alignment thighs must be direct roots of the measured source legs')
        result[side]=(thigh_i,knee_i,upper_i,forearm_i,wrist_i)
        channels.update((thigh_i,knee_i,foot_i,upper_i,forearm_i,wrist_i))
    if len(channels)!=12:
        raise ValidationError('Limb alignment requires distinct bilateral leg and arm chains')
    return result


def apply_limb_alignment(source: dict, profile: dict) -> dict:
    """Keep every source joint center and all unselected world-pose matrices exact."""
    validate_limb_alignment(profile)
    rule=profile['limb_alignment']
    source_frames=source['frames']
    if (source['first_frame']!=rule['first_frame'] or len(source_frames)!=len(rule['forearm_angle_tenths']['left'])):
        raise ValidationError('Limb alignment schedule does not cover the entire measured source clock')
    chains=_measured_chains(source,profile)
    bones=source['bones']
    rest={}
    for side,(thigh,knee,_,_,_) in chains.items():
        rest[side]=(_sub(bones[knee]['head'],bones[thigh]['head']),nm.rotation(bones[thigh]['matrix'])[0])
    upper={(row['frame'],row['side']):row['angle_degrees'] for row in rule['upper_arm_turns']}
    transformed=[]
    for i,frame in enumerate(source_frames):
        before=frame['poses']
        poses=before[:]
        for side,(thigh,knee,arm,forearm,wrist) in chains.items():
            poses[thigh]=_canonical_thigh(before[thigh],before[knee],*rest[side])
            if angle:=upper.get((frame['frame'],side),0.):
                poses[arm]=_rotate_about_limb_ray(before[arm],before[forearm],angle)
            if roll:=rule['forearm_angle_tenths'][side][i]:
                poses[forearm]=_rotate_about_limb_ray(before[forearm],before[wrist],roll/10.)
        transformed.append({**frame,'poses':poses,'pose_sha256':nm.pose_digest(frame['armature_world'],poses)})
    return {**source,'frames':transformed}
