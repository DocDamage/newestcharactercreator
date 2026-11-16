"""Stage a real facial Action; verify all source and saved-scene raster frames."""
from pathlib import Path
from typing import Any
from blender_bridge.face_policy import read_json,digest
from blender_bridge.face_operations import state_digest
from blender_bridge.expression_clip_policy import check_inputs
from blender_bridge.expression_clip_workers import reference
from blender_bridge.expression_clip_action import create_action,saved_intake
from blender_bridge.expression_existing import canonical_keys
from blender_bridge.expression_geometry import source_state
from blender_bridge.skin_material_model import checked_owned_material,nonmaterial_state,material_name,shader_snapshot
from blender_bridge.sprite_scene import setup,snapshot,cleanup,SCENE
from blender_bridge.facial_sprite_frames import render_frames,compare_frames
from blender_bridge.godot_outputs import write_json
from ucc.core.facial_sprites import POLICY,STAGE,VERIFY,TARGET_BINDINGS,validate_recipe,validate_job,FacialSpriteRequest
from ucc.core.skin_material import SkinMaterialSpec
from ucc.core.sprite_render import canonical


def source(bpy: Any,root: Path,job: dict) -> tuple:
    options=job['options'];validate_job(job['operation'],job['input_project'],options)
    recipe=validate_recipe(read_json(root/'facial_sprite_recipe.json',options['recipe_sha256'],256*1024))
    request=FacialSpriteRequest.from_dict(recipe['request']);settings=request.review.settings
    plan=check_inputs(root,{k:options[k] for k in ('master_sha256','clip_sha256',*TARGET_BINDINGS)})
    if canonical(plan)!=request.clip_json:raise ValueError('Facial sprite clip differs from its reviewed recipe')
    context=reference(bpy,root,plan);human,rig,targets=context[:3];spec=SkinMaterialSpec.from_dict(recipe['material_spec'])
    if checked_owned_material(bpy,human)!=spec:raise ValueError('Facial sprite source material differs from the saved specification')
    state=nonmaterial_state(bpy,human,rig,targets,{material_name(spec)});shader=state_digest(shader_snapshot(human.data.materials[0]))
    return request,settings,spec,context,state,shader


def restore(bpy: Any,scene: Any,original: Any,context: tuple,spec: Any,state: str,shader: str,*,saved: bool) -> None:
    human,rig,targets=context[:3]
    if saved:
        action=human.data.shape_keys.animation_data.action
        human.data.shape_keys.animation_data_clear();bpy.data.actions.remove(action)
    cleanup(bpy,scene,original)
    if (nonmaterial_state(bpy,human,rig,targets,{material_name(spec)})!=state
            or state_digest(shader_snapshot(human.data.materials[0]))!=shader):
        raise ValueError('Facial sprite operation changed original editable state, materials, rig or keys')


def scene_context(bpy: Any,context: tuple) -> tuple:
    # The added cameras/lights are part of invariant_state.objects. Measure the
    # animated surface against this fixed render scene, then separately remove
    # only those helpers and check the complete original fingerprint in restore.
    human,rig,targets=context[:3]
    return (*context[:4],source_state(bpy,human,rig,targets,strip_expression=True),
        source_state(bpy,human,rig,targets),*context[6:])


def stage(bpy: Any,root: Path,job: dict) -> dict:
    if any((root/n).exists() or (root/n).is_symlink() for n in ('facial_sprite_scene.blend','facial_sprite_stage.json')):
        raise ValueError('Facial sprite outputs already exist')
    request,settings,spec,context,state,shader=source(bpy,root,job);human,rig=context[:2]
    scene,original,pivot=setup(bpy,human,rig,settings);context=scene_context(bpy,context)
    create_action(bpy,human,context[7]);saved_intake(bpy,context[7])
    configuration=snapshot(scene);original_name=original.name
    bpy.ops.wm.save_as_mainfile(filepath=str(root/'facial_sprite_scene.blend'),compress=False)
    frames=render_frames(bpy,root,scene,settings,context,spec,prefix='',manual=False)
    saved_intake(bpy,context[7]);restore(bpy,scene,original,context,spec,state,shader,saved=True)
    report={'schema_version':1,'policy':POLICY,'recipe_sha256':job['options']['recipe_sha256'],
        'master_sha256':job['options']['master_sha256'],'clip_sha256':job['options']['clip_sha256'],
        'scene_sha256':digest(root/'facial_sprite_scene.blend'),'source_state_sha256':state,'shader_sha256':shader,
        'configuration':configuration,'original_scene':original_name,'pivot':pivot,'frames':frames,'timeline':request.clip['timeline'],
        'blender_version':bpy.app.version_string,'blender_build_hash':bpy.app.build_hash.decode(),'animation_clips':True,'visual_quality_approved':False}
    write_json(root/'facial_sprite_stage.json',report)
    return {'policy':POLICY,'scene_sha256':report['scene_sha256'],'stage_sha256':digest(root/'facial_sprite_stage.json')}


def verify(bpy: Any,root: Path,job: dict) -> dict:
    options=job['options'];request,settings,spec,context,state,shader=source(bpy,root,job);human,rig=context[:2]
    report=read_json(root/'facial_sprite_stage.json',options['stage_sha256'],4*1024*1024)
    scene,original,pivot=setup(bpy,human,rig,settings);context=scene_context(bpy,context);expected=snapshot(scene)
    # Saved Action creates this exact fixed timeline on the new render scene.
    original_name=original.name
    for key,value in {'master_sha256':options['master_sha256'],'recipe_sha256':options['recipe_sha256'],
            'clip_sha256':options['clip_sha256'],'scene_sha256':options['scene_sha256'],'source_state_sha256':state,
            'shader_sha256':shader,'configuration':expected,'pivot':pivot,'original_scene':original_name,'timeline':request.clip['timeline']}.items():
        if canonical(report.get(key))!=canonical(value):raise ValueError('Facial sprite stage differs from independent original-source reconstruction: '+key)
    if digest(root/'facial_sprite_scene.blend')!=options['scene_sha256']:raise ValueError('Saved facial sprite scene changed')
    rows=render_frames(bpy,root,scene,settings,context,spec,prefix='source-',manual=True);compare_frames(root,rows,report)
    restore(bpy,scene,original,context,spec,state,shader,saved=False)
    bpy.ops.wm.open_mainfile(filepath=str(root/'facial_sprite_scene.blend'),load_ui=False)
    scene=bpy.data.scenes.get(SCENE);original=bpy.data.scenes.get(original_name)
    if scene is None or original is None or bpy.context.scene!=scene or snapshot(scene)!=expected:
        raise ValueError('Saved facial sprite scene/camera/render settings differ')
    # Objects outside the active render scene have unevaluated identity world
    # matrices immediately after reopening. Evaluate their existing scene before
    # comparing the full invariant; do not assign transforms or repair data.
    bpy.context.window.scene=original;bpy.context.view_layer.update()
    bpy.context.window.scene=scene;bpy.context.view_layer.update()
    human,rig,_,targets=saved_intake(bpy,context[7]);loaded,_,_,_=canonical_keys(root,human,targets)
    saved_context=(human,rig,targets,loaded,*context[4:])
    if checked_owned_material(bpy,human)!=spec:raise ValueError('Saved facial sprite material differs')
    rows=render_frames(bpy,root,scene,settings,saved_context,spec,prefix='verify-',manual=False);compare_frames(root,rows,report)
    saved_intake(bpy,context[7]);restore(bpy,scene,original,saved_context,spec,state,shader,saved=True)
    proof={'schema_version':1,'policy':POLICY,'bindings':options,'verified_reopen':True,'saved_scene_rebuilt_or_repaired':False,
        'source_state_sha256':state,'shader_sha256':shader,'reference_frames':25*settings.directions,'saved_frames':25*settings.directions,
        'exact_neutral_endpoints':True,'exact_rerender_pixels':True,'visual_quality_approved':False}
    write_json(root/'facial_sprite_verification.json',proof);return proof
