"""Versioned Godot skin encoding plan, independent of diagnostic UV channels.

This is an adapter input, not rights admission or engine acceptance. Matching
uses exact float32 positions and the unmodified importer's bone/code set. Any
collision requiring a different correction fails instead of guessing.
"""
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import re
import struct
from typing import Any

from ucc.core.expressions import TARGETS

from .godot_skin_evidence import _DenseSkin, _integer, GodotSkinEvidenceError

PROFILE = 'MPFB_GODOT_UNIT_SUM_SKIN_V1'
CORRESPONDENCE = 'FLOAT32_POSITION_AND_IMPORTED_POSITIVE_BONE_CODES_V1'
POLICY = 'UNIT_SUM_UNORM16_LARGEST_REMAINDER_V1'
_BONE = re.compile(r'[A-Za-z0-9_.-]{1,128}\Z')


class GodotSkinPlanError(GodotSkinEvidenceError):
    """The candidate cannot safely use this exact Godot skin adapter."""


def _float32(value: float) -> float:
    return struct.unpack('<f', struct.pack('<f', value))[0]


def unit_sum_codes(weights: dict[str, float]) -> dict[str, int]:
    """Apportion one uint16 unit while retaining every positive contribution."""
    if type(weights) is not dict or not 1 <= len(weights) <= 8:
        raise GodotSkinPlanError('Require one to eight positive skin contributions')
    for name, value in weights.items():
        if (type(name) is not str or not _BONE.fullmatch(name)
                or type(value) not in (int, float) or not math.isfinite(value)
                or not 0 < value <= 1):
            raise GodotSkinPlanError('Invalid original bone identity or positive weight')
    total = math.fsum(weights.values())
    if abs(total-1) > 1e-6:
        raise GodotSkinPlanError('Serialized relative weights must already be normalized')
    scaled = {name: value/total*65535 for name, value in weights.items()}
    codes = {name: math.floor(value) for name, value in scaled.items()}
    deficit = 65535-sum(codes.values())
    if not 0 <= deficit <= len(codes):
        raise GodotSkinPlanError('Invalid integer apportionment')
    order = sorted(codes, key=lambda name: (-(scaled[name]-codes[name]), name))
    for name in order[:deficit]:
        codes[name] += 1
    if any(code <= 0 for code in codes.values()):
        raise GodotSkinPlanError('Positive contribution cannot be represented; never prune')
    if any(abs(codes[name]/65535-weights[name]/total) > 1/65535+1e-12 for name in codes):
        raise GodotSkinPlanError('Encoding exceeds one UNORM16 quantum')
    return dict(sorted(codes.items()))


def _import_codes(rows: list[tuple[str, float]]) -> dict[str, int]:
    # Godot 4.7 glTF: accumulate and divide all eight slots in float32 order,
    # then multiply in float32 and truncate to uint16. Zero slots add nothing.
    total = 0.
    for _, value in rows:
        total = _float32(total+value)
    result = {name: int(_float32(_float32(value/total)*65535)) for name, value in rows}
    if any(code <= 0 for code in result.values()):
        raise GodotSkinPlanError('Unmodified engine packing would lose a positive contribution')
    return result


def correspondence_key(position: tuple[float, ...], codes: dict[str, int]) -> str:
    # Canonicalize signed zero because Godot may change its sign in arithmetic.
    bits = struct.pack('<3f', *(0. if value == 0 else value for value in position)).hex()
    return bits+':'+';'.join(f'{name}={code}' for name, code in sorted(codes.items()))


@dataclass(frozen=True, slots=True)
class GodotSkinPlan:
    candidate_sha256: str
    vertex_count: int
    bone_names: tuple[str, ...]
    entries: dict[str, dict[str, Any]]
    maximum_encoding_error: float

    def to_dict(self) -> dict[str, Any]:
        return {'schema_version': 1, 'profile': PROFILE, 'policy': POLICY,
                'correspondence': CORRESPONDENCE, 'candidate_sha256': self.candidate_sha256,
                'vertex_count': self.vertex_count, 'bone_names': list(self.bone_names),
                'entries': self.entries, 'max_relative_encoding_error': self.maximum_encoding_error,
                'diagnostic_UV_required': False, 'engine_import_verified': False}


def build_skin_plan(path: Path, *, corrective_frames: int = 0) -> GodotSkinPlan:
    """Read a bounded self-contained dense GLB and reject ambiguous skin matches."""
    if type(corrective_frames) is not int or not 0 <= corrective_frames <= 600:
        raise GodotSkinPlanError('Corrective skin metadata requires an explicit bounded complete frame count')
    morph_names = {target.key_name for target in TARGETS}
    morph_names |= {f'UCC_POSE_CORRECTION_V1_f{frame:04d}' for frame in range(1, corrective_frames+1)}
    reader = _DenseSkin(path)
    doc = reader.document
    try:
        # Blender's standard morph-name metadata is needed by Godot to retain
        # named controls. Admit that exact closed payload on the sole mesh;
        # arbitrary node/material extras and script metadata remain rejected.
        named_mesh = None
        meshes = doc.get('meshes')
        if type(meshes) is list and len(meshes) == 1 and type(meshes[0]) is dict:
            extras = meshes[0].get('extras')
            if (type(extras) is dict and set(extras) == {'targetNames'}
                    and type(extras['targetNames']) is list and len(extras['targetNames']) == len(morph_names)
                    and all(type(name) is str for name in extras['targetNames'])
                    and set(extras['targetNames']) == morph_names):
                named_mesh = meshes[0]
        # Engine candidates cannot cause implicit external reads, plugin
        # execution or a different extension path during actual editor import.
        pending = [doc]
        visited = 0
        while pending:
            value = pending.pop(); visited += 1
            if visited > 2_000_000:
                raise GodotSkinPlanError('Candidate metadata exceeds bounded engine inspection')
            if type(value) is dict:
                if (any(key in value for key in ('uri', 'extensions'))
                        or ('extras' in value and value is not named_mesh)):
                    raise GodotSkinPlanError('External resources, extensions and custom extras need separate admission')
                pending.extend(value.values())
            elif type(value) is list:
                pending.extend(value)
        if doc.get('extensionsUsed'):
            raise GodotSkinPlanError('Optional glTF extensions need separate engine admission')
        if len(doc['meshes']) != 1 or len(doc['meshes'][0]['primitives']) != 1 or len(doc['skins']) != 1:
            raise GodotSkinPlanError('This skin adapter requires one mesh, primitive and skin')
        if doc.get('extensionsRequired'):
            raise GodotSkinPlanError('Required glTF extensions need separate admission')
        primitive = doc['meshes'][0]['primitives'][0]
        if type(primitive.get('mode', 4)) is not int or primitive.get('mode', 4) != 4 or primitive.get('extensions'):
            raise GodotSkinPlanError('Only ordinary triangle primitives are supported')
        attributes = primitive['attributes']
        joints = doc['skins'][0]['joints']
        if type(joints) is not list or not 1 <= len(joints) <= 512 or len(set(joints)) != len(joints):
            raise GodotSkinPlanError('Invalid or duplicate joint identity')
        names = []
        for joint in joints:
            node = doc['nodes'][_integer(joint, len(doc['nodes'])-1, 'joint')]
            name = node.get('name')
            if type(name) is not str or not _BONE.fullmatch(name) or name in names:
                raise GodotSkinPlanError('Invalid, ambiguous or duplicate bone name')
            names.append(name)
        positions = reader.rows(attributes['POSITION'], 'VEC3', (5126,))
        j0 = reader.rows(attributes['JOINTS_0'], 'VEC4', (5121, 5123))
        j1 = reader.rows(attributes['JOINTS_1'], 'VEC4', (5121, 5123))
        w0 = reader.rows(attributes['WEIGHTS_0'], 'VEC4', (5126,))
        w1 = reader.rows(attributes['WEIGHTS_1'], 'VEC4', (5126,))
        if len({len(rows) for rows in (positions, j0, j1, w0, w1)}) != 1:
            raise GodotSkinPlanError('Inconsistent position and skin accessor coverage')
        entries = {}; maximum = 0.
        for index, position in enumerate(positions):
            rows = []; seen = set()
            for joint, value in zip(j0[index]+j1[index], w0[index]+w1[index]):
                name = names[_integer(joint, len(names)-1, 'skin joint')]
                if not 0 <= value <= 1:
                    raise GodotSkinPlanError('Invalid serialized skin contribution')
                if value > 0:
                    if name in seen:
                        raise GodotSkinPlanError('Duplicate positive bone contribution')
                    seen.add(name); rows.append((name, value))
            weights = dict(rows)
            desired = unit_sum_codes(weights)
            key = correspondence_key(position, _import_codes(rows))
            if key in entries and entries[key]['codes'] != desired:
                raise GodotSkinPlanError('Ambiguous imported vertex requires different skin codes')
            if key not in entries:
                entries[key] = {'count': 0, 'codes': desired}
            entries[key]['count'] += 1
            total = math.fsum(weights.values())
            maximum = max(maximum, *(abs(desired[name]/65535-weights[name]/total) for name in desired))
        return GodotSkinPlan(hashlib.sha256(reader.raw).hexdigest(), len(positions),
                             tuple(names), entries, maximum)
    except (KeyError, IndexError, TypeError, AttributeError) as error:
        raise GodotSkinPlanError('Incomplete or malformed skin-plan candidate') from error
