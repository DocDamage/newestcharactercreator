"""Blender-only independent local hand correction intake and quaternion solve."""
import math

POLICY='BOUNDED_NATIVE_ARM_HAND_IK_V2'


def rotations(rows: list[dict],fps: float) -> list[tuple[float,float,float]]:
    result=[]
    for row in rows:
        v=row.get('hand_rotation_local_degrees')
        if (type(v) is not list or len(v)!=3 or
            any(type(x) not in (int,float) or not -15.<=x<=15. for x in v) or math.hypot(*v)>15.+1e-12):
            raise ValueError('Hand rotation exceeds finite local 15-degree bound')
        result.append(tuple(v))
    if result[0]!=(0.,0.,0.) or result[-1]!=(0.,0.,0.) or not any(math.hypot(*v)>1e-7 for v in result):
        raise ValueError('Hand rotation requires fixed endpoints and nonzero correction')
    velocity=[(0.,0.,0.)]+[tuple((b[i]-a[i])*fps for i in range(3)) for a,b in zip(result,result[1:])]+[(0.,0.,0.)]
    if (any(math.hypot(*v)>90.+1e-9 for v in velocity) or
        any(math.hypot(*(b[i]-a[i] for i in range(3)))*fps>900.+1e-9 for a,b in zip(velocity,velocity[1:]))):
        raise ValueError('Hand rotation exceeds local speed/acceleration bounds')
    return result


def orient(plan: dict,matrices: dict,frame: int) -> dict:
    from mathutils import Matrix,Quaternion,Vector
    vector=Vector(plan['hand_rotations'][frame-1]);degrees=vector.length
    if degrees==0.:return matrices
    hand=matrices[plan['chain'][2]];pivot=hand.translation.copy()
    axis=hand.to_quaternion()@(vector/degrees)
    delta=Quaternion(axis,math.radians(degrees))
    transform=Matrix.Translation(pivot)@delta.to_matrix().to_4x4()@Matrix.Translation(-pivot)
    for name in plan['descendants']:matrices[name]=transform@matrices[name]
    return matrices


def changed(plan: dict,frame: int) -> bool:
    if 'active_frames' in plan:return plan['active_frames'][frame-1]
    return any(plan['offsets'][frame-1]) or bool(plan.get('hand_rotations') and any(plan['hand_rotations'][frame-1]))


def angular_bones(plan: dict) -> tuple[str,...]:
    if 'active_frames' in plan:
        return tuple(n for s in ('left','right') for n in (*plan[s]['chain'],plan[s]['clavicle']))
    return plan['chain'] if plan.get('hand_rotations') else plan['chain'][:2]
