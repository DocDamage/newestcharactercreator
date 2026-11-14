"""Fresh-process reproduction of complete surface review and triangle topology."""
from hashlib import sha256
from array import array
import sys
from blender_bridge.native_review_reopen import reopen_native,scene_objects,digest
from blender_bridge.native_inputs import read_json,validate_profile
from blender_bridge.native_surface_review import SurfaceInspector


def verify_surface_review(bpy,root,options: dict) -> dict:
    base={k:v for k,v in options.items() if k!="surface_review_sha256"}
    reopened=reopen_native(bpy,root,base)
    expected=read_json(root/"motion_contacts.json",options["surface_review_sha256"],16*1024*1024)
    profile=validate_profile(read_json(root/"native_mapping.json",base["mapping_sha256"],64*1024),
        base["source_sha256"],base["snapshot_sha256"],base["master_sha256"])
    data=read_json(root/"target_timeline.json",base["timeline_sha256"],64*1024*1024)
    human,rig=scene_objects(bpy);inspector=SurfaceInspector(profile,rig,human)
    for frame,row in enumerate(data["full_timeline_frames"],1):
        bpy.context.scene.frame_set(frame);graph=bpy.context.evaluated_depsgraph_get()
        evaluated=human.evaluated_get(graph);mesh=evaluated.to_mesh(preserve_all_data_layers=True,depsgraph=graph)
        try:
            mesh.calc_loop_triangles()
            vertices=array('f',[0.])*(len(mesh.vertices)*3);mesh.vertices.foreach_get('co',vertices)
            import struct
            skin=sha256()
            for i in range(0,len(vertices),3):skin.update(struct.pack('<qqq',*(round(v*1000000) for v in vertices[i:i+3])))
            if skin.hexdigest()!=row["evaluated_sha256"]:raise ValueError("Surface verification skin differs from bound timeline")
            indices=array('I',[0])*(len(mesh.loop_triangles)*3);mesh.loop_triangles.foreach_get('vertices',indices)
            if sys.byteorder!='little':indices.byteswap()
            inspector.inspect(mesh,frame,row["evaluated_sha256"],sha256(indices.tobytes()).hexdigest())
        finally:evaluated.to_mesh_clear()
    actual=inspector.report(base)
    if actual!=expected:raise ValueError("Fresh saved-scene surface review/topology differs")
    if digest(root/"motion_contacts.json")!=options["surface_review_sha256"]:raise ValueError("Surface review changed during verification")
    return {"status":"REAL_NATIVE_SURFACE_REVIEW_VERIFIED","bindings":dict(options),"frames_verified":len(inspector.rows),
            "saved_review_verification":reopened,"world_matrix":[float(v) for line in human.matrix_world for v in line],
            "originals_unchanged":True,"contact_quality_verified":False}
