"""Bounded bilateral knee correction with fixed measured foot trajectories."""
import math

from ucc.core.errors import ValidationError

from . import native_math as nm
from .native_skin_policy import CORRECTIVE_POLICIES

_LIMIT = math.radians(148.)
_MAX_LIFT = .11
_MAX_LIFT_STEP = .025
_IDENTITY = ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.))


def validate_planted_knee(profile: dict) -> None:
    if 'planted_knee' not in profile:
        return
    cfg = profile['planted_knee']
    if (profile.get('root_motion_policy') != 'SOURCE_HIP_MIDPOINT_V1'
            or profile.get('skin_deformation_policy') not in CORRECTIVE_POLICIES
            or profile.get('mesh_strain_reference') != 'TRUE_NEUTRAL_BIND_V2'):
        raise ValidationError('Planted knee correction requires the hip anchor and both neutral skin references')
    if (type(cfg) is not dict or set(cfg) != {'schema_version','first_frame','frame_count','source_lift_axis'}
            or type(cfg['schema_version']) is not int or cfg['schema_version'] != 1
            or type(cfg['first_frame']) is not int or abs(cfg['first_frame']) > 100_000
            or type(cfg['frame_count']) is not int or not 1 <= cfg['frame_count'] <= 12):
        raise ValidationError('Planted knee correction requires a short, versioned opening window')
    axis = cfg['source_lift_axis']
    if (type(axis) is not list or len(axis) != 3
            or any(type(v) not in (int, float) or not -1. <= v <= 1. for v in axis)
            or abs(math.hypot(*axis) - 1.) > 1e-8 or axis[2] < .97):
        raise ValidationError('Planted knee correction requires a unit source lift axis near vertical')


def validate_planted_alignment(profile: dict, axes) -> None:
    if 'planted_knee' in profile:
        axis = profile['planted_knee']['source_lift_axis']
        projected = [_dot(row, axis) for row in axes]
        if math.dist(projected, (0., 0., 1.)) > 1e-6:
            raise ValidationError('Source lift axis differs from calibrated target vertical')


def _dot(a, b):
    return math.fsum(x*y for x,y in zip(a,b))


def _sub(a, b):
    return tuple(x-y for x,y in zip(a,b))


def _add(a, b):
    return tuple(x+y for x,y in zip(a,b))


def _scale(a, factor):
    return tuple(x*factor for x in a)


def _mv(matrix, vector):
    return tuple(_dot(row, vector) for row in matrix)


def _turn(a, b):
    old, new = nm.unit(a), nm.unit(b)
    x, y, z = (old[1]*new[2]-old[2]*new[1], old[2]*new[0]-old[0]*new[2], old[0]*new[1]-old[1]*new[0])
    c = _dot(old,new)
    if c <= -.9999:
        raise ValidationError('Planted knee bend reversal is ambiguous')
    skew = ((0.,-z,y),(z,0.,-x),(-y,x,0.))
    square = nm.product(skew,skew)
    return [[_IDENTITY[i][j]+skew[i][j]+square[i][j]/(1.+c) for j in range(3)] for i in range(3)]


def _align(pose, world, inverse_world, old_ray, new_ray, new_head):
    world_pose = nm.product(world,nm.rows(pose))
    rotation = nm.product(_turn(old_ray,new_ray),[row[:3] for row in world_pose[:3]])
    corrected = [row+[new_head[i]] for i,row in enumerate(rotation)]+[[0.,0.,0.,1.]]
    return [v for row in nm.product(inverse_world,corrected) for v in row]


def _chain_indices(source, profile):
    names = {bone['name']:i for i,bone in enumerate(source['bones'])}
    parent = {bone['name']:bone['parent'] for bone in source['bones']}
    mapped = {pair['source'] for pair in profile['pairs']}
    chains, feet = [], set()
    for side in ('left','right'):
        hip = profile['landmarks'][side+'_hip']['source']
        foot = profile['landmarks'][side+'_foot']['source']
        knee = parent.get(foot)
        if (hip not in names or foot not in names or knee not in mapped or parent.get(hip) is not None
                or parent.get(knee) != hip or {name for name,p in parent.items() if p == hip} != {knee}
                or {name for name,p in parent.items() if p == knee} != {foot}):
            raise ValidationError('Planted knee correction requires two mapped direct hip-knee-foot chains')
        subtree = {foot}
        for name, owner in parent.items():
            if owner in subtree:
                subtree.add(name)
        if len(subtree) < 2 or feet & subtree:
            raise ValidationError('Planted knee correction requires distinct measured foot and toe branches')
        feet.update(subtree)
        chains.append(tuple(names[name] for name in (hip,knee,foot)))
    return chains,tuple(sorted(names[name] for name in feet))


def _required_lift(chains, axis):
    minimum, maximum = 0., _MAX_LIFT
    for hip,knee,ankle in chains:
        upper, lower = math.dist(hip,knee), math.dist(knee,ankle)
        ray = _sub(hip,ankle)
        height = _dot(ray,axis)
        planar_sq = max(0.,_dot(ray,ray)-height**2)
        closest_sq = upper**2+lower**2+2.*upper*lower*math.cos(_LIMIT)
        farthest_sq = (upper+lower-1e-5)**2
        if height <= 0. or planar_sq >= farthest_sq:
            raise ValidationError('Planted knee joint reach is incompatible with the opening contact')
        minimum = max(minimum,math.sqrt(max(0.,closest_sq-planar_sq))-height)
        maximum = min(maximum,math.sqrt(farthest_sq-planar_sq)-height)
    if minimum > maximum + 1e-10:
        raise ValidationError('Planted knee correction exceeds the available lift or joint reach')
    return minimum


def _solve_knee(hip,knee,ankle,shift):
    next_hip = _add(hip,shift)
    old_ray, ray = _sub(ankle,hip), _sub(ankle,next_hip)
    old_axis, axis = nm.unit(old_ray), nm.unit(ray)
    knee_ray = _sub(knee,hip)
    radial = _sub(knee_ray,_scale(old_axis,_dot(knee_ray,old_axis)))
    direction = nm.unit(_mv(_turn(old_ray,ray),radial))
    upper,lower,distance = math.dist(hip,knee),math.dist(knee,ankle),math.hypot(*ray)
    section = (upper**2-lower**2+distance**2)/(2.*distance)
    knee_next = _add(_add(next_hip,_scale(axis,section)),_scale(direction,math.sqrt(max(0.,upper**2-section**2))))
    if max(abs(math.dist(next_hip,knee_next)-upper),abs(math.dist(knee_next,ankle)-lower)) > 1e-8:
        raise ValidationError('Planted knee solve did not preserve measured leg lengths')
    return next_hip,knee_next


def apply_planted_knee(source: dict, profile: dict) -> dict:
    cfg = profile['planted_knee']
    count = cfg['frame_count']
    if cfg['first_frame'] != source['first_frame'] or count >= len(source['frames']):
        raise ValidationError('Planted knee correction needs the measured opening and a handoff sample')
    chains,feet = _chain_indices(source,profile)
    axis = cfg['source_lift_axis']
    frames = source['frames'][:]
    previous = None
    for index,row in enumerate(frames[:count+1]):
        world = nm.rows(row['armature_world'])
        poses = row['poses']
        points = [tuple(nm.point(world,[poses[i][j] for j in (3,7,11)]) for i in chain) for chain in chains]
        lift = _required_lift(points,axis)
        if index == count:
            if lift > 1e-8 or previous > _MAX_LIFT_STEP:
                raise ValidationError('Planted knee correction does not join the untouched motion')
            break
        if lift <= 1e-8 or (previous is not None and abs(lift-previous) > _MAX_LIFT_STEP):
            raise ValidationError('Planted knee window contains unneeded or discontinuous lift')
        previous = lift
        shift = _scale(axis,lift)
        lifted_world = [row[:] for row in world]
        for i in range(3):
            lifted_world[i][3] += shift[i]
        inverse_world = nm.inverse(lifted_world)
        local_shift = _mv([row[:3] for row in inverse_world[:3]],shift)
        corrected = poses[:]
        for foot in feet:
            pose = poses[foot][:]
            for component,j in enumerate((3,7,11)):
                pose[j] -= local_shift[component]
            corrected[foot] = pose
        for (h,k,_),(hip,knee,ankle) in zip(chains,points):
            next_hip,next_knee = _solve_knee(hip,knee,ankle,shift)
            corrected[h] = _align(poses[h],world,inverse_world,_sub(knee,hip),_sub(next_knee,next_hip),next_hip)
            corrected[k] = _align(poses[k],world,inverse_world,_sub(ankle,knee),_sub(ankle,next_knee),next_knee)
        world_values = [v for row in lifted_world for v in row]
        frames[index] = {**row,'armature_world':world_values,'poses':corrected,
                         'pose_sha256':nm.pose_digest(world_values,corrected)}
    return {**source,'frames':frames}
