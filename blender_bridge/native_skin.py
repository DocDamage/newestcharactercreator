"""Independent per-target skin response before native source Action creation."""
import math
from blender_bridge.pose_deformation import _evaluated_vertices,_movement


def probe_targets(bpy,human,rig,pairs,neutral,neutral_sha):
    from mathutils import Quaternion
    results=[]
    for row in pairs[1:]:
        bone=rig.pose.bones[row["target"]]
        if not bone.bone.use_deform:
            raise ValueError("Native mapped body target must be an actual deform bone: "+bone.name)
        basis,mode=bone.matrix_basis.copy(),bone.rotation_mode
        try:
            bone.rotation_mode="QUATERNION"
            result=None
            for axis,vector in (("X",(1,0,0)),("Y",(0,1,0)),("Z",(0,0,1))):
                bone.rotation_quaternion=Quaternion(vector,math.radians(12))
                points,_=_evaluated_vertices(bpy,human)
                moved,distance=_movement(neutral,points)
                if moved>=16 and distance>1e-6:
                    result={"source":row["source"],"target":row["target"],"axis":axis,
                            "moved_vertices":moved,"max_displacement_local":distance}
                    break
            if result is None:raise ValueError("Mapped native target did not move actual weighted skin: "+bone.name)
            results.append(result)
        finally:
            bone.rotation_mode=mode;bone.matrix_basis=basis
            if _evaluated_vertices(bpy,human)[1]!=neutral_sha:
                raise ValueError("Native independent skin probe did not restore neutral geometry")
    return results
