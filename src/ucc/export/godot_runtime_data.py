"""Bounded independent byte validation for private runtime inputs, not execution."""
import math
from collections import Counter
from pathlib import Path
import struct
from typing import Callable

from ucc.core.errors import ValidationError
from .godot_candidate_contract import canonical_bytes
from .godot_runtime_contract import NativeRuntimeRequest, PROFILE, CODE_FILES, DATA_FILES
from .godot_skin_evidence import _DenseSkin
from .godot_skin_plan import build_skin_plan

COUNTS = {'source_vertices': 19158, 'vertices': 13380, 'faces': 13378, 'corners': 53512,
          'bones': 163, 'max_influences': 8}
SMOOTHING = {'factor': .5, 'iterations': 5, 'smooth_type': 'SIMPLE', 'scale': 1.,
    'rest_source': 'BIND', 'use_only_smooth': False, 'use_pin_boundary': False,
    'vertex_group': '', 'invert_vertex_group': False, 'show_viewport': True, 'show_render': True}
SIZES = {'neighbor_ranges.u32': 13380*8, 'neighbors.u32': 53512*4,
    'corners.u32': 53512*16, 'offsets_vec4.f32': 53512*16,
    'corner_ranges.u32': 13380*8, 'corner_indices.u32': 53512*4,
    'face_ranges.u32': 13378*8, 'face_vertices.u32': 53512*4, 'face_ids.u32': 53512*4,
    'bind_positions.bin': 13380*12}
LIMITS = {**SIZES, **{name: 256*1024 for name in CODE_FILES},
          'character.glb': 512*1024*1024, 'skin_plan.json': 64*1024*1024,
          'bind_source_indices.json': 4*1024*1024, 'source_profile.json': 64*1024}


def _rows(data: bytes, fmt: str, count: int) -> list[tuple]:
    if len(data) != struct.calcsize(fmt)*count:
        raise ValidationError('Runtime binary has incomplete or trailing records')
    return list(struct.iter_unpack(fmt, data))


def _ranges(data: bytes, count: int, total: int, minimum: int, maximum: int) -> list[tuple[int, int]]:
    rows = _rows(data, '<2I', count); cursor = 0
    for start, size in rows:
        if start != cursor or not minimum <= size <= maximum:
            raise ValidationError('Runtime ranges overlap, skip records or have unsupported valence')
        cursor += size
    if cursor != total:
        raise ValidationError('Runtime ranges do not cover the complete topology')
    return rows


def validate_topology(data: dict[str, bytes], *, vertices: int, faces: int, corners: int,
                      check: Callable[[], None]) -> None:
    """Cross-check adjacency, polygon loops and corner incidence independently.

    Counts are supplied by the admitted profile. Smaller isolated test fixtures
    exercise this logic without pretending to be an MPFB integration.
    """
    loop = _rows(data['corners.u32'], '<4I', corners)
    face_vertices = [row[0] for row in _rows(data['face_vertices.u32'], '<I', corners)]
    face_ids = [row[0] for row in _rows(data['face_ids.u32'], '<I', corners)]
    ranges = _ranges(data['face_ranges.u32'], faces, corners, 3, 4)
    adjacency = [set() for _ in range(vertices)]
    for face, (start, size) in enumerate(ranges):
        check(); ids = face_vertices[start:start+size]
        if len(set(ids)) != size or any(vertex >= vertices for vertex in ids):
            raise ValidationError('Invalid or degenerate runtime polygon identity')
        for index, vertex in enumerate(ids):
            previous, following = ids[index-1], ids[(index+1) % size]
            if loop[start+index] != (previous, vertex, following, 0) or face_ids[start+index] != face:
                raise ValidationError('Runtime corner/polygon correspondence changed')
            adjacency[vertex].update((previous, following))
    neighbor_rows = _ranges(data['neighbor_ranges.u32'], vertices,
                            len(data['neighbors.u32'])//4, 1, 64)
    neighbors = [row[0] for row in _rows(data['neighbors.u32'], '<I', sum(size for _, size in neighbor_rows))]
    incident_ranges = _ranges(data['corner_ranges.u32'], vertices, corners, 1, 64)
    incident = [row[0] for row in _rows(data['corner_indices.u32'], '<I', corners)]
    if set(incident) != set(range(corners)):
        raise ValidationError('Runtime incidence must cover each original corner exactly once')
    for vertex in range(vertices):
        if vertex % 256 == 0:
            check()
        start, size = neighbor_rows[vertex]; values = neighbors[start:start+size]
        if len(set(values)) != size or set(values) != adjacency[vertex]:
            raise ValidationError('Runtime adjacency differs from original polygons')
        start, size = incident_ranges[vertex]
        if any(loop[index][1] != vertex for index in incident[start:start+size]):
            raise ValidationError('Runtime corner incidence names another vertex')
    for offset in _rows(data['offsets_vec4.f32'], '<4f', corners):
        if any(not math.isfinite(value) or abs(value) > 1 for value in offset[:3]) or offset[3] != 1.:
            raise ValidationError('Runtime offsets require bounded finite original local vectors and homogeneous one')


def _position_key(point: tuple) -> str:
    return struct.pack('<3f', *(0. if value == 0 else value for value in point)).hex()


def validate_triangles(polygons: list[tuple[int, ...]], triangles: list[tuple[int, ...]],
                       check: Callable[[], None]) -> None:
    """Require a winding-preserving complete triangulation of original polygons."""
    incident: dict[int, set[int]] = {}
    for face, polygon in enumerate(polygons):
        for vertex in polygon:
            incident.setdefault(vertex, set()).add(face)
    grouped: list[list[tuple[int, ...]]] = [[] for _ in polygons]
    for triangle in triangles:
        check()
        if len(triangle) != 3 or len(set(triangle)) != 3:
            raise ValidationError('Runtime GLB triangle has invalid source identities')
        candidates = set.intersection(*(incident.get(vertex, set()) for vertex in triangle))
        if len(candidates) != 1:
            raise ValidationError('Runtime GLB triangle crosses or ambiguously names original polygons')
        grouped[candidates.pop()].append(triangle)
    for polygon, rows in zip(polygons, grouped):
        if len(rows) != len(polygon)-2:
            raise ValidationError('Runtime GLB lost or duplicated original polygon triangles')
        edges: Counter = Counter()
        for row in rows:
            edges.update(zip(row, row[1:]+row[:1]))
        for a, b in list(edges):
            count = min(edges[a, b], edges[b, a])
            edges[a, b] -= count; edges[b, a] -= count
        if +edges != Counter(zip(polygon, polygon[1:]+polygon[:1])):
            raise ValidationError('Runtime GLB triangulation changed winding or boundary edges')


def validate_clock(times: list[float], mode: str, values: list[tuple]) -> bool:
    complete = [struct.unpack('<f', struct.pack('<f', frame/30.))[0] for frame in range(300)]
    if times not in (complete, [complete[0], complete[-1]]) or mode not in ('LINEAR', 'STEP'):
        raise ValidationError('Runtime animation changed native clock or interpolation')
    if mode == 'STEP' and (len(times) != 2 or not values or len(values) % 2
                           or values[:len(values)//2] != values[len(values)//2:]):
        raise ValidationError('Only exactly constant two-endpoint STEP tracks are admitted')
    return times == complete


def validate_native_clock(reader: _DenseSkin) -> None:
    doc = reader.document
    try:
        animations = doc.get('animations', [])
        if type(animations) is not list or len(animations) != 1 or type(animations[0]) is not dict:
            raise ValidationError('Runtime input needs exactly one native source clip')
        animation = animations[0]; samplers = animation['samplers']; channels = animation['channels']
        if (type(samplers) is not list or not 1 <= len(samplers) <= 1024
                or type(channels) is not list or not 1 <= len(channels) <= 1024):
            raise ValidationError('Invalid runtime animation sampler/channel collections')
        used = set(); full = False
        for channel in channels:
            target = channel['target']; index = channel['sampler']; node = target['node']; path = target['path']
            if (type(index) is not int or not 0 <= index < len(samplers)
                    or type(node) is not int or not 0 <= node < len(doc['nodes'])
                    or path not in ('translation', 'rotation', 'scale', 'weights')):
                raise ValidationError('Invalid runtime animation channel target')
            sampler = samplers[index]; used.add(index)
            times = [row[0] for row in reader.rows(sampler['input'], 'SCALAR', (5126,))]
            kind = {'translation': 'VEC3', 'rotation': 'VEC4', 'scale': 'VEC3', 'weights': 'SCALAR'}[path]
            values = reader.rows(sampler['output'], kind, (5126,))
            if len(values) != len(times)*(12 if path == 'weights' else 1):
                raise ValidationError('Runtime animation output count changed')
            full |= validate_clock(times, sampler.get('interpolation', 'LINEAR'), values)
        if used != set(range(len(samplers))) or not full:
            raise ValidationError('Runtime clip has unused samplers or lacks its complete native clock')
    except (KeyError, IndexError, TypeError) as error:
        raise ValidationError('Malformed runtime animation structure') from error


def validate_runtime_files(folder: Path, request: NativeRuntimeRequest,
                           check: Callable[[], None]) -> dict:
    # Reuse strict path/JSON helpers, without admitting the older V1 deformation.
    from ucc.jobs.godot_candidate_inputs import regular_file, read_json
    from ucc.jobs.master_preview import _digest
    for name, expected in request.files:
        check(); path = regular_file(folder/name, folder, LIMITS[name])
        if name in SIZES and path.stat().st_size != SIZES[name]:
            raise ValidationError('Runtime fixed-size input changed: '+name)
        if _digest(path, None) != expected:
            raise ValidationError('Runtime input hash changed: '+name)
    profile = read_json(folder/'source_profile.json', LIMITS['source_profile.json'])
    expected_profile = {'schema_version': 1, 'profile': PROFILE, 'counts': COUNTS,
        'source_review_sha256': dict(request.evidence_bindings)['native_review'],
        'source_timeline_sha256': dict(request.evidence_bindings)['native_timeline'],
        'master_sha256': request.master_sha256, 'smoothing': SMOOTHING,
        'is_bound': True, 'linear_skin': True, 'static_masks_baked': True,
        'model_world': [1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.],
        'flat_faces': 0, 'sharp_edges': 0, 'custom_normals': False,
        'source_production_verified': False, 'engine_import_verified': False}
    if canonical_bytes(profile) != canonical_bytes(expected_profile):
        raise ValidationError('Runtime source profile differs from the bounded smooth identity experiment')
    data = {name: (folder/name).read_bytes() for name in DATA_FILES}
    validate_topology(data, vertices=COUNTS['vertices'], faces=COUNTS['faces'], corners=COUNTS['corners'], check=check)
    points = _rows((folder/'bind_positions.bin').read_bytes(), '<3f', COUNTS['vertices'])
    indices = {}
    for index, point in enumerate(points):
        if any(not math.isfinite(value) or abs(value) > 100 for value in point):
            raise ValidationError('Invalid runtime bind coordinates')
        key = _position_key(point)
        if key in indices:
            raise ValidationError('Ambiguous runtime bind vertex identity')
        indices[key] = index
    if canonical_bytes(read_json(folder/'bind_source_indices.json', LIMITS['bind_source_indices.json'])) != canonical_bytes(indices):
        raise ValidationError('Runtime bind/source mapping changed')
    check(); plan = build_skin_plan(folder/'character.glb')
    if len(plan.bone_names) != COUNTS['bones']:
        raise ValidationError('Runtime family rig differs from the admitted profile')
    if canonical_bytes(read_json(folder/'skin_plan.json', LIMITS['skin_plan.json'])) != canonical_bytes(plan.to_dict()):
        raise ValidationError('Runtime skin plan differs from independent GLB inspection')
    reader = _DenseSkin(folder/'character.glb'); doc = reader.document
    primitive = doc['meshes'][0]['primitives'][0]
    imported_points = reader.rows(primitive['attributes']['POSITION'], 'VEC3', (5126,))
    actual = {_position_key(point) for point in imported_points}
    if actual != set(indices):
        raise ValidationError('Runtime GLB lost complete source surface correspondence')
    imported_ids = [indices[_position_key(point)] for point in imported_points]
    triangle_indices = [row[0] for row in reader.rows(primitive['indices'], 'SCALAR', (5121, 5123, 5125))]
    if len(triangle_indices) % 3 or any(index >= len(imported_ids) for index in triangle_indices):
        raise ValidationError('Runtime GLB triangle indices are incomplete or out of range')
    source_ids = [imported_ids[index] for index in triangle_indices]
    face_vertices = [row[0] for row in struct.iter_unpack('<I', data['face_vertices.u32'])]
    polygons = [tuple(face_vertices[start:start+size]) for start, size in struct.iter_unpack('<2I', data['face_ranges.u32'])]
    triangles = [tuple(source_ids[index:index+3]) for index in range(0, len(source_ids), 3)]
    validate_triangles(polygons, triangles, check)
    validate_native_clock(reader)
    check()
    return {'status': 'PRIVATE_RUNTIME_BYTES_VALIDATED_NOT_EXECUTED', 'counts': dict(COUNTS),
        'source_profile_claim_only': True, 'runtime_execution_verified': False,
        'native_lineage_verified': False, 'engine_import_verified': False,
        'visual_quality_approved': False, 'distribution_license_review_complete': False}
