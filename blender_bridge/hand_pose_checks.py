"""Transient full-skin pose, shading and potential-overlap observations."""
from array import array
from hashlib import sha256
import math

from blender_bridge.face_geometry import evaluated,points_digest
from blender_bridge.hand_master import observe_master
from blender_bridge.hand_policy import state_digest


def _surface(bpy,human):
    bpy.context.view_layer.update()
    obj=human.evaluated_get(bpy.context.evaluated_depsgraph_get());mesh=obj.to_mesh()
    try:
        points=[tuple(human.matrix_world@v.co) for v in mesh.vertices]
        normals=array('f',(x for n in mesh.corner_normals for x in n.vector))
        if len(points) != 13380 or not all(math.isfinite(v) for v in normals):
            raise ValueError('Hand pose produced an incomplete/nonfinite real surface')
        return points,sha256(normals.tobytes()).hexdigest()
    finally:obj.to_mesh_clear()


def _overlap_observations(bpy,human,region):
    from mathutils.bvhtree import BVHTree
    points=evaluated(bpy,human,full=True)
    hand=[p['vertices'] for p in region['polygons']];ids=set(region['ids'])
    body=[vertices for _,vertices in region['skin_polygons'] if not any(i in ids for i in vertices)]
    hand_tree=BVHTree.FromPolygons(points,hand,all_triangles=False,epsilon=0.)
    body_tree=BVHTree.FromPolygons(points,body,all_triangles=False,epsilon=0.)
    external=len(hand_tree.overlap(body_tree))
    internal=sum(a<b and not set(hand[a])&set(hand[b]) for a,b in hand_tree.overlap(hand_tree))
    return {'potential_hand_body_overlaps':external,'potential_hand_self_overlaps':internal}


def pose_observations(bpy,human,rig,targets,region):
    from mathutils import Quaternion
    initial_state=state_digest(observe_master(bpy,human,rig,targets))
    baseline,_=_surface(bpy,human);records=[]
    for name,axes in [('wrist.L',(0,1,2)),*[(f'finger{i}-1.L',(0,)) for i in range(1,6)],
                      ('finger2-2.L',(0,)),('finger5-2.L',(0,))]:
        for axis in axes:
            for angle in (-20,20):
                bone=rig.pose.bones[name];mode=bone.rotation_mode
                q,e,aa=bone.rotation_quaternion.copy(),bone.rotation_euler.copy(),tuple(bone.rotation_axis_angle)
                try:
                    vector=[0.,0.,0.];vector[axis]=1.
                    bone.rotation_mode='QUATERNION';bone.rotation_quaternion=Quaternion(vector,math.radians(angle))
                    actual,normals=_surface(bpy,human)
                    distances=[math.dist(a,b) for a,b in zip(baseline,actual)]
                    moved=sum(v>1e-6 for v in distances)
                    if moved<16 or not 1e-6<max(distances)<.5:
                        raise ValueError('Installed hand fails meaningful bounded full-skin deformation')
                    records.append({'bone':name,'axis':axis,'degrees':angle,
                                    'skin_sha256':points_digest(actual),'normals_sha256':normals,
                                    'moved_vertices_over_1um':moved,'maximum_displacement':max(distances),
                                    **_overlap_observations(bpy,human,region)})
                finally:
                    bone.rotation_quaternion=q;bone.rotation_euler=e;bone.rotation_axis_angle=aa
                    bone.rotation_mode=mode;bpy.context.view_layer.update()
                if state_digest(observe_master(bpy,human,rig,targets)) != initial_state:
                    raise ValueError('Hand pose check failed exact source/key/skin/rig restoration')
    if len(records) != 20:
        raise ValueError('Installed hand pose coverage is incomplete')
    return records
