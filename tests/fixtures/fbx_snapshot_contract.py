"""Non-shipping original synthetic transforms for native FBX boundary tests."""
from copy import deepcopy
from blender_bridge.fbx_source import CONVENTION, IMPORT_OPTIONS, pose_digest

IDENTITY=[1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.,0.,0.,0.,0.,1.]


def snapshot():
    bones=[{"name":"RootA","parent":None,"head":[0.,0.,0.],"tail":[0.,1.,0.],"matrix":IDENTITY[:]},
           {"name":"RootB","parent":None,"head":[0.,0.,0.],"tail":[0.,1.,0.],"matrix":IDENTITY[:]},
           {"name":"Child","parent":"RootA","head":[0.,0.,0.],"tail":[0.,1.,0.],"matrix":IDENTITY[:]}]
    frames=[]
    for frame in range(1,5):
        world=IDENTITY[:]
        world[3]=frame*.01  # Motion exists at the armature object, not just bones.
        poses=[IDENTITY[:] for _ in bones]
        frames.append({"frame":frame,"armature_world":world,"poses":poses,"pose_sha256":pose_digest(world,poses)})
    return {"schema_version":1,"convention":CONVENTION,"source_sha256":"a"*64,"blender_version":"5.3.0",
            "import_options":deepcopy(IMPORT_OPTIONS),"action":"Synthetic original motion","fps":30.,
            "rest_import_options":{**IMPORT_OPTIONS,"use_anim":False},"armature_rest_world":IDENTITY[:],
            "first_frame":1,"last_frame":4,"bones":bones,"frames":frames,
            "retargeting_verified":False,"animation_visual_quality_verified":False,"engine_import_verified":False}


def report(data, payload):
    from hashlib import sha256
    return {"status":"REAL_BLENDER_FBX_SOURCE_SNAPSHOT","convention":CONVENTION,
            "source_sha256":data["source_sha256"],"bone_count":len(data["bones"]),"root_count":2,
            "frame_count":len(data["frames"]),"first_frame":1,"last_frame":4,"fps":30.,
            "action":data["action"],"blender_version":"5.3.0",
            "snapshot":{"name":"source_snapshot.json","bytes":len(payload),"sha256":sha256(payload).hexdigest()},
            "retargeting_verified":False,"animation_visual_quality_verified":False,"engine_import_verified":False}
