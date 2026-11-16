"""Position/UV correspondence and all dense facial deltas for real engine checks."""
from pathlib import Path
import struct
from ucc.core.errors import ValidationError
from ucc.core.expressions import TARGETS
from .godot_skin_evidence import _DenseSkin
from .godot_candidate_contract import canonical_bytes


def write_morph_reference(glb: Path,folder: Path) -> dict:
    reader=_DenseSkin(glb);doc=reader.document;mesh=doc['meshes'][0];primitive=mesh['primitives'][0]
    positions=reader.rows(primitive['attributes']['POSITION'],'VEC3',(5126,))
    uvs=reader.rows(primitive['attributes']['TEXCOORD_0'],'VEC2',(5126,))
    names=mesh['extras']['targetNames']
    if set(names)!={t.key_name for t in TARGETS} or len(names)!=12 or len(positions)!=len(uvs):raise ValidationError('Static export lacks exact canonical face/UV data')
    deltas=[reader.rows(target['POSITION'],'VEC3',(5126,)) for target in primitive['targets']]
    if any(len(rows)!=len(positions) for rows in deltas):raise ValidationError('Incomplete static morph reference')
    lookup={};entries=[]
    for index,(point,uv) in enumerate(zip(positions,uvs)):
        key=struct.pack('<5f',*(0. if v==0 else v for v in (*point,*uv))).hex()
        entry=(point,*[rows[index] for rows in deltas])
        if key in lookup:
            if entries[lookup[key]]!=entry:raise ValidationError('Position/UV collision has different facial deltas')
        else:lookup[key]=len(entries);entries.append(entry)
    binary=b''.join(struct.pack('<3f',*value) for entry in entries for value in entry)
    (folder/'morph_reference.bin').write_bytes(binary)
    metadata={'schema_version':1,'names':names,'lookup':lookup,'entries':len(entries),'vectors_per_entry':13,
        'position_limit_m':1e-6,'morph_limit_m':1e-5,'preview_shape':next(t.key_name for t in TARGETS if t.role=='mouth_open' and t.family=='caucasian')}
    (folder/'morph_reference.json').write_bytes(canonical_bytes(metadata));return metadata
