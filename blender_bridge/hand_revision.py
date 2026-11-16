"""Independent source-bound hand swapping; no master promotion occurs here."""
import json
import shutil

from blender_bridge.hand_policy import POLICY,check_revision_inputs,state_digest,digest,read_json
from blender_bridge.hand_master import asset_payloads,reconstruct,observe_saved,observe_master
from blender_bridge.hand_pose_checks import pose_observations


def _reproduce(bpy,root,options,manifest):
    payloads=asset_payloads(bpy,root,manifest)
    _,_,_,expected_current=reconstruct(bpy,root,manifest,payloads,options['current_selection'])
    current_sha=state_digest(expected_current)
    if options['current_selection'] != 'neutral' and current_sha != options['current_observation_sha256']:
        raise ValueError('Current hand receipt differs from independent original/asset reproduction')
    _,_,_,actual_current=observe_saved(bpy,root/'candidate.blend')
    if state_digest(actual_current) != current_sha:
        raise ValueError('Current master differs from its declared original/hand selection; no edits discarded')
    human,rig,targets,desired=reconstruct(bpy,root,manifest,payloads,options['selection'])
    region=payloads['shorter']['region']
    return human,rig,targets,desired,region,payloads


def _report(bpy,options,observation,scene_sha):
    return {'schema_version':1,'policy':POLICY,'manifest_sha256':options['manifest_sha256'],
            'source_master_sha256':options['master_sha256'],'original_master_sha256':options['original_master_sha256'],
            'current_selection':options['current_selection'],'selection':options['selection'],
            'scene_sha256':scene_sha,'observation_sha256':state_digest(observation),
            'blender_version':bpy.app.version_string,
            'selection_changed':options['selection'] != options['current_selection'],
            'visual_quality_approved':False,'penetration_quality_approved':False,'engine_import_verified':False}


def stage_revision(bpy,root,options):
    manifest=check_revision_inputs(root,options)
    scene=root/'revised_human.blend';report_path=root/'hand_revision_report.json'
    if any(p.exists() or p.is_symlink() for p in (scene,report_path)):
        raise ValueError('Hand revision refuses to overwrite existing output')
    human,rig,targets,expected,_,_=_reproduce(bpy,root,options,manifest)
    if options['selection'] == 'neutral':
        shutil.copyfile(root/'original.blend',scene)
    else:
        bpy.ops.wm.save_as_mainfile(filepath=str(scene),compress=False)
    if state_digest(observe_master(bpy,human,rig,targets)) != state_digest(expected):
        raise ValueError('Saving changed the installed hand')
    check_revision_inputs(root,options)
    report=_report(bpy,options,expected,digest(scene))
    with report_path.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,indent=2,allow_nan=False)
    return report


def verify_revision(bpy,root,options):
    manifest=check_revision_inputs(root,options,verify=True)
    report=read_json(root/'hand_revision_report.json',options['revision_report_sha256'],16*1024*1024)
    _,_,_,expected,region,payloads=_reproduce(bpy,root,options,manifest)
    expected_report=_report(bpy,options,expected,options['revised_sha256'])
    if state_digest(report) != state_digest(expected_report):
        raise ValueError('Hand report differs from independent original/asset reproduction')
    human,rig,targets,actual=observe_saved(bpy,root/'revised_human.blend')
    if state_digest(actual) != state_digest(expected):
        raise ValueError('Saved hand geometry, keys, rig or unrelated state differs from independent reproduction')
    actual_poses=pose_observations(bpy,human,rig,targets,region)
    human,rig,targets,repeated=reconstruct(bpy,root,manifest,payloads,options['selection'])
    if state_digest(repeated) != state_digest(expected):
        raise ValueError('Independent hand reference changed during saved-scene observation')
    expected_poses=pose_observations(bpy,human,rig,targets,region)
    if state_digest(actual_poses) != state_digest(expected_poses):
        raise ValueError('Saved hand skin/shading/overlap observations differ over20 independent poses')
    if options['selection'] == 'neutral' and options['revised_sha256'] != options['original_master_sha256']:
        raise ValueError('Neutral reset did not restore the exact original master bytes')
    check_revision_inputs(root,options,verify=True)
    return {'schema_version':1,'policy':POLICY,'verified_reopen':True,
            'manifest_sha256':options['manifest_sha256'],'source_master_sha256':options['master_sha256'],
            'original_master_sha256':options['original_master_sha256'],'scene_sha256':options['revised_sha256'],
            'observation_sha256':state_digest(expected),'current_selection':options['current_selection'],
            'selection':options['selection'],'selection_changed':options['selection'] != options['current_selection'],
            'skin_poses':actual_poses,'all40_restores_exact':True,'visual_quality_approved':False,
            'penetration_quality_approved':False,'engine_import_verified':False}
