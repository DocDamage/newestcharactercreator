"""Observe prepared keys before any changes; compare raw pinned target math."""
from array import array
from hashlib import sha256
from pathlib import Path

from blender_bridge.expression_policy import POLICY, TARGETS, PREFIX, filename, keyname, check_inputs
from blender_bridge.expression_geometry import macro_context, target_rows, source_state, exercise
from blender_bridge.face_geometry import intake, coordinates, key_settings, key_state, float32
from blender_bridge.face_operations import state_digest


def canonical_keys(root: Path, human, targets) -> tuple:
    """Never create reference keys, reset values, or repair a saved scene."""
    keys = human.data.shape_keys.key_blocks
    expected_names = {keyname(r, f) for r, f, _ in TARGETS}
    if {k.name for k in keys if k.name.startswith(PREFIX)} != expected_names:
        raise ValueError('Prepared expressions require exactly the twelve reserved keys with no extras')
    basis = keys.get('Basis')
    if basis is None or len(basis.data) != 19158:
        raise ValueError('Prepared expressions require the complete pinned Basis')
    scale, race = macro_context(human, targets)
    base = array('f', [0.])*(len(basis.data)*3); basis.data.foreach_get('co', base)
    loaded = {}; support = {}
    settings = {'mute': False, 'interpolation': 'KEY_LINEAR', 'slider_min': 0., 'slider_max': 1., 'vertex_group': ''}
    for role, family, _ in TARGETS:
        name = keyname(role, family); key = keys[name]
        if key.value != 0. or key.relative_key != basis or key_settings(key) != settings:
            raise ValueError('Prepared expression key is not canonical and neutral: '+name)
        rows = target_rows(root/filename(role, family)); expected = array('f', base)
        for index, delta in rows.items():
            for axis in range(3):
                expected[index*3+axis] = float32(base[index*3+axis]+delta[axis]*scale)
        if coordinates(key) != sha256(expected.tobytes()).hexdigest():
            raise ValueError('Prepared expression key differs from the pinned target coordinates: '+name)
        support.setdefault(role, set()).update(i for i, d in rows.items() if any(d))
        loaded[(role, family)] = key
    return loaded, support, race, scale


def inspect_existing(bpy, root: Path, options: dict) -> dict:
    check_inputs(root, options)
    bpy.ops.wm.open_mainfile(filepath=str(root/'candidate.blend'), load_ui=False)
    human, rig, _, targets = intake(bpy)
    loaded, support, race, scale = canonical_keys(root, human, targets)
    observation = source_state(bpy, human, rig, targets)
    baseline = source_state(bpy, human, rig, targets, strip_expression=True)
    samples = exercise(bpy, human, rig, targets, loaded, support, race, baseline)
    if source_state(bpy, human, rig, targets) != observation:
        raise ValueError('Prepared expression inspection changed neutral state')
    canonical_keys(root, human, targets)
    check_inputs(root, options)
    return {'schema_version': 1, 'policy': POLICY, 'master_sha256': options['master_sha256'],
            'recipe_sha256': options['recipe_sha256'], 'blender_version': bpy.app.version_string,
            'observation': observation, 'expression_keys_sha256': state_digest({k.name: key_state(k) for k in loaded.values()}),
            'samples': samples, 'race_weights': race, 'scale_factor': scale, 'sample_count': 20,
            'exact_neutral_restoration': True, 'visual_quality_approved': False, 'engine_import_verified': False}
