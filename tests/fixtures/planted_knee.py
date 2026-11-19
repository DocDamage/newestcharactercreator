"""Synthetic two-bone chains exercising only the pure preview solver."""
from ucc.animations.native_math import pose_digest


def _matrix(x, y, z):
    return [1.,0.,0.,x, 0.,1.,0.,y, 0.,0.,1.,z, 0.,0.,0.,1.]


def planted_knee_case():
    bones, pairs, landmarks = [], [], {}
    for side in ('left','right'):
        parent = None
        for joint in ('hip','knee','foot','toe'):
            name = side+'_'+joint
            bones.append({'name':name,'parent':parent})
            pairs.append({'source':name})
            if joint in ('hip','foot'):
                landmarks[name] = {'source':name}
            parent = name
    frames = []
    for frame,height in ((7,.22),(8,.25),(9,.26)):
        world = _matrix(.03*frame,0.,0.)
        poses = []
        for side in (-.2,.2):
            poses.extend(_matrix(side,y,z) for y,z in ((0.,height),(.4,height/2.),(0.,0.),(-.15,0.)))
        frames.append({'frame':frame,'armature_world':world,'poses':poses,'pose_sha256':pose_digest(world,poses)})
    profile = {
        'root_motion_policy':'SOURCE_HIP_MIDPOINT_V1',
        'skin_deformation_policy':'BOUND_CORRECTIVE_SMOOTH_V1',
        'mesh_strain_reference':'TRUE_NEUTRAL_BIND_V2',
        'landmarks':landmarks,'pairs':pairs,
        'planted_knee':{'schema_version':1,'first_frame':7,'frame_count':1,'source_lift_axis':[0.,0.,1.]},
    }
    return {'bones':bones,'first_frame':7,'frames':frames},profile
