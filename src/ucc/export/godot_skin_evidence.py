"""Bounded eight-influence GLB evidence against original MPFB weights.

The shared dense decoder supports bounded position, skin and UV accessors.
The original-weight comparison below remains a diagnostic-only UV profile,
not general glTF acceptance or proof of Godot rendering or animation.
"""
import hashlib
import json
import math
from pathlib import Path
import struct

from .inspect_glb import GLBInspectionError, MAX_GLB_BYTES, MAX_JSON_BYTES


class GodotSkinEvidenceError(GLBInspectionError):
    pass


def _integer(value: object, maximum: int, label: str) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise GodotSkinEvidenceError('Invalid '+label)
    return value


def _object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for name, value in pairs:
        if name in result:
            raise GodotSkinEvidenceError('Duplicate GLB JSON field')
        result[name] = value
    return result


class _DenseSkin:
    def __init__(self, path: Path):
        if path.is_symlink() or not path.is_file() or not 20 <= path.stat().st_size <= MAX_GLB_BYTES:
            raise GodotSkinEvidenceError('Require a bounded regular candidate GLB')
        with path.open('rb') as stream:
            self.raw = stream.read(MAX_GLB_BYTES+1)
        if not 20 <= len(self.raw) <= MAX_GLB_BYTES:
            raise GodotSkinEvidenceError('Candidate changed outside its bounded container')
        if struct.unpack_from('<4sII', self.raw) != (b'glTF', 2, len(self.raw)):
            raise GodotSkinEvidenceError('Invalid candidate GLB header')
        cursor = 12; document = binary = None
        while cursor < len(self.raw):
            if len(self.raw)-cursor < 8:
                raise GodotSkinEvidenceError('Incomplete candidate chunk')
            size, kind = struct.unpack_from('<I4s', self.raw, cursor); cursor += 8
            if size % 4 or size > len(self.raw)-cursor:
                raise GodotSkinEvidenceError('Candidate chunk escaped container')
            chunk = self.raw[cursor:cursor+size]; cursor += size
            if kind == b'JSON' and document is None and binary is None and size <= MAX_JSON_BYTES:
                try:
                    document = json.loads(chunk.decode('utf-8'), object_pairs_hook=_object)
                except (ValueError, UnicodeError, RecursionError) as error:
                    raise GodotSkinEvidenceError('Invalid candidate JSON') from error
            elif kind == b'BIN\0' and document is not None and binary is None:
                binary = chunk
            else:
                raise GodotSkinEvidenceError('Unsupported or duplicate candidate chunk')
        if (type(document) is not dict or binary is None or type(document.get('asset')) is not dict
                or document['asset'].get('version') != '2.0'):
            raise GodotSkinEvidenceError('Candidate has no complete glTF 2.0 payload')
        buffers = document.get('buffers')
        if (type(buffers) is not list or len(buffers) != 1 or type(buffers[0]) is not dict
                or 'uri' in buffers[0] or _integer(buffers[0].get('byteLength'), len(binary), 'buffer size') > len(binary)):
            raise GodotSkinEvidenceError('External or incomplete candidate buffer')
        declared = buffers[0]['byteLength']
        if not 0 <= len(binary)-declared <= 3:
            raise GodotSkinEvidenceError('Invalid candidate binary padding')
        self.document = document; self.binary = binary[:declared]

    def rows(self, index: object, kind: str, components: tuple[int, ...]) -> list[tuple]:
        accessors = self.document.get('accessors'); views = self.document.get('bufferViews')
        if type(accessors) is not list or type(views) is not list:
            raise GodotSkinEvidenceError('Missing candidate accessors')
        accessor = accessors[_integer(index, len(accessors)-1, 'accessor index')]
        if (type(accessor) is not dict or accessor.get('type') != kind
                or type(accessor.get('componentType')) is not int
                or accessor.get('componentType') not in components or 'sparse' in accessor
                or accessor.get('normalized', False) is not False):
            raise GodotSkinEvidenceError('Unsupported diagnostic skin accessor')
        view = views[_integer(accessor.get('bufferView'), len(views)-1, 'view index')]
        if type(view) is not dict or type(view.get('buffer')) is not int or view.get('buffer') != 0:
            raise GodotSkinEvidenceError('Skin accessor uses another buffer')
        offset = _integer(view.get('byteOffset', 0), len(self.binary), 'view offset')
        length = _integer(view.get('byteLength'), len(self.binary), 'view length')
        begin = _integer(accessor.get('byteOffset', 0), length, 'accessor offset')
        count = _integer(accessor.get('count'), 100000, 'skin vertex count')
        formats = {5121: 'B', 5123: 'H', 5125: 'I', 5126: 'f'}
        dimensions = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}
        if kind not in dimensions or accessor['componentType'] not in formats:
            raise GodotSkinEvidenceError('Unsupported dense accessor dimensions or component format')
        fmt = '<'+formats[accessor['componentType']]*dimensions[kind]
        width = struct.calcsize(fmt)
        stride = _integer(view.get('byteStride', width), 252, 'skin stride')
        # Tightly packed scalar indices may be uint8/uint16. Interleaved
        # vertex records retain their four-byte stride requirement.
        stride_alignment = 4 if 'byteStride' in view or kind != 'SCALAR' else struct.calcsize(formats[accessor['componentType']])
        if (count < 1 or stride < width or stride % stride_alignment
                or (offset+begin) % struct.calcsize(formats[accessor['componentType']])
                or offset+length > len(self.binary) or begin+(count-1)*stride+width > length):
            raise GodotSkinEvidenceError('Skin accessor escaped its declared view')
        rows = [struct.unpack_from(fmt, self.binary, offset+begin+i*stride) for i in range(count)]
        if any(not math.isfinite(value) for row in rows for value in row):
            raise GodotSkinEvidenceError('Nonfinite candidate skin value')
        return rows


def inspect_diagnostic_skin(path: Path, source_weights: list) -> tuple[dict, list[dict[str, float]]]:
    """Check every serialized influence, including vertices split at UV seams."""
    if type(source_weights) is not list or not 1 <= len(source_weights) <= 100000:
        raise GodotSkinEvidenceError('Missing bounded original skin evidence')
    originals = []
    for rows in source_weights:
        expected = {}
        if type(rows) is not list or not 1 <= len(rows) <= 8:
            raise GodotSkinEvidenceError('Invalid original influence list')
        for row in rows:
            if type(row) not in (list, tuple) or len(row) != 2:
                raise GodotSkinEvidenceError('Invalid original influence pair')
            name, weight = row
            if (type(name) is not str or not name or len(name) > 128 or name in expected
                    or type(weight) not in (int, float) or not math.isfinite(weight) or not 0 < weight <= 1):
                raise GodotSkinEvidenceError('Invalid or duplicate original influence')
            expected[name] = float(weight)
        if abs(math.fsum(expected.values())-1) > 1e-6:
            raise GodotSkinEvidenceError('Original reference must explicitly describe normalized ratios')
        originals.append(expected)
    reader = _DenseSkin(path); doc = reader.document
    try:
        if len(doc['meshes']) != 1 or len(doc['meshes'][0]['primitives']) != 1 or len(doc['skins']) != 1:
            raise GodotSkinEvidenceError('Diagnostic profile requires one skinned primitive')
        attributes = doc['meshes'][0]['primitives'][0]['attributes']
        joints = doc['skins'][0]['joints']; bone_names = []
        if type(joints) is not list or not 1 <= len(joints) <= 512 or len(set(joints)) != len(joints):
            raise GodotSkinEvidenceError('Invalid candidate joints')
        for node in joints:
            name = doc['nodes'][_integer(node, len(doc['nodes'])-1, 'joint node')].get('name')
            if type(name) is not str or not name or name in bone_names:
                raise GodotSkinEvidenceError('Missing or duplicate original bone name')
            bone_names.append(name)
        uv = reader.rows(attributes['TEXCOORD_1'], 'VEC2', (5126,))
        j0 = reader.rows(attributes['JOINTS_0'], 'VEC4', (5121, 5123))
        j1 = reader.rows(attributes['JOINTS_1'], 'VEC4', (5121, 5123))
        w0 = reader.rows(attributes['WEIGHTS_0'], 'VEC4', (5126,))
        w1 = reader.rows(attributes['WEIGHTS_1'], 'VEC4', (5126,))
        if len({len(rows) for rows in (uv, j0, j1, w0, w1)}) != 1:
            raise GodotSkinEvidenceError('Inconsistent skin accessor lengths')
        observed: dict[int, dict[str, float]] = {}; maximum = 0.
        for vertex, (u, v) in enumerate(uv):
            low, high = round(u*255), round((1-v)*255)
            if (not 0 <= low <= 255 or not 0 <= high <= 255
                    or abs(u*255-low) > 1e-4 or abs((1-v)*255-high) > 1e-4):
                raise GodotSkinEvidenceError('Invalid diagnostic source identity')
            source = _integer(low+256*high, len(source_weights)-1, 'source vertex')
            actual = {}
            for joint, weight in zip(j0[vertex]+j1[vertex], w0[vertex]+w1[vertex]):
                name = bone_names[_integer(joint, len(bone_names)-1, 'skin joint')]
                if not 0 <= weight <= 1.00001:
                    raise GodotSkinEvidenceError('Invalid serialized weight')
                if weight > 0:
                    if name in actual:
                        raise GodotSkinEvidenceError('Duplicate positive bone contribution')
                    actual[name] = weight
            expected = originals[source]
            if set(actual) != set(expected):
                raise GodotSkinEvidenceError('Exporter dropped or introduced a positive influence')
            error = max(abs(actual[name]-expected[name]) for name in expected)
            if error > 1e-6:
                raise GodotSkinEvidenceError('Serialized weight ratios changed')
            maximum = max(maximum, error)
            if source in observed and observed[source] != actual:
                raise GodotSkinEvidenceError('Split vertices disagree on source skin')
            observed[source] = actual
        if set(observed) != set(range(len(source_weights))):
            raise GodotSkinEvidenceError('Candidate lost source vertices')
        proof = {'status': 'ALL_ORIGINAL_POSITIVE_INFLUENCES_SERIALIZED',
            'glb_sha256': hashlib.sha256(reader.raw).hexdigest(), 'serialized_vertices': len(uv),
            'source_vertices': len(source_weights), 'max_weight_serialization_error': maximum,
            'engine_import_verified': False}
        return proof, [observed[index] for index in range(len(source_weights))]
    except (KeyError, IndexError, TypeError) as error:
        raise GodotSkinEvidenceError('Incomplete diagnostic candidate structure') from error
