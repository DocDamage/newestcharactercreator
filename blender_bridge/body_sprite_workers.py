"""Independent authenticated native FK and saved-scene body-sprite reproduction."""
from pathlib import Path
from typing import Any
import shutil

from blender_bridge.face_geometry import intake
from blender_bridge.face_policy import read_json,digest
from blender_bridge.face_operations import state_digest
from blender_bridge.native_inputs import validate_source,validate_profile
from blender_bridge.native_retarget import retarget_native
from blender_bridge.native_review_reopen import reopen_native,scene_objects,bound_scene
from blender_bridge.godot_outputs import write_json
from blender_bridge.skin_material_model import shader_snapshot,checked_owned_material
from blender_bridge.sprite_scene import snapshot,SCENE
from blender_bridge.body_sprite_scene import setup,restore,source_state
from blender_bridge.body_sprite_frames import action_state,geometry,all_frames,compare_complete,render_frames,compare_frames
from ucc.core.body_sprites import POLICY,STAGE,VERIFY,BodySpriteRequest,validate_recipe,validate_job,worker_bindings
from ucc.core.target_action_format import canonical_bytes

INPUTS={'candidate.blend':'master_sha256','review_motion.blend':'review_sha256',
        'source_snapshot.json':'snapshot_sha256','native_mapping.json':'mapping_sha256',
        'target_timeline.json':'timeline_sha256','body_sprite_recipe.json':'recipe_sha256'}


def unchanged(root: Path,options: dict) -> None:
    for name,key in INPUTS.items():
        path=root/name
        if path.is_symlink() or not path.is_file() or digest(path)!=options[key]:raise ValueError('Body-sprite staged authoritative input changed: '+name)


def inputs(root: Path,job: dict) -> tuple:
    options=job['options'];validate_job(job['operation'],job['input_project'],options);unchanged(root,options)
    recipe=validate_recipe(read_json(root/'body_sprite_recipe.json',options['recipe_sha256'],256*1024))
    request=BodySpriteRequest.from_dict(recipe['request'])
    expected=worker_bindings(request,options['recipe_sha256'])
    if any(options[key]!=value for key,value in expected.items()):raise ValueError('Body-sprite recipe differs from its complete registered binding')
    native={key:options[key] for key in ('master_sha256','review_sha256','snapshot_sha256','mapping_sha256','timeline_sha256')}
    native['source_sha256']=request.target_binding.source.source_sha256
    source=validate_source(read_json(root/'source_snapshot.json',native['snapshot_sha256'],64*1024*1024),native['source_sha256'])
    profile=validate_profile(read_json(root/'native_mapping.json',native['mapping_sha256'],64*1024),native['source_sha256'],native['snapshot_sha256'],native['master_sha256'])
    timeline=read_json(root/'target_timeline.json',native['timeline_sha256'],64*1024*1024)
    if ((source['first_frame'],source['last_frame'],source['fps'],len(source['frames']))!=(2,301,30,300)
            or profile.get('skin_deformation_policy')!='BOUND_CORRECTIVE_SMOOTH_V1'):
        raise ValueError('Body-sprite sources differ from complete registered native300 V1 clock/skin')
    return request,native,profile,timeline


def original_reference(bpy: Any,root: Path,native: dict,profile: dict,request: Any) -> tuple:
    """Recompute genuine source FK; no retained report can substitute for this solve."""
    directory=root/'body_source_reference'
    if directory.exists() or directory.is_symlink():raise ValueError('Body source reconstruction directory already exists')
    directory.mkdir()
    for name in ('candidate.blend','source_snapshot.json','native_mapping.json'):
        shutil.copyfile(root/name,directory/name)
        if digest(directory/name)!=digest(root/name):raise ValueError('Body reference input copy changed')
    bound_scene(directory/'candidate.blend',native['master_sha256'])
    bpy.ops.wm.open_mainfile(filepath=str(directory/'candidate.blend'),load_ui=False)
    human,rig,_,targets=intake(bpy)
    if checked_owned_material(bpy,human) is not None:raise ValueError('Source Human already has material slots')
    result=retarget_native(bpy,directory,{key:native[key] for key in ('master_sha256','source_sha256','snapshot_sha256','mapping_sha256')}|{'render_private_frames':False})
    options={**{key:native[key] for key in ('master_sha256','source_sha256','snapshot_sha256','mapping_sha256')},
        'review_sha256':result['visual_review_blend']['sha256'],'timeline_sha256':result['timeline']['sha256']}
    measured=[]
    reopened=reopen_native(bpy,directory,options,frame_observer=lambda api,h,r,frame,skin:measured.append(geometry(api,h,r,profile['pairs'])))
    if reopened['frames_verified']!=300 or len(measured)!=300:raise ValueError('Body source reconstruction did not verify every native frame')
    human,rig=scene_objects(bpy);bpy.context.scene.frame_set(request.window.target_first_frame);bpy.context.view_layer.update()
    return human,rig,targets,measured,source_state(bpy,human,rig,targets,request),action_state(bpy,rig)


def retained_source(bpy: Any,root: Path,native: dict,profile: dict,request: Any,reference: list[dict],state: str,action: str,targets: Any) -> tuple:
    measured=[]
    report=reopen_native(bpy,root,native,frame_observer=lambda api,h,r,frame,skin:measured.append(geometry(api,h,r,profile['pairs'])))
    if report['frames_verified']!=300:raise ValueError('Registered saved Action lacks complete300 admission')
    compare_complete(measured,reference)
    human,rig=scene_objects(bpy);bpy.context.scene.frame_set(request.window.target_first_frame);bpy.context.view_layer.update()
    if source_state(bpy,human,rig,targets,request)!=state or action_state(bpy,rig)!=action:
        raise ValueError('Registered Action changed source character intent or canonical complete Action')
    return human,rig


def stage(bpy: Any,root: Path,job: dict) -> dict:
    options=job['options'];request,native,profile,timeline=inputs(root,job)
    if any((root/name).exists() or (root/name).is_symlink() for name in ('body_sprite_scene.blend','body_sprite_stage.json')):
        raise ValueError('Body sprite outputs already exist')
    _,_,targets,reference,state,action=original_reference(bpy,root,native,profile,request)
    human,rig=retained_source(bpy,root,native,profile,request,reference,state,action,targets)
    scene,original,pivot=setup(bpy,human,rig,request);configuration=snapshot(scene)
    if source_state(bpy,human,rig,targets,request,temporary=True)!=state:raise ValueError('Body render setup changed original character intent')
    shader=state_digest(shader_snapshot(human.data.materials[0]));original_name=original.name
    bpy.ops.wm.save_as_mainfile(filepath=str(root/'body_sprite_scene.blend'),compress=False)
    rows=render_frames(bpy,root,scene,request,human,rig,profile['pairs'],reference)
    restore(bpy,scene,original,human,request)
    if source_state(bpy,human,rig,targets,request)!=state or action_state(bpy,rig)!=action:
        raise ValueError('Body sprite staging failed to preserve original character/Action')
    unchanged(root,options)
    report={'schema_version':1,'policy':POLICY,'bindings':dict(options),'scene_sha256':digest(root/'body_sprite_scene.blend'),
        'source_state_sha256':state,'saved_action_state_sha256':action,'shader_sha256':shader,
        'temporary_matte_sha256':request.temporary_matte.sha256,'source_material_slots':0,
        'configuration':configuration,'original_scene':original_name,'pivot':pivot,
        'full_clock':request.to_dict()['full_clock'],'window':request.window.to_dict(),'frames':rows,
        'blender_version':bpy.app.version_string,'blender_build_hash':bpy.app.build_hash.decode(),
        'visual_quality_approved':False,'material_adopted':False}
    write_json(root/'body_sprite_stage.json',report)
    return {'policy':POLICY,'scene_sha256':report['scene_sha256'],'stage_sha256':digest(root/'body_sprite_stage.json')}


def verify(bpy: Any,root: Path,job: dict) -> dict:
    options=job['options'];request,native,profile,timeline=inputs(root,job)
    stage=read_json(root/'body_sprite_stage.json',options['stage_sha256'],4*1024*1024)
    human,rig,targets,reference,state,action=original_reference(bpy,root,native,profile,request)
    # Source construction and selected raster reference are fresh in this process.
    scene,original,pivot=setup(bpy,human,rig,request);configuration=snapshot(scene)
    shader=state_digest(shader_snapshot(human.data.materials[0]));original_name=original.name
    expected={'schema_version':1,'policy':POLICY,'bindings':{key:options[key] for key in worker_bindings(request,options['recipe_sha256'])},
        'scene_sha256':options['scene_sha256'],'source_state_sha256':state,'saved_action_state_sha256':action,'shader_sha256':shader,
        'temporary_matte_sha256':request.temporary_matte.sha256,'source_material_slots':0,
        'configuration':configuration,'original_scene':original_name,'pivot':pivot,
        'full_clock':request.to_dict()['full_clock'],'window':request.window.to_dict(),
        'blender_version':bpy.app.version_string,'blender_build_hash':bpy.app.build_hash.decode(),
        'visual_quality_approved':False,'material_adopted':False}
    if set(stage)!=set(expected)|{'frames'} or canonical_bytes({k:v for k,v in stage.items() if k!='frames'})!=canonical_bytes(expected):
        raise ValueError('Body sprite stage differs from independently reconstructed original source')
    rows=render_frames(bpy,root,scene,request,human,rig,profile['pairs'],reference,prefix='source-')
    compare_frames(root,rows,stage['frames']);restore(bpy,scene,original,human,request)
    bound_scene(root/'body_sprite_scene.blend',options['scene_sha256'])
    bpy.ops.wm.open_mainfile(filepath=str(root/'body_sprite_scene.blend'),load_ui=False)
    scene=bpy.data.scenes.get(SCENE);original=bpy.data.scenes.get(original_name)
    if scene is None or original is None or bpy.context.scene!=scene:raise ValueError('Saved body sprite scenes differ')
    bpy.context.window.scene=original;bpy.context.view_layer.update();bpy.context.window.scene=scene;bpy.context.view_layer.update()
    if snapshot(scene)!=configuration:raise ValueError('Saved body sprite camera/render configuration changed')
    human,rig=scene_objects(bpy)
    if source_state(bpy,human,rig,targets,request,temporary=True)!=state or action_state(bpy,rig)!=action:
        raise ValueError('Saved body sprite source intent/rest/weights/keys or Action changed')
    if state_digest(shader_snapshot(human.data.materials[0]))!=shader:raise ValueError('Saved body sprite shader differs')
    compare_complete(all_frames(bpy,human,rig,profile['pairs'],timeline),reference)
    rows=render_frames(bpy,root,scene,request,human,rig,profile['pairs'],reference,prefix='verify-');compare_frames(root,rows,stage['frames'])
    restore(bpy,scene,original,human,request)
    if source_state(bpy,human,rig,targets,request)!=state or action_state(bpy,rig)!=action:raise ValueError('Saved body sprite cleanup changed source/Action')
    unchanged(root,options)
    proof={'schema_version':1,'policy':POLICY,'bindings':dict(options),'verified_reopen':True,'saved_scene_rebuilt_or_repaired':False,
        'source_state_sha256':state,'saved_action_state_sha256':action,'shader_sha256':shader,'temporary_matte_sha256':request.temporary_matte.sha256,
        'reference_frames':request.image_count,'saved_frames':request.image_count,'full_source_frames_verified':300,'full_saved_frames_verified':300,
        'exact_selected_pose_match':True,'exact_rerender_pixels':True,'material_adopted':False,'visual_quality_approved':False}
    write_json(root/'body_sprite_verification.json',proof);return proof
