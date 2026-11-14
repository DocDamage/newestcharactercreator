"""Independent real saved-scene reader for original-only CI; writes aggregates only."""
import argparse
from array import array
from hashlib import sha256
import json
import math
from pathlib import Path
import struct
import sys

import bpy
from mathutils import Matrix

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'src'), str(ROOT)]
from ucc.jobs.native_regional_skin_evidence import MODIFIERS, MASK_NAME, SOURCE_GROUPS


def require(condition, message):
    if not condition: raise RuntimeError(message)


def geometry(human):
    bpy.context.view_layer.update(); graph = bpy.context.evaluated_depsgraph_get()
    evaluated = human.evaluated_get(graph); mesh = evaluated.to_mesh()
    try:
        points = tuple(tuple(float(x) for x in v.co) for v in mesh.vertices)
        edges = tuple(sorted(tuple(sorted(e.vertices)) for e in mesh.edges))
        digest = sha256()
        for point in points:
            require(all(math.isfinite(x) for x in point), 'Independent reader found nonfinite skin')
            digest.update(struct.pack('<qqq', *(round(x*1000000) for x in point)))
        return points, edges, digest.hexdigest()
    finally: evaluated.to_mesh_clear()


def groups(human):
    names = tuple((g.index, g.name) for g in human.vertex_groups)
    rows = tuple(tuple((g.group, struct.pack('<f', g.weight)) for g in v.groups) for v in human.data.vertices)
    return names, rows


def group_digest(names, rows):
    digest = sha256()
    for index, name in names: digest.update(struct.pack('<I', index)+name.encode('utf-8')+b'\0')
    for index, memberships in enumerate(rows):
        digest.update(struct.pack('<II', index, len(memberships)))
        for group, value in memberships: digest.update(struct.pack('<I', group)+value)
    return digest.hexdigest()


def rest(rig):
    return tuple((b.name, b.parent.name if b.parent else None, b.use_deform,
                  tuple(float(x) for row in b.matrix_local for x in row)) for b in rig.data.bones)


def mesh_data(human):
    digest = sha256()
    values = array('f', [0.])*(len(human.data.vertices)*3); human.data.vertices.foreach_get('co', values)
    digest.update(values.tobytes())
    for key in human.data.shape_keys.key_blocks if human.data.shape_keys else ():
        digest.update(key.name.encode('utf-8')+b'\0'+struct.pack('<f', key.value))
        values = array('f', [0.])*(len(key.data)*3); key.data.foreach_get('co', values); digest.update(values.tobytes())
    return digest.hexdigest()


def modifier_state(mod):
    keys = ('use_vertex_groups', 'use_bone_envelopes', 'use_deform_preserve_volume', 'use_multi_modifier') if mod.type == 'ARMATURE' else ('mode', 'vertex_group', 'invert_vertex_group', 'threshold', 'use_smooth')
    return mod.name, mod.type, tuple(getattr(mod, key) for key in (*keys, 'show_viewport', 'show_render'))


def strain(points, edges, lengths):
    ratios = [math.dist(points[a], points[b])/length for (a, b), length in zip(edges, lengths) if length > 1e-9]
    require(bool(ratios) and .05 <= min(ratios) <= max(ratios) <= 4., 'Independent reader found out-of-bound strain')
    return min(ratios), max(ratios)


def verify(job: Path, output: Path):
    names = ('candidate.blend', 'review_motion.blend', 'target_timeline.json', 'native_mapping.json', 'source_snapshot.json')
    protected = {name: sha256((job/name).read_bytes()).hexdigest() for name in names}
    data = json.loads((job/'target_timeline.json').read_text(encoding='utf-8'))
    proof = data['skin_deformation']; count = data['source_frame_count']
    require(count == 300 and data['skin_deformation_policy'] == 'BOUND_REGIONAL_CORRECTIVE_SMOOTH_V2'
            and type(proof['schema_version']) is int and proof['schema_version'] == 2, 'Unexpected independent regional source')
    bpy.ops.wm.open_mainfile(filepath=str(job/'candidate.blend'), load_ui=False)
    human = next(o for o in bpy.data.objects if o.type == 'MESH' and len(o.data.vertices) > 100)
    rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    original, original_edges, original_sha = geometry(human)
    original_names, original_rows = groups(human); original_rest = rest(rig); original_mesh = mesh_data(human)
    original_mods = tuple(modifier_state(m) for m in human.modifiers)
    world = tuple(float(x) for row in rig.matrix_world for x in row)
    mesh_world = tuple(float(x) for row in human.matrix_world for x in row)
    require(original_sha == proof['source_neutral_sha256'] and group_digest(original_names, original_rows) == proof['source_vertex_groups_sha256'], 'Independent original skin/weight identity differs')
    group_indices = {index for index, name in original_names if name in SOURCE_GROUPS}
    require(len(group_indices) == 5 and all(rig.data.bones[name].use_deform for name in SOURCE_GROUPS), 'Independent source regions are not actual deform groups')
    expected_weights = [struct.pack('<f', min(1., sum(struct.unpack('<f', value)[0] for index, value in row if index in group_indices))) for row in original_rows]
    bpy.ops.wm.open_mainfile(filepath=str(job/'review_motion.blend'), load_ui=False)
    human = next(o for o in bpy.data.objects if o.type == 'MESH' and len(o.data.vertices) > 100)
    rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
    require(rest(rig) == original_rest and mesh_data(human) == original_mesh, 'Independent source rest/geometry/keys changed')
    require(tuple(float(x) for row in rig.matrix_world for x in row) == world and tuple(float(x) for row in human.matrix_world for x in row) == mesh_world, 'Independent source world transforms changed')
    saved_names, saved_rows = groups(human); mask_index = len(original_names)
    require(saved_names == (*original_names, (mask_index, MASK_NAME)) and rig.data.bones.get(MASK_NAME) is None, 'Independent source group order or mask bone differs')
    mask_hash = sha256(); weighted = 0
    for index, (old, saved, expected) in enumerate(zip(original_rows, saved_rows, expected_weights)):
        require(tuple(row for row in saved if row[0] != mask_index) == old, 'Independent original binary weight changed')
        selected = [v for g, v in saved if g == mask_index]
        require(len(selected) <= 1 and (selected[0] if selected else struct.pack('<f', 0.)) == expected, 'Independent mask is not the sum of original deform weights')
        weighted += struct.unpack('<f', expected)[0] > 0; mask_hash.update(struct.pack('<I', index)+expected)
    require(proof['region_mask'] == {'name': MASK_NAME, 'formula': 'MIN_ONE_SUM_ORIGINAL_DEFORM_WEIGHTS_V1', 'source_groups': SOURCE_GROUPS,
        'source_mesh_vertices': len(original_rows), 'weighted_vertices': weighted, 'weights_sha256': mask_hash.hexdigest()}, 'Independent mask metadata differs')
    mods = tuple(human.modifiers); owned = mods[-2:]
    require(tuple(modifier_state(m) for m in mods[:-2]) == original_mods and proof['modifiers'] == list(MODIFIERS), 'Independent original/owned layer order differs')
    for mod, expected in zip(owned, MODIFIERS):
        for key, value in expected.items():
            actual = mod.is_bind if key == 'is_bound' else getattr(mod, key)
            require(type(actual) is type(value) and actual == value, 'Independent exact layer setting differs')
    action = rig.animation_data.action; slot = rig.animation_data.action_slot
    require(list(action.frame_range) == [1., 300.] and not rig.animation_data.nla_tracks, 'Independent saved Action coverage differs')
    curves = [c for layer in action.layers for strip in layer.strips for bag in strip.channelbags for c in bag.fcurves]
    require(len(curves) == 59*4+3 and all(len(c.keyframe_points) == 300 and all(p.interpolation == 'LINEAR' and p.co.x == i for i, p in enumerate(c.keyframe_points, 1)) for c in curves), 'Independent saved key coverage differs')
    rig.animation_data.action = None
    for bone in rig.pose.bones: bone.matrix_basis = Matrix.Identity(4)
    neutral, edges, neutral_sha = geometry(human)
    require(edges == original_edges and neutral_sha == data['neutral_bind_skin_sha256'] and max(math.dist(a, b) for a, b in zip(neutral, original)) <= 1e-6, 'Independent neutral skin/topology changed')
    original_lengths = [math.dist(original[a], original[b]) for a, b in edges]
    bind_lengths = [math.dist(neutral[a], neutral[b]) for a, b in edges]
    diagonal = math.dist([min(p[i] for p in neutral) for i in range(3)], [max(p[i] for p in neutral) for i in range(3)])
    rig.animation_data.action = action; rig.animation_data.action_slot = slot
    for frame, row in enumerate(data['full_timeline_frames'], 1):
        bpy.context.scene.frame_set(frame); points, current_edges, skin_sha = geometry(human)
        require(current_edges == edges and skin_sha == row['evaluated_sha256'], 'Independent full-frame skin/topology differs')
        digest = sha256(struct.pack('<16q', *(round(x*1000000) for x in world)))
        for pair in data['mapped_pairs']:
            values = [float(x) for line in rig.matrix_world@rig.pose.bones[pair['target']].matrix for x in line]
            digest.update(struct.pack('<16q', *(round(x*1000000) for x in values)))
        require(digest.hexdigest() == row['target_pose_sha256'], 'Independent actual pose differs')
        for lengths, record in ((original_lengths, data['master_relative_frames'][frame-1]), (bind_lengths, data['bind_relative_frames'][frame-1])):
            low, high = strain(points, edges, lengths)
            require(abs(low-record['min_edge_length_ratio']) <= 1e-6 and abs(high-record['max_edge_stretch_ratio']) <= 1e-6, 'Independent actual strain differs')
        for mod in owned: mod.show_viewport = False
        try: raw, raw_edges, raw_sha = geometry(human)
        finally:
            for mod in owned: mod.show_viewport = True
        shifts = [math.dist(a, b) for a, b in zip(raw, points)]; correction = row['skin_correction']
        require(raw_edges == edges and raw_sha == correction['uncorrected_sha256'] and max(shifts) <= diagonal*.03 and abs(max(shifts)-correction['max_correction_local']) <= 1e-8 and sum(x > 1e-5 for x in shifts) == correction['corrected_vertices'], 'Independent original raw skin or correction cap differs')
    require(all(sha256((job/name).read_bytes()).hexdigest() == h for name, h in protected.items()), 'Independent reader changed input bytes')
    result = {'frames_verified': count, 'original_binary_weights_and_mask_formula_verified': True,
              'ordered_bound_layers_verified': 2, 'complete_action_skin_pose_raw_and_both_strain_references': True,
              'original_files_unchanged': True, 'visual_quality_approved': False, 'engine_import_verified': False}
    output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('INDEPENDENT_REGIONAL_FULL_SAVED_SCENE_VERIFIED', count, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--job', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:]); verify(args.job, args.output)
