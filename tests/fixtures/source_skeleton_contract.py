"""Nonshipping analytical transforms, never a character or native FBX proof."""
from copy import deepcopy

from fixtures.fbx_snapshot_contract import IDENTITY, snapshot
from blender_bridge.fbx_source import pose_digest


def analytical_source_snapshot(first=11, count=4):
    data = snapshot()
    # Rest bone Y points along world Z; tail cannot be guessed from pose head.
    rest = [1.,0.,0.,2., 0.,0.,-1.,3., 0.,1.,0.,4., 0.,0.,0.,1.]
    data['bones'][0].update(matrix=rest,head=[2.,3.,4.],tail=[2.,3.,6.])
    child = IDENTITY[:];child[7]=1.
    data['bones'][2].update(matrix=child,head=[0.,1.,0.],tail=[0.,2.,0.])
    data.update(first_frame=first,last_frame=first+count-1,frames=[])
    for index in range(count):
        world = [0.,-1.,0.,100.+index, 1.,0.,0.,200., 0.,0.,1.,300., 0.,0.,0.,1.]
        pose = [0.,-1.,0.,7., 1.,0.,0.,8., 0.,0.,1.,9., 0.,0.,0.,1.]
        child_pose = IDENTITY[:];child_pose[7]=5.
        poses = [pose,IDENTITY[:],child_pose]
        data['frames'].append({'frame':first+index,'armature_world':world,
            'poses':deepcopy(poses),'pose_sha256':pose_digest(world,poses)})
    return data
