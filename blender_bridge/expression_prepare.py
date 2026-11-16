"""Two-worker neutral preparation; no project publication or receipt relabeling."""
import json
from pathlib import Path

from blender_bridge.expression_policy import POLICY, TARGETS, keyname, check_inputs
from blender_bridge.expression_geometry import build_keys, exercise, source_state
from blender_bridge.face_geometry import intake
from blender_bridge.face_operations import state_digest
from blender_bridge.face_policy import digest, read_json


def reproduce(bpy, root: Path, *, manual: bool) -> tuple:
    bpy.ops.wm.open_mainfile(filepath=str(root/'candidate.blend'), load_ui=False)
    human, rig, _, targets = intake(bpy)
    baseline = source_state(bpy, human, rig, targets)
    loaded, support, race, scale = build_keys(bpy, root, human, targets, manual=manual)
    if source_state(bpy, human, rig, targets, strip_expression=True) != baseline:
        raise ValueError('Adding neutral expression keys changed the original character')
    samples = exercise(bpy, human, rig, targets, loaded, support, race, baseline)
    observation = source_state(bpy, human, rig, targets)
    return human, rig, targets, baseline, observation, samples, race, scale


def report_for(bpy, options, baseline, observation, samples, race, scale, scene_sha) -> dict:
    return {'schema_version': 1, 'policy': POLICY, 'recipe_sha256': options['recipe_sha256'],
            'source_master_sha256': options['master_sha256'], 'prepared_sha256': scene_sha,
            'blender_version': bpy.app.version_string, 'baseline': baseline, 'observation': observation,
            'samples': samples, 'race_weights': race, 'scale_factor': scale,
            'visual_quality_approved': False, 'engine_import_verified': False}


def stage_preparation(bpy, root: Path, options: dict) -> dict:
    check_inputs(root, options)
    scene = root/'expression_human.blend'; report = root/'expression_report.json'
    if any(p.exists() or p.is_symlink() for p in (scene, report)):
        raise ValueError('Expression preparation refuses to overwrite outputs')
    human, rig, targets, baseline, observation, samples, race, scale = reproduce(bpy, root, manual=False)
    bpy.ops.wm.save_as_mainfile(filepath=str(scene), compress=False)
    if source_state(bpy, human, rig, targets) != observation:
        raise ValueError('Saving changed the prepared expression character')
    check_inputs(root, options)
    result = report_for(bpy, options, baseline, observation, samples, race, scale, digest(scene))
    with report.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    return result


def verify_preparation(bpy, root: Path, options: dict) -> dict:
    check_inputs(root, options, verify=True)
    supplied = read_json(root/'expression_report.json', options['report_sha256'], 4*1024*1024)
    _, _, _, baseline, expected, samples, race, scale = reproduce(bpy, root, manual=True)
    report = report_for(bpy, options, baseline, expected, samples, race, scale, options['prepared_sha256'])
    if (type(supplied) is not dict or type(supplied.get('schema_version')) is not int
            or state_digest(supplied) != state_digest(report)):
        raise ValueError('Expression report differs from independent raw-target reconstruction')
    bpy.ops.wm.open_mainfile(filepath=str(root/'expression_human.blend'), load_ui=False)
    human, rig, _, targets = intake(bpy)
    # Observe first: do not reset values, recreate keys, or refit the saved rig.
    if source_state(bpy, human, rig, targets) != expected:
        raise ValueError('Saved expression master differs from independently reconstructed neutral state')
    loaded = {(r, f): human.data.shape_keys.key_blocks[keyname(r, f)] for r, f, _ in TARGETS}
    # Reuse declared indices, not key coordinates, to constrain saved motion.
    from blender_bridge.expression_geometry import target_rows
    from blender_bridge.expression_policy import filename
    support = {}
    for r, f, _ in TARGETS:
        support.setdefault(r, set()).update(i for i, d in target_rows(root/filename(r, f)).items() if any(d))
    if exercise(bpy, human, rig, targets, loaded, support, race, baseline) != samples:
        raise ValueError('Saved expression motion differs from independent original-source samples')
    check_inputs(root, options, verify=True)
    return {'schema_version': 1, 'policy': POLICY, 'verified_reopen': True,
            'source_master_sha256': options['master_sha256'], 'prepared_sha256': options['prepared_sha256'],
            'recipe_sha256': options['recipe_sha256'], 'reference_samples': 20, 'saved_samples': 20,
            'exact_neutral_restoration': True, 'visual_quality_approved': False, 'engine_import_verified': False}
