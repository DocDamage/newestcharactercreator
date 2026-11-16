"""Complete real facial skin samples and bounded local playback bytes."""
from array import array
from hashlib import sha256
import math
from pathlib import Path
import struct
import zlib

from blender_bridge.expression_clip_action import linear_weight
from blender_bridge.face_geometry import evaluated
from blender_bridge.expression_geometry import source_state
from blender_bridge.face_operations import state_digest

MAGIC = b'UCCSKN1\0'
MAX_BYTES = 16*1024*1024


def surface(bpy, human) -> tuple:
    graph = bpy.context.evaluated_depsgraph_get(); obj = human.evaluated_get(graph)
    mesh = obj.to_mesh(preserve_all_data_layers=True, depsgraph=graph)
    try:
        mesh.calc_loop_triangles()
        if len(mesh.vertices) != 13380 or len(mesh.loop_triangles) != 26756:
            raise ValueError('Expression cache requires the entire actual visible skin')
        vertices = array('f', [0.])*(3*13380); indices = array('I', [0])*(3*26756)
        mesh.vertices.foreach_get('co', vertices); mesh.loop_triangles.foreach_get('vertices', indices)
        if any(not math.isfinite(v) or abs(v) > 10000 for v in vertices):
            raise ValueError('Nonfinite or excessive expression skin coordinates')
        import sys
        if sys.byteorder != 'little': vertices.byteswap(); indices.byteswap()
        vb, ib = vertices.tobytes(), indices.tobytes()
        quantized = sha256()
        for xyz in struct.iter_unpack('<fff', vb):
            quantized.update(struct.pack('<qqq', *(round(v*1000000) for v in xyz)))
        return vb+ib, {'local_vertices_sha256': sha256(vb).hexdigest(), 'triangles_sha256': sha256(ib).hexdigest(),
                       'skin_sha256': quantized.hexdigest(), 'raw_sha256': sha256(vb+ib).hexdigest()}
    finally:
        obj.to_mesh_clear()


def fixed_state(state: dict) -> str:
    return state_digest({k: v for k, v in state.items() if k not in {'full_sha256', 'visible_sha256'}})


def measure_frame(bpy, human, rig, targets, frame: int, values: dict, loaded: dict,
                   baseline: dict, original: list, support: set) -> tuple:
    actual = {pair: float(key.value) for pair, key in loaded.items()}
    expected = {pair: linear_weight(peak, frame) for pair, peak in values.items()}
    if actual != expected:
        raise ValueError('Expression frame strengths differ from independent float32 interpolation')
    state = source_state(bpy, human, rig, targets, strip_expression=True)
    if fixed_state(state) != fixed_state(baseline):
        raise ValueError('Expression frame changed original keys, rig, skin binding or unrelated state')
    full = evaluated(bpy, human, full=True)
    distances = [math.dist(a, b) for a, b in zip(original, full)]
    if len(full) != 19158 or max(distances) > .03 or max((d for i, d in enumerate(distances)
            if i not in support), default=0.) > 1e-6:
        raise ValueError('Expression frame exceeds its support or 30mm combined displacement bound')
    if frame in (1, 25) and (state['full_sha256'] != baseline['full_sha256']
            or state['visible_sha256'] != baseline['visible_sha256']):
        raise ValueError('Expression endpoint did not restore exact neutral skin')
    raw, hashes = surface(bpy, human)
    return raw, {'frame': frame, 'full_sha256': state['full_sha256'], 'visible_sha256': state['visible_sha256'],
                 'fixed_state_sha256': fixed_state(state), 'maximum_displacement': max(distances),
                 'moved_vertices_over_1um': sum(d > 1e-6 for d in distances), **hashes}


class SkinWriter:
    def __init__(self, path: Path, hip: list):
        self.path = path; self.hip = hip; self.frames = []; self.stream = path.open('xb'); self.stream.write(MAGIC)

    def append(self, raw: bytes, row: dict) -> None:
        packed = zlib.compress(raw, 1); offset = self.stream.tell()
        if offset+len(packed) > MAX_BYTES or len(self.frames) >= 25:
            raise ValueError('Complete expression cache exceeds its fixed bound; no cropping')
        self.stream.write(packed)
        self.frames.append({'frame': row['frame'], 'offset': offset, 'compressed_bytes': len(packed),
                            'raw_sha256': row['raw_sha256'], 'skin_sha256': row['skin_sha256'], 'hip_world': self.hip})

    def close(self):
        self.stream.close()


def read_cache(path: Path, manifest: dict) -> list:
    data = path.read_bytes()
    if len(data) > MAX_BYTES or data[:8] != MAGIC or len(manifest.get('frames', [])) != 25:
        raise ValueError('Expression cache header or complete coverage differs')
    offset = 8; rows = []
    for frame, row in enumerate(manifest['frames'], 1):
        if (type(row) is not dict or row.get('frame') != frame or type(row.get('offset')) is not int
                or row['offset'] != offset or type(row.get('compressed_bytes')) is not int
                or not 0 < row['compressed_bytes'] <= MAX_BYTES-offset):
            raise ValueError('Expression cache offsets, coverage or workload differ')
        size = row['compressed_bytes']; decoder = zlib.decompressobj()
        raw = decoder.decompress(data[offset:offset+size], 12*(13380+26756)+1)
        if (len(raw) != 12*(13380+26756) or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail
                or sha256(raw).hexdigest() != row.get('raw_sha256')):
            raise ValueError('Expression cache frame is changed, oversized or concatenated')
        rows.append(raw); offset += size
    if offset != len(data): raise ValueError('Expression cache has trailing bytes or missing coverage')
    return rows
