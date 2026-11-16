"""Actual source render plus separate saved-scene rerender; no source publication."""
from pathlib import Path
from typing import Any
from blender_bridge.face_geometry import intake
from blender_bridge.face_policy import read_json,digest
from blender_bridge.face_operations import state_digest
from blender_bridge.neutral_master import animation_audit,neutral_pose_and_keys
from blender_bridge.skin_material_model import checked_owned_material,material_name,nonmaterial_state,shader_snapshot
from blender_bridge.godot_outputs import write_json
from blender_bridge.sprite_scene import setup,snapshot,cleanup,SCENE,PREFIX
from ucc.core.sprite_render import POLICY,SpriteSettings,validate_recipe,validate_job
from ucc.core.skin_material import SkinMaterialSpec
from ucc.jobs.private_render_evidence import png_measurements


def source(bpy: Any,root: Path,job: dict) -> tuple:
    validate_job(job['operation'],job['input_project'],job['options']);options=job['options']
    recipe=validate_recipe(read_json(root/'sprite_recipe.json',options['recipe_sha256'],256*1024))
    if recipe['request']['source_bindings']['master']!=options['master_sha256'] or digest(root/'candidate.blend')!=options['master_sha256']:
        raise ValueError('Sprite source differs from the reviewed master')
    spec=SkinMaterialSpec.from_dict(recipe['material_spec']);settings=SpriteSettings.from_dict(recipe['request']['settings'])
    bpy.ops.wm.open_mainfile(filepath=str(root/'candidate.blend'),load_ui=False);animation_audit(bpy)
    human,rig,_,targets=intake(bpy)
    if neutral_pose_and_keys(rig,human)!=12 or checked_owned_material(bpy,human)!=spec:raise ValueError('Sprite source must retain its neutral prepared rig and saved owned material')
    state=nonmaterial_state(bpy,human,rig,targets,{material_name(spec)});shader=state_digest(shader_snapshot(human.data.materials[0]))
    return recipe,settings,spec,human,rig,targets,state,shader


def render(bpy: Any,root: Path,scene: Any,settings: SpriteSettings,*,verify: bool,reference: bool=False) -> list[dict]:
    frames=[];before=snapshot(scene)
    for i,yaw in enumerate(settings.angles()):
        name=f'sprite-{i:02d}.png';output=root/(('source-' if reference else 'verify-' if verify else '')+name)
        if output.exists() or output.is_symlink():raise ValueError('Sprite renderer refuses existing output')
        scene.camera=bpy.data.objects[PREFIX+f'CAMERA_{i:02d}'];scene.render.filepath=str(output)
        bpy.ops.render.render(scene=scene.name,write_still=True)
        if snapshot(scene)!=before:raise ValueError('Rendering changed the bound camera/lighting/source scene')
        observed=png_measurements(output.read_bytes(),include_pixel_hash=True,expected_size=(settings.resolution,settings.resolution))
        frames.append({'file':name,'direction_index':i,'yaw_deg':yaw,'sha256':digest(output),**observed})
    scene.camera=bpy.data.objects[PREFIX+'CAMERA_00']
    return frames


def compare_frames(root: Path,frames: list[dict],report: dict,*,source_reference: bool) -> None:
    if len(report.get('frames',[]))!=len(frames):raise ValueError('Incomplete staged sprite images')
    for actual,record in zip(frames,report['frames']):
        path=root/actual['file']
        if path.is_symlink() or not path.is_file() or digest(path)!=record.get('sha256') or {k:v for k,v in actual.items() if k!='sha256'}!={k:v for k,v in record.items() if k!='sha256'}:
            raise ValueError('Independent original-source sprite pixels differ from staged PNGs' if source_reference else 'Saved sprite scene re-render pixels differ from staged PNGs')


def stage(bpy: Any,root: Path,job: dict) -> dict:
    if any((root/n).exists() or (root/n).is_symlink() for n in ('sprite_scene.blend','sprite_stage.json')):raise ValueError('Sprite stage outputs already exist')
    recipe,settings,spec,human,rig,targets,state,shader=source(bpy,root,job)
    scene,original,pivot=setup(bpy,human,rig,settings);configuration=snapshot(scene)
    bpy.ops.wm.save_as_mainfile(filepath=str(root/'sprite_scene.blend'),compress=False)
    frames=render(bpy,root,scene,settings,verify=False);cleanup(bpy,scene,original)
    if nonmaterial_state(bpy,human,rig,targets,{material_name(spec)})!=state or state_digest(shader_snapshot(human.data.materials[0]))!=shader:
        raise ValueError('Sprite staging changed the original editable character state')
    report={'schema_version':1,'policy':POLICY,'recipe_sha256':job['options']['recipe_sha256'],'master_sha256':job['options']['master_sha256'],
        'scene_sha256':digest(root/'sprite_scene.blend'),'source_state_sha256':state,'shader_sha256':shader,'configuration':configuration,
        'pivot':pivot,'frames':frames,'blender_version':bpy.app.version_string,'blender_build_hash':bpy.app.build_hash.decode(),
        'animation_clips':False,'visual_quality_approved':False}
    write_json(root/'sprite_stage.json',report)
    return {'policy':POLICY,'scene_sha256':report['scene_sha256'],'stage_sha256':digest(root/'sprite_stage.json')}


def verify(bpy: Any,root: Path,job: dict) -> dict:
    options=job['options'];recipe,settings,spec,human,rig,targets,state,shader=source(bpy,root,job)
    report=read_json(root/'sprite_stage.json',options['stage_sha256'],4*1024*1024)
    scene,_,pivot=setup(bpy,human,rig,settings);expected=snapshot(scene)
    if (report.get('recipe_sha256')!=options['recipe_sha256'] or report.get('master_sha256')!=options['master_sha256']
            or report.get('scene_sha256')!=options['scene_sha256'] or digest(root/'sprite_scene.blend')!=options['scene_sha256']
            or report.get('source_state_sha256')!=state or report.get('shader_sha256')!=shader or report.get('configuration')!=expected or report.get('pivot')!=pivot):
        raise ValueError('Sprite stage differs from independent original-source reconstruction')
    # An existing source material can be used as a coherent scene/view-layer
    # override without changing the owned body shader. A separately rendered
    # original-source reference also binds settings outside the snapshot fields.
    source_frames=render(bpy,root,scene,settings,verify=True,reference=True)
    compare_frames(root,source_frames,report,source_reference=True)
    bpy.ops.wm.open_mainfile(filepath=str(root/'sprite_scene.blend'),load_ui=False);animation_audit(bpy)
    human,rig,_,targets=intake(bpy);scene=bpy.data.scenes.get(SCENE)
    if (scene is None or neutral_pose_and_keys(rig,human)!=12 or checked_owned_material(bpy,human)!=spec or snapshot(scene)!=expected):
        raise ValueError('Saved sprite scene differs from its source, camera, material or bounded render settings')
    bpy.context.window.scene=scene;bpy.context.view_layer.update();frames=render(bpy,root,scene,settings,verify=True)
    compare_frames(root,frames,report,source_reference=False)
    original=next((s for s in bpy.data.scenes if s.name!=SCENE),None)
    if original is None:raise ValueError('Original scene was removed from sprite staging')
    cleanup(bpy,scene,original)
    if nonmaterial_state(bpy,human,rig,targets,{material_name(spec)})!=state or state_digest(shader_snapshot(human.data.materials[0]))!=shader:
        raise ValueError('Saved sprite scene changed original geometry, rig, UVs, keys or shader')
    proof={'schema_version':1,'policy':POLICY,'bindings':options,'verified_reopen':True,'saved_scene_rebuilt_or_repaired':False,
        'source_state_sha256':state,'shader_sha256':shader,'frame_count':settings.directions,'exact_rerender_pixels':True,'visual_quality_approved':False}
    write_json(root/'sprite_verification.json',proof)
    return proof
