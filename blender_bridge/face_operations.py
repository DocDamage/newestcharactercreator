"""Private real-MPFB facial staging and independent saved-scene reproduction.

No operation here promotes a master or edits a project. Verification rebuilds
the expected state from the bound original, then observes the saved result
without reapplying targets or repairing its rig.
"""
from hashlib import sha256
import gzip
import json
import math
from pathlib import Path

from blender_bridge.face_policy import POLICY, TARGETS, check_inputs, digest, read_json
from blender_bridge.face_geometry import (
    intake, own_keys, invariant_state, rest_state, canonical_rest,
    evaluated, points_digest, float32, key_state,
)


def state_digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def declared_vertices(root: Path) -> set[int]:
    indices = set()
    for _, name, _ in TARGETS:
        seen = set()
        with gzip.open(root/(name+'.target.gz'), 'rt', encoding='utf-8') as stream:
            for line in stream:
                if not line.strip() or line.lstrip().startswith('#'):
                    continue
                words = line.split()
                if len(words) != 4:
                    raise ValueError('Invalid pinned target record')
                index = int(words[0]); delta = [float(v) for v in words[1:]]
                if index in seen or not 0 <= index < 19158 or not all(math.isfinite(v) for v in delta):
                    raise ValueError('Invalid or duplicate pinned target index')
                seen.add(index)
                if any(delta):
                    indices.add(index)
    if not indices:
        raise ValueError('Empty facial target region')
    return indices


def observe(bpy, human, rig, targets) -> dict:
    full = evaluated(bpy, human, full=True)
    visible = evaluated(bpy, human)
    return {'invariants_sha256': state_digest(invariant_state(bpy, human, rig, targets)),
            'rest_sha256': state_digest(rest_state(rig)),
            'own_keys': {name: key_state(human.data.shape_keys.key_blocks[name]) for _, name, _ in TARGETS},
            'full_vertices': len(full), 'visible_vertices': len(visible),
            'full_coordinates_sha256': points_digest(full), 'visible_coordinates_sha256': points_digest(visible)}


def reproduce(bpy, root: Path, recipe: dict) -> tuple:
    bpy.ops.wm.open_mainfile(filepath=str(root/'candidate.blend'), load_ui=False)
    human, rig, service, targets = intake(bpy)
    before = invariant_state(bpy, human, rig, targets)
    original_rest = rest_state(rig)
    original_points = evaluated(bpy, human, full=True)
    keys = own_keys(human, targets, root, create=True)
    original_values = [float(key.value) for key in keys]
    service.refit(human)
    bpy.context.view_layer.update()
    canonical_rest(original_rest, rest_state(rig))
    desired = [t['weight'] for t in recipe['targets']]
    for key, value in zip(keys, desired):
        key.value = value
    service.refit(human)
    bpy.context.view_layer.update()
    if any(key.value != float32(value) for key, value in zip(keys, desired)):
        raise ValueError('MPFB did not persist exact float32 facial target strengths')
    if invariant_state(bpy, human, rig, targets) != before:
        raise ValueError('Facial refit changed unrelated keys, macros, topology, weights, UV/materials or transforms')
    final_points = evaluated(bpy, human, full=True)
    if len(final_points) != len(original_points) or len(final_points) != 19158:
        raise ValueError('Facial refit changed evaluated full-mesh indexing')
    affected = declared_vertices(root)
    distances = [math.dist(a, b) for a, b in zip(original_points, final_points)]
    span = max(p[2] for p in original_points)-min(p[2] for p in original_points)
    if not .1 <= span <= 100:
        raise ValueError('Facial operation rejects unsupported character units/scale')
    if max(distances) > min(.08, span*.05):
        raise ValueError('Facial displacement exceeds the bounded family policy')
    if max(d for i, d in enumerate(distances) if i not in affected) > 1e-6:
        raise ValueError('Facial refit moved geometry outside the declared target region')
    observation = observe(bpy, human, rig, targets)
    metrics = {'declared_target_vertices': len(affected), 'maximum_world_displacement': max(distances),
               'moved_vertices_over_1um': sum(d > 1e-6 for d in distances),
               'geometry_changed': points_digest(original_points) != points_digest(final_points),
               'target_values_changed': original_values != [float32(v) for v in desired]}
    return human, rig, targets, observation, metrics


def stage_face(bpy, root: Path, options: dict) -> dict:
    plan = check_inputs(root, options)
    scene = root/'faced_human.blend'; report_path = root/'face_report.json'
    if scene.exists() or scene.is_symlink() or report_path.exists() or report_path.is_symlink():
        raise ValueError('Facial stage refuses to overwrite existing outputs')
    human, rig, targets, observation, metrics = reproduce(bpy, root, plan)
    bpy.ops.wm.save_as_mainfile(filepath=str(scene), compress=False)
    # Saving must not alter the observed character either.
    if observe(bpy, human, rig, targets) != observation:
        raise ValueError('Saving changed the staged facial character')
    check_inputs(root, options)
    report = {'schema_version': 1, 'policy': POLICY, 'recipe_sha256': options['recipe_sha256'],
              'source_master_sha256': options['master_sha256'], 'scene_sha256': digest(scene),
              'blender_version': bpy.app.version_string, 'observation': observation, 'metrics': metrics,
              'visual_quality_approved': False, 'engine_import_verified': False}
    with report_path.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    return report


def verify_face(bpy, root: Path, options: dict) -> dict:
    plan = check_inputs(root, options, verify=True)
    report = read_json(root/'face_report.json', options['report_sha256'], 4*1024*1024)
    _, _, _, expected, metrics = reproduce(bpy, root, plan)
    expected_report = {'schema_version': 1, 'policy': POLICY, 'recipe_sha256': options['recipe_sha256'],
                       'source_master_sha256': options['master_sha256'], 'scene_sha256': options['face_sha256'],
                       'blender_version': bpy.app.version_string, 'observation': expected, 'metrics': metrics,
                       'visual_quality_approved': False, 'engine_import_verified': False}
    if (type(report) is not dict or type(report.get('schema_version')) is not int
            or state_digest(report) != state_digest(expected_report)):
        raise ValueError('Facial report differs from independent original-source reproduction')
    bpy.ops.wm.open_mainfile(filepath=str(root/'faced_human.blend'), load_ui=False)
    human, rig, _, targets = intake(bpy)
    # Canonical reference keys are temporary and removed. Never set a saved
    # result's target values or refit its rig before observing it.
    keys = own_keys(human, targets, root, create=False)
    if any(k.value != float32(t['weight']) for k, t in zip(keys, plan['targets'])):
        raise ValueError('Saved facial target strengths differ from the bound recipe')
    if observe(bpy, human, rig, targets) != expected:
        raise ValueError('Saved facial geometry/rig/skin differs from independent reproduction')
    check_inputs(root, options, verify=True)
    return {'schema_version': 1, 'policy': POLICY, 'verified_reopen': True,
            'source_master_sha256': options['master_sha256'], 'scene_sha256': options['face_sha256'],
            'recipe_sha256': options['recipe_sha256'], 'geometry_changed': metrics['geometry_changed'],
            'target_values_changed': metrics['target_values_changed'],
            'visual_quality_approved': False, 'engine_import_verified': False}
