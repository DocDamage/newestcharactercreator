"""Actual source-driven corrective inversion probe; no shipping candidate."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

import bpy
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from blender_bridge.godot_bind_mesh import build_godot_bind_mesh
from blender_bridge.godot_skin_weights import normalize_weights
from blender_bridge.face_geometry import evaluated
from blender_bridge.native_corrective import NAME, SETTINGS


def float_transform(matrices, points):
    """Explicit single-precision affine arithmetic, preserving term order."""
    matrix=np.asarray(matrices,dtype=np.float32);point=np.asarray(points,dtype=np.float32)
    if matrix.ndim==2:matrix=np.broadcast_to(matrix,(len(point),4,4))
    value=matrix[:,:3,0]*point[:,0,None]
    value=value+matrix[:,:3,1]*point[:,1,None]
    value=value+matrix[:,:3,2]*point[:,2,None]
    return value+matrix[:,:3,3]


def float_delta_skin(points,deformation,bone_ids,raw_weights,to_rig,to_mesh,world):
    """Numerical diagnostic of linear weighted displacement accumulation."""
    co=float_transform(to_rig,points)
    delta=np.zeros_like(co);total=np.zeros(len(co),dtype=np.float32)
    for slot in range(8):
        weight=raw_weights[:,slot].astype(np.float32)
        transformed=float_transform(deformation[bone_ids[:,slot]],co)
        delta=delta+(transformed-co)*weight[:,None]
        total=total+weight
    value=co+delta*(np.float32(1.)/total)[:,None]
    return float_transform(world,float_transform(to_mesh,value))


def mathutils_delta_skin(points,deformation,bone_ids,raw_weights,to_rig,to_mesh,world):
    from mathutils import Matrix,Vector
    bone_matrices=[Matrix(rows.tolist()) for rows in deformation]
    begin=Matrix(to_rig.tolist());end=Matrix(to_mesh.tolist());world=Matrix(world.tolist())
    result=[]
    for point,indices,weights in zip(points,bone_ids,raw_weights):
        co=begin@Vector(point.tolist());delta=Vector((0.,0.,0.));total=np.float32(0.)
        for index,weight in zip(indices,weights):
            if weight:
                delta+=(bone_matrices[index]@co-co)*float(weight)
                total=np.float32(total+np.float32(weight))
        value=co+delta*float(np.float32(1.)/total)
        result.append(tuple(world@(end@value)))
    return np.array(result,dtype=np.float64)


def run(job: Path, output: Path, matrix_policy: str, first_frame: int, last_frame: int) -> dict:
    if not 1<=first_frame<=last_frame<=300:raise ValueError('Invalid explicit diagnostic frame window')
    output.mkdir(exist_ok=False)
    paths=[job/'candidate.blend',job/'review_motion.blend',job/'target_timeline.json']
    before={str(path):sha256(path.read_bytes()).hexdigest() for path in paths}
    timeline=json.loads(paths[2].read_text())
    if timeline['source_frame_count']!=300 or timeline['fps']!=30. or timeline['skin_deformation_policy']!='BOUND_CORRECTIVE_SMOOTH_V1':
        raise ValueError('Probe needs the exact independently verified native300 source')
    bpy.ops.wm.open_mainfile(filepath=str(paths[0]),load_ui=False)
    human=bpy.data.objects['Human'];rig=bpy.data.objects['Human.rig']
    candidate=build_godot_bind_mesh(bpy,human,rig)
    base=np.array([tuple(vertex.co) for vertex in candidate.object.data.vertices],dtype=np.float64)
    ids=candidate.source_vertex_ids
    names=[bone.name for bone in rig.data.bones];index={name:i for i,name in enumerate(names)}
    deform={bone.name for bone in rig.data.bones if bone.use_deform}
    groups={group.index:group.name for group in human.vertex_groups}
    bone_ids=np.zeros((len(ids),8),dtype=np.int32);weights=np.zeros((len(ids),8),dtype=np.float64)
    raw_weights=np.zeros_like(weights)
    for i,source_id in enumerate(ids):
        normalized,_=normalize_weights(tuple((groups[row.group],float(row.weight))
            for row in human.data.vertices[source_id].groups if groups[row.group] in deform))
        for j,(name,weight) in enumerate(normalized):bone_ids[i,j]=index[name];weights[i,j]=weight
        for j,row in enumerate([row for row in human.data.vertices[source_id].groups if groups[row.group] in deform and row.weight>0]):
            raw_weights[i,j]=float(row.weight)
    rest_inverse=np.linalg.inv(np.array([list(map(list,bone.matrix_local)) for bone in rig.data.bones],dtype=np.float64))
    base4=np.column_stack((base,np.ones(len(base))))
    bpy.ops.wm.open_mainfile(filepath=str(paths[1]),load_ui=False)
    human=bpy.data.objects['Human'];rig=bpy.data.objects['Human.rig'];modifier=human.modifiers.get(NAME)
    if modifier is None or not modifier.is_bind or any(getattr(modifier,name)!=value for name,value in SETTINGS.items()):
        raise ValueError('Probe lost actual bound corrective settings')
    if names!=[bone.name for bone in rig.data.bones] or human.modifiers[0].use_deform_preserve_volume:
        raise ValueError('Probe cannot silently reinterpret another rig or dual-quaternion policy')
    actual_candidate=actual_raw=corrective_key=None
    if matrix_policy=='actual_blender_candidate':
        # Explicit private references only. The original source keeps its
        # bound corrective modifier throughout corrected evaluation.
        donor=human.copy();donor.data=human.data.copy();bpy.context.scene.collection.objects.link(donor)
        donor.modifiers.remove(donor.modifiers[NAME])
        staged=build_godot_bind_mesh(bpy,donor,rig)
        actual_candidate=staged.object
        if staged.source_vertex_ids!=ids or not np.array_equal(np.array([tuple(v.co) for v in actual_candidate.data.vertices]),base):
            raise ValueError('Native private reference changed exact master bind correspondence')
        donor_mesh=donor.data;bpy.data.objects.remove(donor,do_unlink=True);bpy.data.meshes.remove(donor_mesh)
        actual_raw=actual_candidate.copy();actual_raw.data=actual_candidate.data.copy()
        bpy.context.scene.collection.objects.link(actual_raw)
        for i,indices in enumerate(bone_ids):
            for slot,index in enumerate(indices):
                if raw_weights[i,slot]>0:
                    actual_raw.vertex_groups[names[index]].add([i],float(raw_weights[i,slot]),'REPLACE')
        corrective_key=actual_candidate.shape_key_add(name='UCC_POSE_CORRECTION_NUMERIC_REFERENCE',from_mix=False)
        corrective_key.value=1.
        serialized=np.zeros_like(weights)
        for i,vertex in enumerate(actual_candidate.data.vertices):
            memberships={actual_candidate.vertex_groups[row.group].name:float(row.weight) for row in vertex.groups}
            values=[memberships.get(names[index],0.) if raw_weights[i,slot]>0 else 0. for slot,index in enumerate(bone_ids[i])]
            serialized[i]=np.array(values)/sum(values)
    maxima={'raw_lbs_error_m':0.,'corrected_reconstruction_error_m':0.,'required_correction_world_m':0.,'rest_space_delta_m':0.}
    rows=[];minimum_det=1.;maximum_condition=1.
    with (output/'corrective_targets_blender_local.f32').open('xb') as targets, (output/'source_corrected_blender_world.f32').open('xb') as positions:
        for frame in range(first_frame,last_frame+1):
            bpy.context.scene.frame_set(frame);bpy.context.view_layer.update()
            corrected=np.array(evaluated(bpy,human),dtype=np.float64)
            try:
                modifier.show_viewport=False;bpy.context.view_layer.update()
                raw=np.array(evaluated(bpy,human),dtype=np.float64)
            finally:
                modifier.show_viewport=True;bpy.context.view_layer.update()
            if corrected.shape!=(13380,3) or raw.shape!=corrected.shape:
                raise ValueError('Corrective source changed full visible topology')
            mesh_world=np.array(list(map(list,human.matrix_world)),dtype=np.float64)
            rig_world=np.array(list(map(list,rig.matrix_world)),dtype=np.float64)
            to_rig=np.linalg.inv(rig_world)@mesh_world
            posed=np.array([list(map(list,rig.pose.bones[name].matrix)) for name in names],dtype=np.float64)
            if matrix_policy!='ideal_rest':
                deformation=np.array([list(map(list,rig.pose.bones[name].matrix_channel)) for name in names],dtype=np.float64)
                if frame==1:
                    print('DIRECT_CHANNEL_DESCRIPTION',rig.pose.bones[0].bl_rna.properties['matrix_channel'].description,flush=True)
                    print('DIRECT_CHANNEL_IDEAL_MAX_DIFFERENCE',float(np.max(np.abs(deformation-posed@rest_inverse))),flush=True)
            else:
                deformation=posed@rest_inverse
            bone_matrices=np.linalg.inv(to_rig)[None,:,:]@deformation@to_rig[None,:,:]
            inverse_weights=serialized if actual_candidate is not None else weights
            matrices=np.sum(bone_matrices[bone_ids]*inverse_weights[:,:,None,None],axis=1)
            determinant=np.linalg.det(matrices[:,:3,:3]);conditions=np.linalg.cond(matrices[:,:3,:3])
            if not np.all(np.isfinite(conditions)) or np.min(np.abs(determinant))<1e-8 or np.max(conditions)>1e6:
                raise ValueError('Source skin needs a separately admitted singular inverse policy')
            minimum_det=min(minimum_det,float(np.min(np.abs(determinant))))
            maximum_condition=max(maximum_condition,float(np.max(conditions)))
            predicted=(np.einsum('nij,nj->ni',matrices,base4)@mesh_world.T)[:,:3]
            if actual_raw is not None:
                predicted=np.array(evaluated(bpy,actual_raw),dtype=np.float64)
            if matrix_policy in {'blender_float_delta','mathutils_float_delta'}:
                to_mesh_float=np.array(list(map(list,human.matrix_world.inverted()@rig.matrix_world)),dtype=np.float32)
                from mathutils import Matrix
                to_rig_float=np.array(list(map(list,Matrix(to_mesh_float.tolist()).inverted())),dtype=np.float32)
                skin=mathutils_delta_skin if matrix_policy=='mathutils_float_delta' else float_delta_skin
                predicted=skin(base,deformation,bone_ids,raw_weights,to_rig_float,to_mesh_float,mesh_world)
            raw_error=float(np.max(np.linalg.norm(predicted-raw,axis=1)))
            if actual_raw is not None and frame==first_frame:
                observation={'raw_error_m':raw_error,
                    'raw_copy_vertex_difference':float(np.max(np.abs(np.array([tuple(v.co) for v in actual_raw.data.vertices])-base))),
                    'raw_copy_keys':{key.name:float(key.value) for key in actual_raw.data.shape_keys.key_blocks},
                    'copy_same_key_data':actual_candidate.data.shape_keys==actual_raw.data.shape_keys,
                    'copy_world_difference':float(np.max(np.abs(np.array(list(map(list,actual_raw.matrix_world)))-mesh_world))),
                    'raw_copy_modifiers':[(mod.name,mod.type) for mod in actual_raw.modifiers]}
                (output/'reference-observation.json').write_text(json.dumps(observation,indent=2))
            if not np.isfinite(raw_error) or raw_error>1e-6:
                raise ValueError('Independent normalized original LBS does not reproduce actual raw Blender surface: '+str({'frame':frame,'error_m':raw_error}))
            desired=np.column_stack((corrected,np.ones(len(base))))@np.linalg.inv(mesh_world).T
            solved=np.linalg.solve(matrices,desired[:,:,None])[:,:,0][:,:3].astype(np.float32)
            # Actual shape keys store absolute float32 coordinates. Simulate
            # Basis-relative value-one arithmetic, including its roundings.
            mixed=(base.astype(np.float32)+(solved-base.astype(np.float32))).astype(np.float32)
            corrected4=np.column_stack((mixed,np.ones(len(base))))
            rebuilt=(np.einsum('nij,nj->ni',matrices,corrected4)@mesh_world.T)[:,:3]
            iterations=0
            if corrective_key is not None:
                for attempt in range(4):
                    corrective_key.data.foreach_set('co',solved.reshape(-1))
                    bpy.context.view_layer.update()
                    rebuilt=np.array(evaluated(bpy,actual_candidate),dtype=np.float64)
                    if float(np.max(np.linalg.norm(rebuilt-corrected,axis=1)))<=1e-6:break
                    residual=np.column_stack((corrected-rebuilt,np.zeros(len(base))))@np.linalg.inv(mesh_world).T
                    update=np.linalg.solve(matrices,residual[:,:,None])[:,:,0][:,:3]
                    solved=(solved.astype(np.float64)+update).astype(np.float32)
                    iterations+=1
            error=float(np.max(np.linalg.norm(rebuilt-corrected,axis=1)))
            if not np.isfinite(error) or error>1e-6:
                raise ValueError('Stored float32 corrective target cannot reproduce actual source: '+str(error))
            correction=float(np.max(np.linalg.norm(corrected-raw,axis=1)))
            delta=float(np.max(np.linalg.norm(solved-base,axis=1)))
            for key,value in [('raw_lbs_error_m',raw_error),('corrected_reconstruction_error_m',error),('required_correction_world_m',correction),('rest_space_delta_m',delta)]:
                maxima[key]=max(maxima[key],value)
            solved.astype('<f4').tofile(targets);corrected.astype('<f4').tofile(positions)
            rows.append({'frame':frame,'raw_lbs_error_m':raw_error,'corrected_reconstruction_error_m':error,
                         'required_correction_world_m':correction,'rest_space_delta_m':delta,
                         'actual_Blender_inverse_refinement_steps':iterations})
            if frame%50==0:print('CORRECTIVE_INVERSE_FRAMES',frame,flush=True)
    if maxima['required_correction_world_m']<1e-4:
        raise ValueError('Probe did not exercise measurable source corrective deformation')
    assert all(sha256(path.read_bytes()).hexdigest()==before[str(path)] for path in paths)
    result={'status':('REAL_NATIVE300_INVERSE_CORRECTIVE_FLOAT32_FEASIBILITY_PASSED' if (first_frame,last_frame)==(1,300) else 'PARTIAL_NUMERIC_DIAGNOSTIC_ONLY_NOT_COMPLETE_FEASIBILITY'),
        'blender_version':bpy.app.version_string,'bundled_numpy_version':np.__version__,
        'matrix_policy':matrix_policy,
        'actual_Blender_mesh_evaluation_verified':actual_candidate is not None,
        'frames':len(rows),'first_frame':first_frame,'last_frame':last_frame,'fps':30,'source_vertices':13380,'family_bones':163,'maxima':maxima,
        'minimum_absolute_skin_determinant':minimum_det,'maximum_skin_condition':maximum_condition,
        'rows':rows,'source_files_unchanged':before,
        'private_files':{path.name:{'sha256':sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size} for path in output.glob('*.f32')},
        'coordinate_policy':'UNCONVERTED_BLENDER_Z_UP_DIAGNOSTIC_ONLY',
        'animation_created':False,'engine_import_verified':False,'visual_quality_approved':False}
    with (output/'receipt.json').open('x',encoding='utf-8') as stream:json.dump(result,stream,indent=2,allow_nan=False)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--job',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--matrix-policy',choices=('ideal_rest','evaluated_channel','blender_float_delta','mathutils_float_delta','actual_blender_candidate'),default='ideal_rest')
    parser.add_argument('--first-frame',type=int,default=1);parser.add_argument('--last-frame',type=int,default=300)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]);print(run(args.job,args.out,args.matrix_policy,args.first_frame,args.last_frame)['status'],flush=True)
