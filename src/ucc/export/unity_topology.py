"""Versioned original quad identities for Unity's native-position normal adapter."""
from dataclasses import dataclass
from hashlib import sha256
from ucc.core.errors import ValidationError
from ucc.core.expressions import is_sha256
from .godot_candidate_contract import canonical_bytes

POLICY = 'UCC_UNITY_SOURCE_QUAD_NORMALS_V1'
MAX_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class UnityQuadSource:
    master_sha256: str
    native_mesh_sha256: str
    source_vertices: int
    native_source: tuple[int, ...]
    quads: tuple[tuple[int, int, int, int], ...]
    bone_names: tuple[str, ...]
    shape_names: tuple[str, ...]

    def __post_init__(self) -> None:
        if (not is_sha256(self.master_sha256) or not is_sha256(self.native_mesh_sha256)
                or type(self.source_vertices) is not int or not 4 <= self.source_vertices <= 100_000
                or type(self.native_source) is not tuple or not self.source_vertices <= len(self.native_source) <= 200_000
                or any(type(v) is not int or not 0 <= v < self.source_vertices for v in self.native_source)
                or set(self.native_source) != set(range(self.source_vertices))):
            raise ValidationError('Unity quad source needs complete bounded source/native vertex identities')
        if type(self.quads) is not tuple or not 1 <= len(self.quads) <= 200_000:
            raise ValidationError('Unity quad source needs bounded original faces')
        seen = set(); used = set(); edges = {}; degree = [0] * self.source_vertices
        for face in self.quads:
            if (type(face) is not tuple or len(face) != 4 or any(type(v) is not int or not 0 <= v < self.source_vertices for v in face)
                    or len(set(face)) != 4 or frozenset(face) in seen):
                raise ValidationError('Unity original quad is malformed, repeated or degenerate')
            seen.add(frozenset(face)); used.update(face)
            for vertex in face:
                degree[vertex] += 1
                if degree[vertex] > 32:
                    raise ValidationError('Unity quad-source vertex exceeds the bounded normal-work budget')
            for a, b in zip(face, face[1:] + face[:1]):
                key = (min(a, b), max(a, b)); direction = a < b
                if key in edges:
                    count, previous = edges[key]
                    if count == 2 or previous == direction:
                        raise ValidationError('Unity quad source has nonmanifold or inconsistent face winding')
                    edges[key] = (2, direction)
                else:
                    edges[key] = (1, direction)
        if used != set(range(self.source_vertices)):
            raise ValidationError('Unity normal reconstruction cannot silently omit loose source vertices')
        for names, count, label in ((self.bone_names, 163, 'bone'), (self.shape_names, 12, 'facial shape')):
            if (type(names) is not tuple or len(names) != count
                    or any(type(name) is not str or not 1 <= len(name) <= 128
                           or name.strip() != name or any(ord(c) < 32 for c in name) for name in names)
                    or len(set(names)) != count):
                raise ValidationError('Unity MPFB human profile needs exact unique '+label+' identities')
        if any(not name.startswith('UCC_EXPR_V1_') for name in self.shape_names):
            raise ValidationError('Unity quad source needs the admitted canonical expression family')
        if len(canonical_bytes(self.to_dict())) > MAX_BYTES:
            raise ValidationError('Unity quad source exceeds its bounded wire contract')

    def to_dict(self) -> dict:
        return {'schema_version': 1, 'policy': POLICY, 'rig_family': 'MPFB_HUMAN_V1',
                'master_sha256': self.master_sha256, 'native_mesh_sha256': self.native_mesh_sha256,
                'source_vertices': self.source_vertices, 'native_vertices': len(self.native_source),
                'native_source': list(self.native_source),
                'quads': [dict(zip(('a', 'b', 'c', 'd'), face)) for face in self.quads],
                'bone_names': list(self.bone_names), 'shape_names': list(self.shape_names)}

    @property
    def sha256(self) -> str:
        return sha256(canonical_bytes(self.to_dict())).hexdigest()

    def adjacency(self) -> tuple[tuple[tuple[int, int], ...], ...]:
        rows = [[] for _ in range(self.source_vertices)]
        for i, quad in enumerate(self.quads):
            for corner, vertex in enumerate(quad):
                rows[vertex].append((i, corner))
        return tuple(tuple(row) for row in rows)

    @classmethod
    def from_dict(cls, raw: dict) -> 'UnityQuadSource':
        fields = {'schema_version', 'policy', 'rig_family', 'master_sha256', 'native_mesh_sha256',
                  'source_vertices', 'native_vertices', 'native_source', 'quads', 'bone_names', 'shape_names'}
        if (type(raw) is not dict or set(raw) != fields
                or any(type(raw[k]) is not list for k in ('native_source', 'quads', 'bone_names', 'shape_names'))
                or any(type(face) is not dict or set(face) != {'a', 'b', 'c', 'd'} for face in raw['quads'])):
            raise ValidationError('Malformed closed Unity quad-source contract')
        result = cls(raw['master_sha256'], raw['native_mesh_sha256'], raw['source_vertices'],
                     tuple(raw['native_source']), tuple(tuple(face[k] for k in ('a', 'b', 'c', 'd')) for face in raw['quads']),
                     tuple(raw['bone_names']), tuple(raw['shape_names']))
        if canonical_bytes(raw) != canonical_bytes(result.to_dict()):
            raise ValidationError('Unity quad source changed version, family or declared counts')
        return result

    @classmethod
    def from_bytes(cls, data: bytes) -> 'UnityQuadSource':
        import json
        from ucc.core.storage import _unique_project_fields, _nonfinite_project_number
        if type(data) is not bytes or not 1 <= len(data) <= MAX_BYTES:
            raise ValidationError('Unity quad source needs bounded UTF-8 JSON bytes')
        try:
            raw = json.loads(data.decode('utf-8'), object_pairs_hook=_unique_project_fields,
                             parse_constant=_nonfinite_project_number)
        except (ValueError, UnicodeError, RecursionError, OverflowError) as error:
            raise ValidationError('Malformed Unity quad-source JSON') from error
        return cls.from_dict(raw)
