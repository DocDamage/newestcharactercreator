"""Fresh actual native interaction evaluation; source data is never rebuilt."""
from pathlib import Path
from typing import Any
import numpy as np
from blender_bridge.godot_runtime_source import checked_recipe,character_state
from blender_bridge.godot_runtime_workers import verify_native_runtime
from blender_bridge.godot_runtime_geometry import sampled_mesh
from blender_bridge.expression_geometry import macro_context
from blender_bridge.expression_policy import TARGETS,keyname
from blender_bridge.mpfb_service import locate_human_service,locate_target_service
from blender_bridge.native_review_reopen import digest
from blender_bridge.native_inputs import read_json
from blender_bridge.godot_outputs import write_json
from ucc.export.godot_candidate_contract import canonical_bytes
from ucc.export.godot_runtime_contract import NativeRuntimeRequest,FILES
from ucc.export.godot_native_recipe import INPUTS
from ucc.export.godot_native_samples import POLICY,COUNT,OUTPUTS,interaction_cases,ROLES,validate_sample_report


def sample_native_runtime(bpy: Any,root: Path,job: dict) -> dict:
    recipe=checked_recipe(root,job);options=job['options']
    for name in OUTPUTS|{'native_samples.json'}:
        if (root/name).exists() or (root/name).is_symlink():raise ValueError('Native sampler refuses existing outputs')
    request_path=root/'runtime_request.json';production=root/'native_production_receipt.json'
    if digest(request_path)!=options['runtime_request_sha256'] or digest(production)!=options['production_receipt_sha256']:
        raise ValueError('Native sample request/production receipt changed')
    request=NativeRuntimeRequest.from_bytes(request_path.read_bytes())
    if request.sha256!=options['runtime_request_sha256']:raise ValueError('Native sample bundle is not canonical')
    for name,sha in request.files:
        if digest(root/name)!=sha:raise ValueError('Native sample bundle file changed: '+name)
    proof=read_json(production,options['production_receipt_sha256'],256*1024)
    if (proof.get('request_sha256')!=request.sha256 or proof.get('recipe_sha256')!=options['native_recipe_sha256']
            or proof.get('native_verification_sha256')!=options['native_verification_sha256']):
        raise ValueError('Native sample source receipt belongs to another produced bundle')
    existing=read_json(root/'native_verification.json',options['native_verification_sha256'],4*1024*1024)
    verify_options={name:options[name] for name in set(INPUTS.values())|{'native_recipe_sha256','native_stage_sha256'}}
    proxy={**job,'operation':'verify_native_godot_runtime','options':verify_options}
    fresh=verify_native_runtime(bpy,root,proxy,save_report=False)
    if canonical_bytes(fresh)!=canonical_bytes(existing):raise ValueError('Fresh sample source verification differs from saved evidence')
    stage=read_json(root/'native_stage.json',options['native_stage_sha256'],4*1024*1024);names=stage['source_names']
    human=bpy.data.objects[names['human']];rig=bpy.data.objects[names['rig']]
    if character_state(bpy,human,rig)!=stage['master_state_sha256']:raise ValueError('Native sample source state changed')
    _,human_module=locate_human_service();targets,_=locate_target_service(human_module)
    _,race=macro_context(human,targets)
    cases=interaction_cases();views=[]
    protected={name:digest(root/name) for name in set(stage['files'])|set(INPUTS)|{'native_recipe.json','native_stage.json','native_verification.json','runtime_request.json','native_production_receipt.json'}}
    try:
        with (root/'expected_vec4.f32').open('xb') as positions,(root/'expected_normals_vec4.f32').open('xb') as normals:
            for index,query in enumerate(cases):
                bpy.context.scene.frame_set(query['frame'],subframe=query['subframe'])
                for role,family,_ in TARGETS:
                    human.data.shape_keys.key_blocks[keyname(role,family)].value=float(np.float32(query['facial_parameters'].get(role,0.)*race[family]))
                p,n=sampled_mesh(bpy,human)
                if np.max(np.abs(p))>100 or np.max(np.abs(np.linalg.norm(n,axis=1)-1))>1e-5:raise ValueError('Unbounded/nonunit native sample data')
                data=np.ones((13380,4),dtype='<f4');data[:,:3]=p;data.tofile(positions)
                data[:,3]=0.;data[:,:3]=n;data.tofile(normals)
                minimum=p.min(axis=0).astype(np.float64);maximum=p.max(axis=0).astype(np.float64);length=float(np.linalg.norm(maximum-minimum))
                views.append({'center':((minimum+maximum)*.5).tolist(),'size':length*1.25,'distance':length*1.6})
                if index%300==0:print('FRESH_NATIVE_INTERACTION_SAMPLE',index,COUNT,flush=True)
    finally:
        for role,family,_ in TARGETS:human.data.shape_keys.key_blocks[keyname(role,family)].value=0.
        bpy.context.scene.frame_set(1);bpy.context.view_layer.update()
    if character_state(bpy,human,rig)!=stage['master_state_sha256'] or any(digest(root/name)!=sha for name,sha in protected.items()):
        raise ValueError('Native sampling changed authoritative source files or state')
    report={'schema_version':1,'policy':POLICY,'status':'FRESH_NATIVE_INTERACTION_REFERENCES_MEASURED',
        'request_sha256':request.sha256,'production_receipt_sha256':options['production_receipt_sha256'],
        'recipe_sha256':options['native_recipe_sha256'],'native_verification_sha256':options['native_verification_sha256'],
        'vertices':13380,'samples':COUNT,'cases':cases,'views':views,'race_mix':race,'roles':list(ROLES),
        'files':{name:{'sha256':digest(root/name),'bytes':(root/name).stat().st_size} for name in OUTPUTS},
        'blender_version':bpy.app.version_string,'source_reopened_without_repair':True,'source_files_unchanged':True,
        'engine_import_verified':False,'visual_quality_approved':False,'distribution_license_review_complete':False}
    validate_sample_report(report,request_sha256=request.sha256,production_sha256=options['production_receipt_sha256'],
        recipe_sha256=options['native_recipe_sha256'],verification_sha256=options['native_verification_sha256'])
    write_json(root/'native_samples.json',report)
    return {'policy':POLICY,'status':report['status'],'native_samples_sha256':digest(root/'native_samples.json'),
        'sample_count':COUNT,'engine_import_verified':False}
