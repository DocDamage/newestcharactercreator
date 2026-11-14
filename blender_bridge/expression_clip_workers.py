"""Real private expression Action/cache and independent full-frame verification."""
import json
from pathlib import Path

from blender_bridge.expression_clip_policy import POLICY, check_inputs
from blender_bridge.expression_clip_action import source_intake, saved_intake, create_action, peaks, linear_weight
from blender_bridge.expression_existing import canonical_keys
from blender_bridge.expression_geometry import source_state
from blender_bridge.expression_clip_surface import measure_frame, SkinWriter, read_cache
from blender_bridge.face_geometry import evaluated
from blender_bridge.face_operations import state_digest
from blender_bridge.face_policy import digest, read_json


def reference(bpy, root: Path, plan: dict) -> tuple:
    bpy.ops.wm.open_mainfile(filepath=str(root/'candidate.blend'), load_ui=False)
    human, rig, _, targets = source_intake(bpy)
    loaded, support, race, _ = canonical_keys(root, human, targets)
    baseline = source_state(bpy, human, rig, targets, strip_expression=True)
    neutral = source_state(bpy, human, rig, targets)
    original = evaluated(bpy, human, full=True)
    values = peaks(plan['parameters'], race); union = set().union(*support.values())
    hip = list((rig.matrix_world @ rig.pose.bones['upperleg01.L'].head
                + rig.matrix_world @ rig.pose.bones['upperleg01.R'].head)*.5)
    return human, rig, targets, loaded, baseline, neutral, original, values, union, hip


def report(options: dict, neutral: dict, rows: list, world: list, hip: list, motion_sha: str) -> dict:
    return {'schema_version': 1, 'policy': POLICY, 'master_sha256': options['master_sha256'],
            'clip_sha256': options['clip_sha256'], 'motion_sha256': motion_sha,
            'neutral_state_sha256': state_digest(neutral), 'world_matrix': world, 'hip_world': hip,
            'frame_count': 25, 'fps': 24, 'keyframes': [1, 13, 25], 'frames': rows,
            'exact_neutral_endpoints': True, 'visual_quality_approved': False, 'engine_import_verified': False}


def cache_manifest(root: Path, options: dict, rows: list, world: list, hip: list,
                     motion_sha: str, report_sha: str, packed_frames: list) -> dict:
    binary = root/'expression_skin.bin'
    return {'schema_version': 1, 'status': 'VERIFIED_EXPRESSION_SKIN_CACHE_V1',
            'bindings': {'master_sha256': options['master_sha256'], 'clip_sha256': options['clip_sha256'],
                         'motion_sha256': motion_sha, 'motion_report_sha256': report_sha},
            'coordinate_space': 'BLENDER_LOCAL_Z_UP', 'world_matrix': world, 'fps': 24,
            'source_first_frame': 1, 'frame_count': 25, 'vertex_count': 13380, 'triangle_count': 26756,
            'frames': packed_frames, 'geometry': {'name': binary.name, 'bytes': binary.stat().st_size,
                                                 'sha256': digest(binary)},
            'animation_visual_quality_verified': False, 'engine_import_verified': False}


def stage_clip(bpy, root: Path, options: dict) -> dict:
    plan = check_inputs(root, options)
    outputs = [root/name for name in ('expression_motion.blend', 'expression_motion.json',
                                     'expression_skin.bin', 'expression_skin.json')]
    if any(p.exists() or p.is_symlink() for p in outputs):
        raise ValueError('Expression clip refuses to overwrite private outputs')
    human, rig, targets, loaded, baseline, neutral, original, values, support, hip = reference(bpy, root, plan)
    create_action(bpy, human, values)
    saved_intake(bpy, values); canonical_keys(root, human, targets)
    if source_state(bpy, human, rig, targets) != neutral:
        raise ValueError('Creating the expression Action changed neutral character state')
    bpy.ops.wm.save_as_mainfile(filepath=str(outputs[0]), compress=False)
    motion_sha = digest(outputs[0]); world = [float(x) for row in human.matrix_world for x in row]
    rows = []; writer = SkinWriter(outputs[2], hip)
    try:
        for frame in range(1, 26):
            bpy.context.scene.frame_set(frame); bpy.context.view_layer.update()
            raw, row = measure_frame(bpy, human, rig, targets, frame, values, loaded, baseline, original, support)
            writer.append(raw, row); rows.append(row)
    finally: writer.close()
    bpy.context.scene.frame_set(1); bpy.context.view_layer.update()
    if source_state(bpy, human, rig, targets) != neutral:
        raise ValueError('Full expression sequence did not restore neutral state')
    result = report(options, neutral, rows, world, hip, motion_sha)
    with outputs[1].open('x', encoding='utf-8') as stream: json.dump(result, stream, allow_nan=False)
    manifest = cache_manifest(root, options, rows, world, hip, motion_sha, digest(outputs[1]), writer.frames)
    with outputs[3].open('x', encoding='utf-8') as stream: json.dump(manifest, stream, allow_nan=False)
    check_inputs(root, options)
    return {'schema_version': 1, 'policy': POLICY, 'master_sha256': options['master_sha256'],
            'clip_sha256': options['clip_sha256'], 'motion_sha256': motion_sha,
            'motion_report_sha256': digest(outputs[1]), 'cache_manifest_sha256': digest(outputs[3]),
            'cache_sha256': digest(outputs[2]), 'frame_count': 25,
            'visual_quality_approved': False, 'engine_import_verified': False}


def verify_clip(bpy, root: Path, options: dict) -> dict:
    plan = check_inputs(root, options, verify=True)
    human, rig, targets, loaded, baseline, neutral, original, values, support, hip = reference(bpy, root, plan)
    # Reject structural saved-scene faults before the longer full traversal.
    # This is observation only: no frame change, value reset or rig repair.
    bpy.ops.wm.open_mainfile(filepath=str(root/'expression_motion.blend'), load_ui=False)
    human, rig, _, targets = saved_intake(bpy, values)
    canonical_keys(root, human, targets)
    if source_state(bpy, human, rig, targets) != neutral:
        raise ValueError('Saved expression scene changed neutral state before evaluation')
    human, rig, targets, loaded, baseline, neutral, original, values, support, hip = reference(bpy, root, plan)
    rows = []
    for frame in range(1, 26):
        bpy.context.scene.frame_set(frame)
        for pair, key in loaded.items(): key.value = linear_weight(values[pair], frame)
        bpy.context.view_layer.update()
        _, row = measure_frame(bpy, human, rig, targets, frame, values, loaded, baseline, original, support)
        rows.append(row)
    for key in loaded.values(): key.value = 0.
    bpy.context.view_layer.update()
    if source_state(bpy, human, rig, targets) != neutral:
        raise ValueError('Independent reference did not restore exact source state')
    world = [float(x) for row in human.matrix_world for x in row]
    supplied = read_json(root/'expression_motion.json', options['motion_report_sha256'], 4*1024*1024)
    expected = report(options, neutral, rows, world, hip, options['motion_sha256'])
    if state_digest(supplied) != state_digest(expected):
        raise ValueError('Expression report differs from independent full-frame source reproduction')
    manifest = read_json(root/'expression_skin.json', options['cache_manifest_sha256'], 4*1024*1024)
    raw_frames = read_cache(root/'expression_skin.bin', manifest)
    canonical_manifest = cache_manifest(root, options, rows, world, hip, options['motion_sha256'],
                                         options['motion_report_sha256'], manifest['frames'])
    if state_digest(manifest) != state_digest(canonical_manifest):
        raise ValueError('Expression cache manifest bindings, coverage or declarations differ')
    bpy.ops.wm.open_mainfile(filepath=str(root/'expression_motion.blend'), load_ui=False)
    human, rig, _, targets = saved_intake(bpy, values)
    loaded, _, _, _ = canonical_keys(root, human, targets)
    if source_state(bpy, human, rig, targets) != neutral:
        raise ValueError('Saved expression scene changed neutral state before evaluation')
    for frame in range(1, 26):
        bpy.context.scene.frame_set(frame); bpy.context.view_layer.update()
        raw, row = measure_frame(bpy, human, rig, targets, frame, values, loaded, baseline, original, support)
        if row != rows[frame-1] or raw != raw_frames[frame-1]:
            raise ValueError('Saved expression frame/cache differs from independent exact reference')
        packed = manifest['frames'][frame-1]
        expected_packed = {'frame': frame, 'offset': packed['offset'], 'compressed_bytes': packed['compressed_bytes'],
                           'raw_sha256': row['raw_sha256'], 'skin_sha256': row['skin_sha256'], 'hip_world': hip}
        if state_digest(packed) != state_digest(expected_packed):
            raise ValueError('Expression cache frame declarations differ from the independent saved surface')
    bpy.context.scene.frame_set(1); bpy.context.view_layer.update()
    saved_intake(bpy, values)
    if source_state(bpy, human, rig, targets) != neutral:
        raise ValueError('Saved expression sequence did not restore source neutral state')
    check_inputs(root, options, verify=True)
    return {'schema_version': 1, 'policy': POLICY, 'bindings': dict(options), 'verified_reopen': True,
            'reference_frames': 25, 'saved_frames': 25, 'cache_frames': 25,
            'exact_neutral_endpoints': True, 'visual_quality_approved': False, 'engine_import_verified': False}
