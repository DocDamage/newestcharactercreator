"""Fresh-process saved-scene and native FBX verification of an original walk."""
import json
from pathlib import Path
from typing import Any

from blender_bridge.fbx_source import inspect_fbx_source, matrix_values
from blender_bridge.idle_authoring_measure import check_frame, measure
from blender_bridge.idle_authoring_policy import (
    canonical_path, checked_sha, document, payload, require, unchanged, write_document,
)
from blender_bridge.walk_authoring_verify_scene import (
    LIMITS, WalkSceneObservation, contact_gates, delta, matrix, observe_saved,
)
from ucc.animations.fbx_snapshot import MAX_SNAPSHOT_BYTES
from ucc.core.authored_idle import AuthoredIdleInspectionRequest
from ucc.core.authored_walk_job import read_walk_intent
from ucc.core.storage import ProjectStore
from ucc.core.target_action_format import MAX_BYTES, checked_uuid


OPERATION = 'verify_authored_walk_source'
STATUS = 'ORIGINAL_WALK_TECHNICALLY_VERIFIED'
SNAPSHOT = 'authored_walk_source_snapshot.json'
REPORT = 'walk_verification.json'
INPUT_OPTIONS = {
    'candidate.blend': 'master_sha256',
    'project.ucc.json': 'project_sha256',
    'idle_anatomical_frame.json': 'anatomy_sha256',
    'idle_inspection_request.json': 'request_sha256',
    'walk_authoring_request.json': 'walk_request_sha256',
    'original_walk.blend': 'review_sha256',
    'original_walk.fbx': 'source_sha256',
}


def _checked_inputs(root: Path, job: dict):
    options = job.get('options')
    verify_id = checked_uuid(job.get('job_id'))
    require(job.get('operation') == OPERATION and job.get('input_project') == 'candidate.blend'
            and type(options) is dict and set(options) == set(INPUT_OPTIONS.values()),
            'Walk verification requires the exact staged options')
    pins = {name: checked_sha(options[key]) for name, key in INPUT_OPTIONS.items()}
    unchanged(root, pins)
    request = AuthoredIdleInspectionRequest.from_bytes(
        payload(root, 'idle_inspection_request.json', pins['idle_inspection_request.json'], MAX_BYTES))
    require(request.job_id != verify_id, 'Original walk verification must use a fresh worker')
    require(request.to_dict()['consumed_sources']['master_and_derived_rig'] == pins['candidate.blend'],
            'Original walk master differs from the inspected project')
    read_walk_intent(payload(root, 'walk_authoring_request.json', pins['walk_authoring_request.json'], MAX_BYTES),
                     options, request)
    project = ProjectStore(root).load()
    require(project == request.project, 'Original walk saved project differs from the inspection request')
    declared = document(root, 'idle_anatomical_frame.json', pins['idle_anatomical_frame.json'])
    unchanged(root, pins)
    return project, declared, pins


def _verify_fbx(bpy: Any, root: Path, source_sha: str, observed: WalkSceneObservation) -> tuple[dict, dict]:
    """Verify bind and full dense FBX playback independently from the saved Blender scene."""
    from mathutils import Vector

    path = canonical_path(root, SNAPSHOT)
    admission = inspect_fbx_source(bpy, canonical_path(root, 'original_walk.fbx'), path, source_sha)
    record = admission['snapshot']
    snapshot = json.loads(payload(root, SNAPSHOT, record['sha256'], MAX_SNAPSHOT_BYTES))
    require((snapshot['first_frame'], snapshot['last_frame'], snapshot['fps'], len(snapshot['frames']))
            == (2, 301, 30., 300) and len(bpy.context.scene.objects) == 1
            and all(o.type == 'ARMATURE' for o in bpy.context.scene.objects),
            'Original walk FBX must contain a single armature and the complete source clock')

    rows = snapshot['bones']
    names = tuple(r['name'] for r in rows)
    bones = observed.bones
    require(len(names) == len(set(names)) == len(bones) and set(names) == set(bones)
            and all(r['parent'] == bones[r['name']]['parent'] for r in rows),
            'Original walk FBX skeleton hierarchy differs')
    rest_world = matrix(snapshot['armature_rest_world'])
    bind_error = delta(matrix_values(rest_world), matrix_values(observed.neutral_armature))
    require(bind_error <= LIMITS['armature_matrix'], 'Original walk FBX armature bind must remain neutral')
    rests = [matrix(r['matrix']) for r in rows]
    bone_bind_error = max(delta(matrix_values(rest_world @ rest), bones[name]['rest_world'])
                          for name, rest in zip(names, rests, strict=True))
    require(bone_bind_error <= LIMITS['fbx_bind_bone_matrix'],
            'Original walk FBX bone bind differs from exact neutral')

    lookup = {name: i for i, name in enumerate(names)}
    parents = [lookup[r['parent']] if r['parent'] else None for r in rows]
    local_rests = [rest.translation if parent is None else (rests[parent].inverted() @ rest).translation
                   for rest, parent in zip(rests, parents, strict=True)]
    hips = [rest_world @ Vector(rows[lookup[name]]['head']) for name in ('upperleg01.L', 'upperleg01.R')]
    head = rest_world @ Vector(rows[lookup['head']]['head'])
    source_height = (head - (hips[0] + hips[1]) / 2).length
    source_scale = rest_world.to_scale()[0]
    require(source_height > .1 and source_scale > 0, 'Original walk FBX root landmarks or scale differ')

    armature_error = pose_error = local_translation = local_scale = 0.
    expected_world = matrix_values(observed.posed_armature)
    for i, frame in enumerate(snapshot['frames']):
        require(frame['frame'] == i + 2 and len(frame['poses']) == len(names),
                'Original walk FBX frame sequence differs')
        world_values = frame['armature_world']
        world = matrix(world_values)
        armature_error = max(armature_error, delta(world_values, expected_world),
                             delta(world_values, observed.armature_timeline[i]))
        armature_poses = [matrix(pose) for pose in frame['poses']]
        inverse_parents = {index: armature_poses[index].inverted()
                           for index in set(parents) - {None}}
        for name, parent, pose, rest in zip(names, parents, armature_poses, local_rests, strict=True):
            local = pose if parent is None else inverse_parents[parent] @ pose
            local_translation = max(local_translation, (local.translation - rest).length)
            local_scale = max(local_scale, max(abs(x - 1.) for x in local.to_scale()))
            pose_error = max(pose_error, delta(matrix_values(world @ pose), observed.bone_timeline[i][name]))
    relative_translation = local_translation / (source_height / source_scale)
    require(relative_translation <= 1e-5,
            'Original walk FBX armature offset folded into an unsupported local bone translation')
    require(local_scale <= 1e-4, 'Original walk FBX local scale exceeds the retarget limit')
    require(armature_error <= LIMITS['armature_matrix'], 'Original walk FBX armature offset changed')
    require(pose_error <= LIMITS['fbx_world_pose_matrix'], 'Original walk FBX poses differ from the saved review')
    return {
        'import_clock': [2, 301, 30],
        'virtual_import_frame': 302,
        'virtual_frame_stored': False,
        'armature_only': True,
        'neutral_armature_bind_residual': bind_error,
        'neutral_bones_world_bind_residual': bone_bind_error,
        'max_animated_armature_export_residual': armature_error,
        'max_world_pose_residual': pose_error,
        'max_bone_local_translation_m': local_translation,
        'max_bone_local_translation_ratio': relative_translation,
        'max_bone_local_scale_delta': local_scale,
        'exact_full_timeline_compared': True,
    }, record


def verify_source(bpy: Any, root: Path, job: dict) -> dict:
    """Independently reopen the exact staged originals, walk scene, and FBX."""
    project, declared, pins = _checked_inputs(root, job)
    require(all(not canonical_path(root, name).exists() for name in (REPORT, SNAPSHOT)),
            'Refuse to replace original walk verification evidence')
    try:
        frame, human, rig, targets = measure(bpy, root, project, pins['candidate.blend'])
        check_frame(frame, declared)
        observed = observe_saved(bpy, canonical_path(root, 'original_walk.blend'), frame, human, rig, targets)
        gates = contact_gates(observed.metrics)
        require(all(gates.values()), 'Original walk contact or knee check exceeded its technical bound')
        unchanged(root, pins)
        fbx, snapshot = _verify_fbx(bpy, root, pins['original_walk.fbx'], observed)
        unchanged(root, pins)
        report = write_document(root, REPORT, {
            'schema_version': 1,
            'policy': 'UCC_ORIGINAL_WALK_VERIFICATION_V1',
            'status': STATUS,
            'request_sha256': pins['idle_inspection_request.json'],
            'walk_request_sha256': pins['walk_authoring_request.json'],
            'target': frame['target'],
            'input_sha256': pins,
            'source_snapshot': snapshot,
            'saved_bake': observed.metrics,
            'fbx_reimport': fbx,
            'technical_contact_checks': gates,
            'limits': LIMITS,
            'armature_root_offset_m': [0., 0., -.045],
            'root_motion': 'IN_PLACE',
            'nominal_ground_speed_m_s': .650,
            'staged_inputs_preserved': True,
            'owner_visual_review_performed': False,
            'visual_quality_approved': False,
            'usable_action_approved': False,
            'target_registered': False,
            'engine_imported': False,
            'source_redistribution_authorized': False,
        })
        return {'status': STATUS, 'outputs': {
            record['name']: {'bytes': record['bytes'], 'sha256': record['sha256']}
            for record in (report, snapshot)
        }}
    finally:
        unchanged(root, pins)
