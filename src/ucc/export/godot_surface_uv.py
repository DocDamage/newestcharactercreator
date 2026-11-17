"""Per-polygon-corner UV fidelity, independent of Blender and material appearance."""
from collections import defaultdict
from hashlib import sha256
import math
from pathlib import Path
import struct
from typing import Callable, Sequence

from ucc.core.errors import ValidationError
from .godot_skin_evidence import _DenseSkin

POLICY = 'UCC_NATIVE_SOURCE_CORNER_UV_V1'
LIMIT = 1e-6  # UV coordinates are dimensionless, not metres.


def verify_corner_uvs(polygons: Sequence[Sequence[int]], corner_uvs: Sequence[Sequence[float]],
        imported_ids: Sequence[int], imported_uvs: Sequence[Sequence[float]], triangle_indices: Sequence[int],
        *, check: Callable[[], None]) -> dict:
    """Check all seam sides against their actual original polygon corners.

    Input UVs and exported UVs use their native conventions: Blender (u,v),
    glTF/Godot (u,1-v). Triangle order does not establish winding acceptance;
    the existing topology gate handles that independently.
    """
    if any(not isinstance(value,(tuple,list)) for value in (polygons,corner_uvs,imported_ids,imported_uvs,triangle_indices)):
        raise ValidationError('UV surface collections must be bounded concrete sequences')
    if (any(not isinstance(p,(tuple,list)) for p in polygons)
            or not 1 <= len(polygons) <= 100000 or len(corner_uvs) != sum(map(len, polygons))
            or len(corner_uvs) > 400000 or not 1 <= len(imported_ids) <= 100000
            or len(imported_uvs) != len(imported_ids) or len(triangle_indices) % 3
            or len(triangle_indices) != sum(3 * (len(p)-2) for p in polygons)):
        raise ValidationError('Incomplete source/imported UV coverage')
    def valid_uv(row) -> bool:
        return (isinstance(row,(tuple,list)) and len(row)==2
            and all(type(v) in (int,float) and math.isfinite(v) and abs(v)<=100 for v in row))
    if any(not valid_uv(row) for row in (*corner_uvs,*imported_uvs)):
        raise ValidationError('Nonfinite or unbounded source/imported UV coordinates')
    incident = defaultdict(set); expected = []; cursor = 0; signature = sha256(); source_pairs = set()
    for face, polygon in enumerate(polygons):
        check()
        if (not 3 <= len(polygon) <= 8 or len(set(polygon)) != len(polygon)
                or any(type(v) is not int or not 0 <= v < 100000 for v in polygon)):
            raise ValidationError('Invalid original UV polygon identity')
        row = {}
        for vertex in polygon:
            uv = tuple(corner_uvs[cursor]); cursor += 1; row[vertex] = uv
            incident[vertex].add(face); signature.update(struct.pack('<2f',*uv)); source_pairs.add((vertex,*uv))
        expected.append(row)
    if any(type(v) is not int or v not in incident for v in imported_ids):
        raise ValidationError('Imported UV vertex lost source identity')
    if any(type(i) is not int or not 0 <= i < len(imported_ids) for i in triangle_indices):
        raise ValidationError('Imported UV triangle index is out of range')
    covered = set(); used = set(); counts = [0]*len(polygons); maximum = 0.
    for start in range(0,len(triangle_indices),3):
        check(); indices = triangle_indices[start:start+3]; ids = [imported_ids[i] for i in indices]
        if len(set(ids)) != 3:raise ValidationError('Degenerate UV triangle')
        faces = set.intersection(*(incident[v] for v in ids))
        if len(faces) != 1:raise ValidationError('UV triangle crosses or ambiguously identifies source polygons')
        face = faces.pop(); counts[face] += 1
        for index, vertex in zip(indices,ids):
            u,v = expected[face][vertex]; actual = imported_uvs[index]
            error = max(abs(actual[0]-u),abs(actual[1]-(1.-v)))
            if error > LIMIT:raise ValidationError('Imported UV corner differs from its source polygon/seam side')
            maximum = max(maximum,error); covered.add((face,vertex)); used.add(index)
    if (len(covered) != len(corner_uvs) or used != set(range(len(imported_ids)))
            or counts != [len(p)-2 for p in polygons]):
        raise ValidationError('Imported UV triangles lost complete face/corner/vertex coverage')
    return {'policy':POLICY,'source_polygons':len(polygons),'source_corners':len(corner_uvs),
        'source_vertex_uv_pairs':len(source_pairs),'imported_vertices':len(imported_ids),
        'triangles':len(triangle_indices)//3,'source_corner_uv_sha256':signature.hexdigest(),
        'maximum_uv_component_error':maximum,'uv_limit':LIMIT,'material_appearance_verified':False,'engine_import_verified':False}


def read_glb_uvs(path: Path,bind: Sequence[Sequence[float]],*,expected_sha256:str|None=None) -> tuple[list,list,list]:
    reader = _DenseSkin(path)
    if expected_sha256 is not None:
        if sha256(reader.raw).hexdigest()!=expected_sha256:
            raise ValidationError('GLB UV parser buffer differs from admitted source SHA')
    try:
        doc = reader.document; primitive = doc['meshes'][0]['primitives'][0]; attributes = primitive['attributes']
        def key(point):return struct.pack('<3f',*(0. if value==0 else value for value in point))
        mapping = {key(point):index for index,point in enumerate(bind)}
        if len(mapping) != len(bind):raise ValidationError('Ambiguous bind/source UV correspondence')
        points = reader.rows(attributes['POSITION'],'VEC3',(5126,))
        ids = [mapping[key(point)] for point in points]
        uvs = reader.rows(attributes['TEXCOORD_0'],'VEC2',(5126,))
        triangles = [row[0] for row in reader.rows(primitive['indices'],'SCALAR',(5121,5123,5125))]
        return ids,uvs,triangles
    except (KeyError,TypeError,IndexError,struct.error) as error:
        raise ValidationError('GLB lacks complete source-bound UV data') from error


def verify_glb_uvs(path: Path,bind: Sequence[Sequence[float]],polygons: Sequence[Sequence[int]],
                    corner_uvs: Sequence[Sequence[float]],*,check: Callable[[],None]) -> dict:
    ids,uvs,triangles=read_glb_uvs(path,bind)
    return verify_corner_uvs(polygons,corner_uvs,ids,uvs,triangles,check=check)


def glb_corner_reference(polygons: Sequence[Sequence[int]],ids: list,uvs: list,triangles: list,
                         *,check: Callable[[],None]) -> list[tuple[float,float]]:
    """Derive admitted GLB corner UVs for an independent engine readback check.

    This is an admitted-GLB reference, not a substitute for the Blender source
    comparison performed by the producer/reopening worker.
    """
    incident=defaultdict(set);values={}
    for face,polygon in enumerate(polygons):
        for vertex in polygon:incident[vertex].add(face)
    try:
        if len(uvs)!=len(ids) or len(triangles)%3:raise ValueError('Incomplete UV reference')
        for start in range(0,len(triangles),3):
            check();corners=triangles[start:start+3];vertices=[ids[index] for index in corners]
            faces=set.intersection(*(incident[v] for v in vertices))
            if len(faces)!=1:raise ValueError('Ambiguous UV reference polygon')
            face=faces.pop()
            for index,vertex in zip(corners,vertices):
                uv=uvs[index];key=(face,vertex)
                if key in values and values[key]!=uv:raise ValueError('GLB split UV within one original polygon')
                values[key]=uv
        reference=[(values[face,vertex][0],1.-values[face,vertex][1]) for face,polygon in enumerate(polygons) for vertex in polygon]
    except (KeyError,IndexError,TypeError,ValueError) as error:
        raise ValidationError('Invalid admitted GLB corner UV reference') from error
    verify_corner_uvs(polygons,reference,ids,uvs,triangles,check=check)
    return reference
