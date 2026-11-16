"""Write actual skinned hand assets; independently reconstruct and reopen them.

Only scalar counts, hashes and bounded pose observations leave these workers.
Mesh coordinates, weights, complete poses and scenes stay in local job files.
"""
import math
from pathlib import Path

from blender_bridge.face_geometry import evaluated, points_digest
from blender_bridge.hand_geometry import (
    source_context, skin_region, expected_asset, observe_asset, SKIN_FIELDS,
)
from blender_bridge.hand_policy import POLICY, TARGETS, SLOT, check_inputs, digest, read_json, state_digest


def _properties(recipe: dict, variant: str, target_sha256: str) -> dict:
    return {'ucc_hand_policy': POLICY, 'ucc_hand_source_sha256': recipe['bindings']['master_sha256'],
            'ucc_hand_variant': variant, 'ucc_hand_slot': SLOT,
            'ucc_hand_target_sha256': target_sha256, 'ucc_hand_strength': .25}


def _source(bpy, root: Path, variant: str, *, source_file: str = 'candidate.blend'):
    human, rig, service, targets = source_context(bpy, root/source_file)
    region = skin_region(human, rig, root)
    before = evaluated(bpy, human, full=True)
    _, filename, _ = next(row for row in TARGETS if row[0] == variant)
    key = targets.load_target(human, str(root/filename), weight=.25)
    if key.name != filename.removesuffix('.target.gz') or key.value != .25:
        raise ValueError('MPFB did not create the exact declared hand target')
    coordinates = [tuple(v.co) for v in key.data]
    service.refit(human)
    expected = expected_asset(bpy, human, rig, region, coordinates)
    after = evaluated(bpy, human, full=True)
    distances = [math.dist(before[i], after[i]) for i in region['ids']]
    if (sum(d > 1e-6 for d in distances) <= 100 or max(distances) >= .03
            or max(math.dist(before[i], after[i]) for i in region['border']) >= 1e-6):
        raise ValueError('Actual hand variant fails bounded displacement or fixed-border checks')
    metrics = {'vertices': 1747, 'polygons': 1735, 'border_vertices': 22, 'joint_helper_vertices': 112,
               'changed_skin_vertices_over_1um': sum(d > 1e-6 for d in distances),
               'maximum_world_displacement': max(distances), 'actual_source_skin': True}
    return human, rig, region, expected, metrics


def _write_asset(bpy, path: Path, human, rig, expected: dict, properties: dict):
    from mathutils import Matrix
    if path.exists() or path.is_symlink():
        raise ValueError('Hand asset stage refuses to overwrite an existing file')
    mesh = bpy.data.meshes.new('UCC compatible left hand')
    mesh.from_pydata(expected['points'], [], expected['faces']); mesh.update(calc_edges=True)
    for material in human.data.materials:
        mesh.materials.append(material)
    for polygon, (smooth, material) in zip(mesh.polygons, expected['face_shading']):
        polygon.use_smooth = smooth; polygon.material_index = material
    for old_layer in human.data.uv_layers:
        layer = mesh.uv_layers.new(name=old_layer.name)
        for polygon, uv in zip(mesh.polygons, expected['uv']):
            for loop, point in zip(polygon.loop_indices, uv[old_layer.name]):
                layer.data[loop].uv = point
    if len(mesh.uv_layers):
        mesh.uv_layers.active_index = expected['uv_active_index']
    for name, kind, domain, field, values in (
        ('ucc_source_vertex_id', 'INT', 'POINT', 'value', expected['source_ids']),
        ('ucc_source_polygon_id', 'INT', 'FACE', 'value', expected['polygon_ids']),
        ('ucc_reference_key_coordinates', 'FLOAT_VECTOR', 'POINT', 'vector',
         [x for point in expected['key_coordinates'] for x in point]),
    ):
        attribute = mesh.attributes.new(name, kind, domain); attribute.data.foreach_set(field, values)
    obj = bpy.data.objects.new('UCC left hand asset', mesh)
    for name in expected['groups']:
        obj.vertex_groups.new(name=name)
    for index, assignments in enumerate(expected['weights']):
        for group, weight in assignments:
            obj.vertex_groups[group].add([index], weight, 'REPLACE')
    asset_rig = rig.copy(); asset_rig.data = rig.data.copy(); asset_rig.name = 'UCC hand asset rig'
    obj.parent = asset_rig; obj.matrix_parent_inverse = Matrix.Identity(4); obj.matrix_world = Matrix.Identity(4)
    mod = obj.modifiers.new('UCC source skin', 'ARMATURE'); mod.object = asset_rig
    for field in SKIN_FIELDS:
        setattr(mod, field, expected['skin'][field])
    for name, value in properties.items():
        obj[name] = value
    if state_digest(observe_asset(bpy, obj, asset_rig)) != state_digest(expected):
        raise ValueError('New standalone hand lost original mesh/UV/material/weight/bind data')
    scene = bpy.data.scenes.new('UCC standalone hand asset')
    scene.collection.objects.link(asset_rig); scene.collection.objects.link(obj)
    bpy.data.libraries.write(str(path), {scene}, path_remap='NONE', fake_user=False, compress=False)
    if not path.is_file() or path.stat().st_size < 1024:
        raise ValueError('Blender produced no real standalone hand scene')


def _report(bpy, options: dict, rows: dict) -> dict:
    return {'schema_version': 1, 'policy': POLICY, 'recipe_sha256': options['recipe_sha256'],
            'source_master_sha256': options['master_sha256'], 'blender_version': bpy.app.version_string,
            'assets': rows, 'visual_quality_approved': False, 'engine_import_verified': False}


def build_assets(bpy, root: Path, options: dict) -> dict:
    import json
    recipe = check_inputs(root, options); rows = {}
    report_path = root/'hand_assets_report.json'
    if report_path.exists() or report_path.is_symlink():
        raise ValueError('Hand assets report already exists')
    for variant, _, target_sha in TARGETS:
        human, rig, _, expected, metrics = _source(bpy, root, variant)
        destination = root/('hand-'+variant+'.blend')
        _write_asset(bpy, destination, human, rig, expected, _properties(recipe, variant, target_sha))
        rows[variant] = {'scene_sha256': digest(destination), 'observation_sha256': state_digest(expected),
                         'metrics': metrics}
    check_inputs(root, options)
    report = _report(bpy, options, rows)
    with report_path.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    return report


def _asset_objects(bpy):
    objects = list(bpy.data.objects)
    meshes = [o for o in objects if o.type == 'MESH']; rigs = [o for o in objects if o.type == 'ARMATURE']
    if len(objects) != 2 or len(meshes) != 1 or len(rigs) != 1:
        raise ValueError('Hand asset contains extra objects or hidden whole-body/helper meshes')
    return meshes[0], rigs[0]


def check_saved_asset(bpy, path: Path, expected: dict, properties: dict):
    bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=False)
    obj, rig = _asset_objects(bpy)
    if state_digest(observe_asset(bpy, obj, rig)) != state_digest(expected):
        raise ValueError('Saved hand asset differs from independent original-source reconstruction')
    actual_properties = {key: obj.get(key) for key in properties}
    if state_digest(actual_properties) != state_digest(properties):
        raise ValueError('Saved hand provenance or strength differs from the original source')
    if obj.name not in bpy.context.view_layer.objects:
        scenes = [s for s in bpy.data.scenes if obj.name in s.objects and rig.name in s.objects]
        if len(scenes) != 1 or bpy.context.window is None:
            raise ValueError('Standalone hand has no unambiguous evaluable scene')
        bpy.context.window.scene = scenes[0]
    return obj, rig


def verify_skin_poses(bpy, obj, rig) -> list[dict]:
    from mathutils import Quaternion
    baseline = evaluated(bpy, obj); initial = points_digest(baseline)
    state = state_digest(observe_asset(bpy, obj, rig)); results = []
    for name, axes in [('wrist.L', (0, 1, 2)), *[(f'finger{i}-1.L', (0,)) for i in range(1, 6)],
                       ('finger2-2.L', (0,)), ('finger5-2.L', (0,))]:
        for axis in axes:
            for angle in (-20, 20):
                bone = rig.pose.bones[name]; mode = bone.rotation_mode
                q, e, aa = bone.rotation_quaternion.copy(), bone.rotation_euler.copy(), tuple(bone.rotation_axis_angle)
                try:
                    vector = [0., 0., 0.]; vector[axis] = 1.
                    bone.rotation_mode = 'QUATERNION'; bone.rotation_quaternion = Quaternion(vector, math.radians(angle))
                    actual = evaluated(bpy, obj)
                    distances = [math.dist(a, b) for a, b in zip(baseline, actual)]
                    moved = sum(d > 1e-6 for d in distances)
                    if len(actual) != 1747 or moved < 16 or not 1e-6 < max(distances) < .5:
                        raise ValueError('Saved hand has ineffective or out-of-bounds real skin deformation')
                    results.append({'bone': name, 'axis': axis, 'degrees': angle,
                                    'moved_vertices_over_1um': moved, 'maximum_displacement': max(distances)})
                finally:
                    bone.rotation_quaternion = q; bone.rotation_euler = e
                    bone.rotation_axis_angle = aa; bone.rotation_mode = mode; bpy.context.view_layer.update()
                if points_digest(evaluated(bpy, obj)) != initial or state_digest(observe_asset(bpy, obj, rig)) != state:
                    raise ValueError('Hand pose check failed exact geometry/weight/rig restoration')
    if len(results) != 20:
        raise ValueError('Incomplete hand skin-pose coverage')
    return results


def verify_assets(bpy, root: Path, options: dict) -> dict:
    recipe = check_inputs(root, options, verify_assets=True)
    report = read_json(root/'hand_assets_report.json', options['assets_report_sha256'], 1024*1024)
    rows, poses = {}, {}
    for variant, _, target_sha in TARGETS:
        _, _, _, expected, metrics = _source(bpy, root, variant)
        rows[variant] = {'scene_sha256': options[variant+'_asset_sha256'],
                         'observation_sha256': state_digest(expected), 'metrics': metrics}
        obj, rig = check_saved_asset(bpy, root/('hand-'+variant+'.blend'), expected,
                                    _properties(recipe, variant, target_sha))
        poses[variant] = verify_skin_poses(bpy, obj, rig)
    if state_digest(report) != state_digest(_report(bpy, options, rows)):
        raise ValueError('Hand asset report differs from independent original-source reconstruction')
    check_inputs(root, options, verify_assets=True)
    return {'schema_version': 1, 'policy': POLICY, 'verified_reopen': True,
            'recipe_sha256': options['recipe_sha256'], 'source_master_sha256': options['master_sha256'],
            'assets': rows, 'skin_poses': poses, 'all40_restores_exact': True,
            'visual_quality_approved': False, 'engine_import_verified': False}
