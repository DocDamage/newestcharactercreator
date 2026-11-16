"""Real evaluated corner normals paired with unchanged V1 facial geometry."""
from array import array
from hashlib import sha256
from pathlib import Path
import json,math,struct,sys,zlib
from blender_bridge.expression_clip_policy import check_inputs
from blender_bridge.expression_clip_workers import reference
from blender_bridge.expression_clip_action import saved_intake,linear_weight
from blender_bridge.expression_existing import canonical_keys
from blender_bridge.expression_clip_surface import measure_frame
from blender_bridge.expression_geometry import source_state
from blender_bridge.face_operations import state_digest
from blender_bridge.face_policy import digest,read_json
from blender_bridge.skin_material_model import checked_owned_material
from ucc.core.expression_material import POLICY,BASE_FIELDS,NORMAL_FIELDS,validate_normal_job
from ucc.core.skin_material import SkinMaterialSpec

MAGIC=b'UCCNRM1\0';MAX_BYTES=32*1024*1024;FRAME_BYTES=26756*3*12


def corners(bpy,human) -> bytes:
    graph=bpy.context.evaluated_depsgraph_get();obj=human.evaluated_get(graph)
    mesh=obj.to_mesh(preserve_all_data_layers=True,depsgraph=graph)
    try:
        mesh.calc_loop_triangles()
        if len(mesh.vertices)!=13380 or len(mesh.loop_triangles)!=26756:raise ValueError('Normals require complete visible facial skin')
        values=array('f')
        for triangle in mesh.loop_triangles:
            for loop in triangle.loops:
                n=mesh.corner_normals[loop].vector
                if any(not math.isfinite(v) for v in n) or abs(n.length-1.)>1e-4:raise ValueError('Nonfinite or nonunit evaluated corner normal')
                values.extend(n)
        if sys.byteorder!='little':values.byteswap()
        result=values.tobytes()
        if len(result)!=FRAME_BYTES:raise ValueError('Incomplete evaluated triangle-corner normals')
        return result
    finally:obj.to_mesh_clear()


def inputs(bpy,root: Path,job: dict):
    validate_normal_job(job['operation'],job['input_project'],job['options']);options=job['options']
    base={k:options[k] for k in BASE_FIELDS};plan=check_inputs(root,base,verify=True)
    spec=SkinMaterialSpec.from_dict(options['owned_material_spec'])
    context=reference(bpy,root,plan);human=context[0]
    if checked_owned_material(bpy,human)!=spec:raise ValueError('Expression source owned shader differs from the saved material')
    report=read_json(root/'expression_motion.json',base['motion_report_sha256'],4*1024*1024)
    return base,spec,context,report


def frame_samples(bpy,root,context,report,*,saved: bool):
    human,rig,targets,loaded,baseline,neutral,original,values,support,hip=context
    if saved:
        bpy.ops.wm.open_mainfile(filepath=str(root/'expression_motion.blend'),load_ui=False)
        human,rig,_,targets=saved_intake(bpy,values);loaded,_,_,_=canonical_keys(root,human,targets)
        if source_state(bpy,human,rig,targets)!=neutral:raise ValueError('Saved normal scene differs from the original neutral source')
    for frame in range(1,26):
        bpy.context.scene.frame_set(frame)
        if not saved:
            for pair,key in loaded.items():key.value=linear_weight(values[pair],frame)
        bpy.context.view_layer.update()
        _,row=measure_frame(bpy,human,rig,targets,frame,values,loaded,baseline,original,support)
        if row!=report['frames'][frame-1]:raise ValueError('Normal frame no longer matches independently verified V1 geometry')
        yield corners(bpy,human)
    if not saved:
        for key in loaded.values():key.value=0.
    bpy.context.scene.frame_set(1);bpy.context.view_layer.update()
    if source_state(bpy,human,rig,targets)!=neutral:raise ValueError('Normal sampling did not restore exact neutral state')


def stage_normals(bpy,root: Path,job: dict) -> dict:
    base,spec,context,report=inputs(bpy,root,job);binary=root/'expression_normals.bin';manifest=root/'expression_normals.json'
    if binary.exists() or manifest.exists():raise ValueError('Normal stage refuses existing outputs')
    rows=[]
    with binary.open('xb') as stream:
        stream.write(MAGIC)
        for frame,raw in enumerate(frame_samples(bpy,root,context,report,saved=True),1):
            packed=zlib.compress(raw,1);offset=stream.tell()
            if offset+len(packed)>MAX_BYTES:raise ValueError('Complete normal stream exceeds the bound; no cropping')
            stream.write(packed);rows.append({'frame':frame,'offset':offset,'compressed_bytes':len(packed),
                'normal_sha256':sha256(raw).hexdigest(),'triangles_sha256':report['frames'][frame-1]['triangles_sha256'],
                'local_vertices_sha256':report['frames'][frame-1]['local_vertices_sha256']})
    data={'schema_version':1,'policy':POLICY,'bindings':base,'material_spec':spec.to_dict(),
        'coordinate_space':'BLENDER_LOCAL_Z_UP','frame_count':25,'normals_per_frame':80268,'frames':rows,
        'geometry':{'name':binary.name,'sha256':digest(binary),'bytes':binary.stat().st_size},
        'visual_quality_approved':False,'engine_import_verified':False}
    with manifest.open('x',encoding='utf-8') as stream:json.dump(data,stream,allow_nan=False)
    check_inputs(root,base,verify=True)
    return {'schema_version':1,'policy':POLICY,'bindings':base,'owned_material_spec':spec.to_dict(),
        'normals_sha256':digest(binary),'normals_manifest_sha256':digest(manifest),'frame_count':25,
        'visual_quality_approved':False,'engine_import_verified':False}


def verify_normals(bpy,root: Path,job: dict) -> dict:
    base,spec,context,report=inputs(bpy,root,job);options=job['options']
    manifest=read_json(root/'expression_normals.json',options['normals_manifest_sha256'],4*1024*1024)
    path=root/'expression_normals.bin'
    if path.is_symlink() or not path.is_file() or not 8<path.stat().st_size<=MAX_BYTES or digest(path)!=options['normals_sha256']:
        raise ValueError('Normal cache binary is missing, changed or oversized')
    data=path.read_bytes();offset=8;reference_normals=[]
    if data[:8]!=MAGIC or type(manifest.get('frames')) is not list or len(manifest['frames'])!=25:raise ValueError('Normal cache coverage differs')
    for frame,raw in enumerate(frame_samples(bpy,root,context,report,saved=False),1):
        row=manifest['frames'][frame-1];size=row.get('compressed_bytes')
        if type(size) is not int or not 0<size<=len(data)-offset:raise ValueError('Invalid normal chunk bounds')
        decoder=zlib.decompressobj();supplied=decoder.decompress(data[offset:offset+size],FRAME_BYTES+1)
        if supplied!=raw or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError('Cached normals differ from the independent original-source frame')
        expected={'frame':frame,'offset':offset,'compressed_bytes':size,'normal_sha256':sha256(raw).hexdigest(),
            'triangles_sha256':report['frames'][frame-1]['triangles_sha256'],'local_vertices_sha256':report['frames'][frame-1]['local_vertices_sha256']}
        if row!=expected:raise ValueError('Normal frame metadata differs from its exact reference')
        reference_normals.append(raw);offset+=size
    if offset!=len(data):raise ValueError('Normal cache has trailing data or missing frames')
    expected={'schema_version':1,'policy':POLICY,'bindings':base,'material_spec':spec.to_dict(),
        'coordinate_space':'BLENDER_LOCAL_Z_UP','frame_count':25,'normals_per_frame':80268,'frames':manifest['frames'],
        'geometry':{'name':path.name,'sha256':digest(path),'bytes':len(data)},'visual_quality_approved':False,'engine_import_verified':False}
    if state_digest(manifest)!=state_digest(expected):raise ValueError('Normal manifest changed its closed contract')
    # Reopen the saved Action separately; no copied normal data or repairs.
    for index,raw in enumerate(frame_samples(bpy,root,context,report,saved=True)):
        if raw!=reference_normals[index]:raise ValueError('Saved expression normals differ from original-source interpolation')
    if reference_normals[0]!=reference_normals[-1]:raise ValueError('Normal endpoints are not exact neutral restorations')
    check_inputs(root,base,verify=True)
    return {'schema_version':1,'policy':POLICY,'bindings':dict(options),'verified_reopen':True,
        'reference_frames':25,'saved_frames':25,'normal_frames':25,'exact_neutral_endpoints':True,
        'visual_quality_approved':False,'engine_import_verified':False}
