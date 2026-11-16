"""Real MPFB skin regions and plain-data hand-asset observations.

Never retain Blender polygon/loop views across a dependency-graph update.
Their indices, UVs and settings are copied to ordinary Python data first.
"""
from collections import Counter, defaultdict
import gzip
import math
from pathlib import Path

from blender_bridge.face_geometry import intake, evaluated, float32, rest_state
from blender_bridge.face_materials import signature as material_signature
from blender_bridge.hand_policy import (
    ROOT_BONE, OWN_KEY, METADATA_SHA, BORDER_SHA, POLYGONS_SHA, TARGETS,
    read_json, state_digest, digest,
)
from blender_bridge.native_fit_scene import bone_controls

SKIN_FIELDS = ('use_vertex_groups', 'use_bone_envelopes', 'use_deform_preserve_volume',
               'use_multi_modifier', 'show_viewport', 'show_render', 'vertex_group', 'invert_vertex_group')


def skin_settings(modifier) -> dict:
    return {field: getattr(modifier, field) for field in SKIN_FIELDS}


def pose_settings(rig) -> dict:
    return {'position': rig.data.pose_position,
            'bones': {b.name: {'mode': b.rotation_mode, 'quaternion': list(b.rotation_quaternion),
                                'euler': list(b.rotation_euler), 'axis_angle': list(b.rotation_axis_angle),
                                'location': list(b.location), 'scale': list(b.scale)} for b in rig.pose.bones}}


def source_context(bpy, path: Path):
    bpy.ops.wm.open_mainfile(filepath=str(path), load_ui=False)
    human, rig, service, targets = intake(bpy)
    if any(name.startswith('ucc_hand_') for name in human.keys()):
        raise ValueError('Original hand-library source uses reserved hand ownership properties')
    if any(k.name == OWN_KEY or k.name.startswith(OWN_KEY+'.') for k in human.data.shape_keys.key_blocks):
        raise ValueError('Build a hand library from the original master without a previous hand asset')
    if any(human.data.shape_keys.key_blocks.get(filename.removesuffix('.target.gz')) is not None
           for _, filename, _ in TARGETS):
        raise ValueError('A source with existing finger-length target keys needs a separate hand adapter')
    for obj in (human, rig):
        if any(abs(obj.matrix_world[i][j]-float(i == j)) > 1e-7 for i in range(4) for j in range(4)):
            raise ValueError('The first hand adapter requires canonical unscaled source transforms')
    return human, rig, service, targets


def target_support(root: Path) -> dict[str, set[int]]:
    result = {}
    for variant, filename, expected in TARGETS:
        path = root/filename
        if path.is_symlink() or not path.is_file() or digest(path) != expected:
            raise ValueError('Missing, redirected or changed pinned hand target')
        indices, seen = set(), set()
        with gzip.open(path, 'rt', encoding='utf-8') as stream:
            for line in stream:
                if not line.strip() or line.lstrip().startswith('#'):
                    continue
                row = line.split()
                if len(row) != 4:
                    raise ValueError('Malformed pinned hand target row')
                index = int(row[0]); delta = [float(v) for v in row[1:]]
                if index in seen or not 0 <= index < 19158 or not all(math.isfinite(v) for v in delta):
                    raise ValueError('Invalid or duplicate hand target coordinate')
                seen.add(index)
                if any(delta):
                    indices.add(index)
        result[variant] = indices
    return result


def skin_region(human, rig, root: Path) -> dict:
    metadata = read_json(root/'basemesh_vertex_groups.json', METADATA_SHA, 2*1024*1024)
    ranges = metadata.get('body') if type(metadata) is dict else None
    if (type(ranges) is not list or any(type(row) is not list or len(row) != 2
            or any(type(i) is not int for i in row) or not 0 <= row[0] <= row[1] < 19158 for row in ranges)):
        raise ValueError('Invalid pinned actual-skin vertex ranges')
    skin = {i for start, end in ranges for i in range(start, end+1)}
    if len(skin) != 13380:
        raise ValueError('Pinned source has an unsupported real-skin region')
    hand = rig.data.bones.get(ROOT_BONE)
    if hand is None or hand.parent is None or hand.parent.name != 'lowerarm02.L':
        raise ValueError('Actual default left-wrist hierarchy is missing')
    names = {hand.name}|{b.name for b in hand.children_recursive}
    if len(names) != 20:
        raise ValueError('Actual hand branch differs from the pinned family')
    groups = {g.index for g in human.vertex_groups if g.name in names}
    weighted = {v.index for v in human.data.vertices if v.index in skin
                and any(g.group in groups and g.weight >= .01 for g in v.groups)}
    supports = target_support(root)
    changed = set.union(*supports.values())
    interior = weighted|(changed&skin)
    faces = [(p.index, tuple(p.vertices)) for p in human.data.polygons if all(v in skin for v in p.vertices)]
    neighbors = defaultdict(set)
    for _, vertices in faces:
        for a, b in zip(vertices, vertices[1:]+vertices[:1]):
            neighbors[a].add(b); neighbors[b].add(a)
    for _ in range(2):
        interior |= {n for v in tuple(interior) for n in neighbors[v]}
    selected = [(i, vs) for i, vs in faces if any(v in interior for v in vs)]
    ids = sorted({v for _, vs in selected for v in vs})
    edges = Counter(tuple(sorted((a, b))) for _, vs in selected for a, b in zip(vs, vs[1:]+vs[:1]))
    border_edges = sorted(edge for edge, count in edges.items() if count == 1)
    adjacency = defaultdict(set)
    for a, b in border_edges:
        adjacency[a].add(b); adjacency[b].add(a)
    border = set(adjacency)
    if (len(weighted) != 1685 or len(ids) != 1747 or len(selected) != 1735
            or len(border) != 22 or len(border_edges) != 22 or any(n not in (1, 2) for n in edges.values())
            or any(len(v) != 2 for v in adjacency.values()) or border&changed):
        raise ValueError('Hand part does not have the pinned manifold unchanged skin border')
    connected, queue = set(), [min(border)]
    while queue:
        index = queue.pop()
        if index not in connected:
            connected.add(index); queue.extend(adjacency[index]-connected)
    if connected != border or state_digest(border_edges) != BORDER_SHA or state_digest([i for i, _ in selected]) != POLYGONS_SHA:
        raise ValueError('Hand border or source-polygon identity differs from the pinned region')
    helper_ids = {variant: sorted(support-skin) for variant, support in supports.items()}
    if any(len(values) != 112 for values in helper_ids.values()) or not (changed&skin) <= set(ids):
        raise ValueError('Hand skin/joint-helper support is incomplete')
    # Snapshot every RNA face field before any call to evaluated()/refit().
    polygons = []
    for index, vertices in selected:
        polygon = human.data.polygons[index]
        polygons.append({'index': index, 'vertices': list(vertices), 'smooth': polygon.use_smooth,
                         'material': polygon.material_index,
                         'uv': {layer.name: [list(layer.data[i].uv) for i in polygon.loop_indices]
                                for layer in human.data.uv_layers}})
    return {'ids': ids, 'border': sorted(border), 'polygons': polygons, 'helper_ids': helper_ids,
            'skin_ids': sorted(skin), 'skin_polygons': [(i,list(vs)) for i,vs in faces]}


def material_state(bpy, obj) -> dict:
    """Keep only actual part dependencies; reject unresolved external textures."""
    names = {m.name for m in obj.data.materials if m is not None}
    images = set()
    for material in obj.data.materials:
        if material is None or material.node_tree is None:
            continue
        for node in material.node_tree.nodes:
            image = getattr(node, 'image', None)
            if image is not None:
                if image.packed_file is None:
                    raise ValueError('Pack hand material textures into the editable master before building assets')
                images.add(image.name)
    signature = material_signature(bpy)
    return {'slots': [m.name if m else None for m in obj.data.materials],
            'materials': {name: signature['materials'][name] for name in sorted(names)},
            'images': {name: signature['images'][name] for name in sorted(images)}}


def expected_asset(bpy, human, rig, region: dict, key_coordinates: list) -> dict:
    """Reconstruct expected asset data directly from the original real source."""
    ids = region['ids']; local = {index: i for i, index in enumerate(ids)}
    groups = [g.name for g in human.vertex_groups]
    weights = [[(g.group, float(g.weight)) for g in human.data.vertices[i].groups] for i in ids]
    materials = material_state(bpy, human)
    points = evaluated(bpy, human, full=True)
    if len(points) != 19158:
        raise ValueError('Hand source full-mesh evaluation changed indexing')
    return {'points': [[float32(x) for x in points[i]] for i in ids],
            'key_coordinates': [list(key_coordinates[i]) for i in ids],
            'source_ids': ids, 'polygon_ids': [p['index'] for p in region['polygons']],
            'faces': [[local[i] for i in p['vertices']] for p in region['polygons']],
            'face_shading': [(p['smooth'], p['material']) for p in region['polygons']],
            'uv': [p['uv'] for p in region['polygons']], 'groups': groups, 'weights': weights,
            'uv_active_index': human.data.uv_layers.active_index,
            'materials': materials, 'rest': rest_state(rig), 'bone_controls': bone_controls(rig),
            'skin': skin_settings(human.modifiers[0]), 'pose': pose_settings(rig),
            'parents': {b.name: b.parent.name if b.parent else '' for b in rig.data.bones}}


def observe_asset(bpy, obj, rig) -> dict:
    if (len(obj.data.vertices) != 1747 or len(obj.data.polygons) != 1735 or len(rig.data.bones) != 163
            or obj.parent != rig or len(obj.modifiers) != 1 or obj.modifiers[0].type != 'ARMATURE'
            or obj.modifiers[0].object != rig or obj.data.shape_keys is not None):
        raise ValueError('Saved hand lacks actual standalone skin mesh/default-rig binding')
    for owner in (obj, obj.data, rig, rig.data):
        if owner.library or owner.override_library:
            raise ValueError('Linked or overridden hand asset data is unsupported')
        animation = getattr(owner, 'animation_data', None)
        if animation and (animation.action or len(animation.drivers) or len(animation.nla_tracks)):
            raise ValueError('Hand asset must be a static editable bind source')
    if len(obj.constraints) or len(rig.constraints) or any(len(b.constraints) for b in rig.pose.bones):
        raise ValueError('Hand asset has unsupported constraints')
    for owner in (obj, rig):
        if any(abs(owner.matrix_world[i][j]-float(i == j)) > 1e-7 for i in range(4) for j in range(4)):
            raise ValueError('Hand asset has noncanonical transforms')
    expected_attributes = {'ucc_source_vertex_id': ('INT', 'POINT'),
                           'ucc_reference_key_coordinates': ('FLOAT_VECTOR', 'POINT'),
                           'ucc_source_polygon_id': ('INT', 'FACE')}
    for name, (kind, domain) in expected_attributes.items():
        attribute = obj.data.attributes.get(name)
        if attribute is None or attribute.data_type != kind or attribute.domain != domain:
            raise ValueError('Hand asset lacks canonical source coordinate/topology attributes')
    return {'points': [list(v.co) for v in obj.data.vertices],
            'key_coordinates': [list(v.vector) for v in obj.data.attributes['ucc_reference_key_coordinates'].data],
            'source_ids': [v.value for v in obj.data.attributes['ucc_source_vertex_id'].data],
            'polygon_ids': [v.value for v in obj.data.attributes['ucc_source_polygon_id'].data],
            'faces': [list(p.vertices) for p in obj.data.polygons],
            'face_shading': [(p.use_smooth, p.material_index) for p in obj.data.polygons],
            'uv': [{layer.name: [list(layer.data[i].uv) for i in p.loop_indices] for layer in obj.data.uv_layers}
                   for p in obj.data.polygons],
            'uv_active_index': obj.data.uv_layers.active_index,
            'groups': [g.name for g in obj.vertex_groups],
            'weights': [[(g.group, float(g.weight)) for g in v.groups] for v in obj.data.vertices],
            'materials': material_state(bpy, obj), 'rest': rest_state(rig), 'bone_controls': bone_controls(rig),
            'skin': skin_settings(obj.modifiers[0]), 'pose': pose_settings(rig),
            'parents': {b.name: b.parent.name if b.parent else '' for b in rig.data.bones}}
