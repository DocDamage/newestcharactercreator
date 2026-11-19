"""Bounded bilateral knee correction with fixed measured foot trajectories."""
import math

from ucc.core.errors import ValidationError

from . import native_math as nm
from .native_skin_policy import CORRECTIVE_POLICIES

_LIMIT = math.radians(148.)
_MAX_LIFT = .11
_MAX_LIFT_STEP = .025
_FLIGHT_LIFT = .13
_FLIGHT_RAMP = .020
_FLIGHT_STEP = .023
_IDENTITY = ((1., 0., 0.), (0., 1., 0.), (0., 0., 1.))


def validate_planted_knee(profile: dict) -> None:
    if 'planted_knee' not in profile:
        return
    cfg = profile['planted_knee']
    if (profile.get('root_motion_policy') != 'SOURCE_HIP_MIDPOINT_V1'
            or profile.get('skin_deformation_policy') not in CORRECTIVE_POLICIES
            or profile.get('mesh_strain_reference') != 'TRUE_NEUTRAL_BIND_V2'):
        raise ValidationError('Planted knee correction requires the hip anchor and both neutral skin references')
    if type(cfg) is not dict or type(cfg.get('schema_version')) is not int or cfg['schema_version'] not in (1,2,3):
        raise ValidationError('Unknown planted knee correction version')
    version = cfg['schema_version']
    keys = {'schema_version','first_frame','frame_count'}
    if version != 3:
        keys.add('source_lift_axis')
    if (set(cfg) != keys or type(cfg['first_frame']) is not int or abs(cfg['first_frame']) > 100_000
            or type(cfg['frame_count']) is not int
            or not 1 <= cfg['frame_count'] <= (24 if version == 2 else 12)):
        raise ValidationError('Planted knee correction requires a short, versioned source window')
    if version == 3:
        return
    axis = cfg['source_lift_axis']
    if (type(axis) is not list or len(axis) != 3
            or any(type(v) not in (int, float) or not -1. <= v <= 1. for v in axis)
            or abs(math.hypot(*axis) - 1.) > 1e-8 or axis[2] < .97):
        raise ValidationError('Planted knee correction requires a unit source lift axis near vertical')


def validate_planted_alignment(profile: dict, axes) -> None:
    if 'planted_knee' in profile and profile['planted_knee']['schema_version'] != 3:
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


def _lift_bounds(chains, axis, max_lift):
    minimum, maximum = 0., max_lift
    for hip,knee,ankle in chains:
        upper, lower = math.dist(hip,knee), math.dist(knee,ankle)
        ray = _sub(hip,ankle)
        height = _dot(ray,axis)
        planar_sq = max(0.,_dot(ray,ray)-height**2)
        closest_sq = upper**2+lower**2+2.*upper*lower*math.cos(_LIMIT)
        farthest_sq = (upper+lower-1e-5)**2
        if height <= 0. or planar_sq >= farthest_sq:
            raise ValidationError('Planted knee joint reach is incompatible with the calibrated lift axis')
        minimum = max(minimum,math.sqrt(max(0.,closest_sq-planar_sq))-height)
        maximum = min(maximum,math.sqrt(farthest_sq-planar_sq)-height)
    if minimum > maximum + 1e-10:
        raise ValidationError('Planted knee correction exceeds the available lift or joint reach')
    return minimum,maximum


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


def _points(row, chains, world):
    poses = row['poses']
    return [tuple(nm.point(world,[poses[i][j] for j in (3,7,11)]) for i in chain) for chain in chains]


def _opening_lifts(frames, chains, axis, count):
    values = [_lift_bounds(_points(row,chains,nm.rows(row['armature_world'])),axis,_MAX_LIFT)[0]
              for row in frames[:count+1]]
    if values[-1] > 1e-8 or values[-2] > _MAX_LIFT_STEP:
        raise ValidationError('Planted knee correction does not join the untouched motion')
    if min(values[:-1]) <= 1e-8 or any(abs(a-b) > _MAX_LIFT_STEP for a,b in zip(values[:-1],values[1:-1])):
        raise ValidationError('Planted knee window contains unneeded or discontinuous lift')
    return values[:-1]


def _flight_lifts(frames, chains, axis, start, end):
    # Two untouched samples at each end let the measured ramp and filter be
    # validated against the original motion on both sides of the correction.
    bounds = [_lift_bounds(_points(row,chains,nm.rows(row['armature_world'])),axis,_FLIGHT_LIFT)
              for row in frames[start-2:end+2]]
    minimum = [lo for lo,_ in bounds]
    if max(minimum) <= 1e-8:
        raise ValidationError('Flight knee correction requires a measured deep bend')
    ramp = minimum[:]
    for i in range(1,len(ramp)):
        ramp[i] = max(ramp[i],ramp[i-1]-_FLIGHT_RAMP)
    for i in range(len(ramp)-2,-1,-1):
        ramp[i] = max(ramp[i],ramp[i+1]-_FLIGHT_RAMP)
    samples = ramp[:]
    weights = (1,2,3,2,1)
    padded = [0.,0.,*ramp,0.,0.]
    for i in range(len(ramp)):
        samples[i] = max(minimum[i],sum(w*v for w,v in zip(weights,padded[i:i+5]))/9.)
    if max(*samples[:2],*samples[-2:]) > 1e-8:
        raise ValidationError('Flight knee correction does not join the untouched motion')
    if (any(lift > high+1e-10 for lift,(_,high) in zip(samples,bounds))
            or any(abs(a-b) > _FLIGHT_STEP for a,b in zip(samples,samples[1:]))):
        raise ValidationError('Flight knee correction exceeds the measured reach or lift rate')
    return samples[2:-2]


_ZERO_SHIFT = (0.,0.,0.)


def _closest_intersection(left, right):
    a, ra = left
    b, rb = right
    line = _sub(b,a)
    distance = math.hypot(*line)
    if distance < 1e-12 or not abs(ra-rb)-1e-10 <= distance <= ra+rb+1e-10:
        return None
    normal = _scale(line,1./distance)
    section = (ra**2-rb**2+distance**2)/(2.*distance)
    center = _add(a,_scale(normal,section))
    circle_radius = math.sqrt(max(0.,ra**2-section**2))
    toward_origin = _scale(_sub(center,_scale(normal,_dot(center,normal))),-1.)
    if math.hypot(*toward_origin) < 1e-12:
        return center if circle_radius < 1e-10 else None
    return _add(center,_scale(nm.unit(toward_origin),circle_radius))


def _minimum_folded_shift(chains):
    constraints = []
    for hip,knee,ankle in chains:
        length_a,length_b = math.dist(hip,knee),math.dist(knee,ankle)
        minimum = math.sqrt(length_a**2+length_b**2+2.*length_a*length_b*math.cos(_LIMIT))
        constraints.append((_sub(ankle,hip),minimum,length_a+length_b))

    def feasible(point):
        return all(lo-1e-10 <= math.dist(point,center) <= hi+1e-10 for center,lo,hi in constraints)

    if feasible(_ZERO_SHIFT):
        return _ZERO_SHIFT
    spheres = [[(center,lo),(center,hi)] for center,lo,hi in constraints]
    options = []
    for pair in spheres:
        for center,radius in pair:
            distance = math.hypot(*center)
            if distance > 1e-12:
                options.append(_scale(center,1.-radius/distance))
    for left in spheres[0]:
        for right in spheres[1]:
            point = _closest_intersection(left,right)
            if point is not None:
                options.append(point)
    retained = [point for point in options if feasible(point)]
    if not retained:
        raise ValidationError('Folded knee correction has no unambiguous common reach')
    return min(retained,key=lambda point:math.hypot(*point))


def _folded_shifts(frames, chains, start, end):
    shifts = [_minimum_folded_shift(_points(row,chains,nm.rows(row['armature_world'])))
              for row in frames[start-1:end+1]]
    if shifts[0] != _ZERO_SHIFT or shifts[-1] != _ZERO_SHIFT:
        raise ValidationError('Folded knee correction does not join the untouched motion')
    if (max(math.hypot(*shift) for shift in shifts) > .075
            or any(math.dist(a,b) > .036 for a,b in zip(shifts,shifts[1:]))
            or _ZERO_SHIFT in shifts[1:-1]):
        raise ValidationError('Folded knee correction exceeds its measured displacement window')
    return shifts[1:-1]


def apply_planted_knee(source: dict, profile: dict) -> dict:
    cfg = profile['planted_knee']
    frames = source['frames'][:]
    start = cfg['first_frame']-source['first_frame']
    end = start+cfg['frame_count']
    version = cfg['schema_version']
    if version == 1 and (start != 0 or end >= len(frames)):
        raise ValidationError('Planted knee correction needs the measured opening and a handoff sample')
    if version == 2 and not 2 <= start < end <= len(frames)-2:
        raise ValidationError('Flight knee correction needs both measured handoffs')
    if version == 3 and not 1 <= start < end < len(frames):
        raise ValidationError('Folded knee correction needs both measured handoffs')
    chains,feet = _chain_indices(source,profile)
    if version == 3:
        shifts = _folded_shifts(frames,chains,start,end)
    else:
        axis = cfg['source_lift_axis']
        values = (_opening_lifts(frames,chains,axis,end) if version == 1
                  else _flight_lifts(frames,chains,axis,start,end))
        shifts = [_scale(axis,lift) for lift in values]
    for index,shift in enumerate(shifts,start):
        if math.hypot(*shift) <= 1e-10:
            continue
        row = frames[index]
        world = nm.rows(row['armature_world'])
        poses = row['poses']
        points = _points(row,chains,world)
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
