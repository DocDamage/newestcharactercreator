"""Isolated nonshipping synthetic topology/transaction data; NOT engine evidence."""
from hashlib import sha256
from pathlib import Path
import struct

from fixtures.godot_transaction_contract import GodotTransactionFixture
from ucc.export.godot_runtime_contract import FILES, CAPABILITY, NativeRuntimeRequest


def quad_data() -> dict[str, bytes]:
    def pack(fmt, rows):
        return b''.join(struct.pack(fmt, *row) for row in rows)
    return {'corners.u32': pack('<4I', [(3,0,1,0),(0,1,2,0),(1,2,3,0),(2,3,0,0)]),
        'face_vertices.u32': pack('<I', [(0,),(1,),(2,),(3,)]), 'face_ids.u32': pack('<I', [(0,)]*4),
        'face_ranges.u32': pack('<2I', [(0,4)]),
        'neighbor_ranges.u32': pack('<2I', [(0,2),(2,2),(4,2),(6,2)]),
        'neighbors.u32': pack('<I', [(1,),(3,),(0,),(2,),(1,),(3,),(2,),(0,)]),
        'corner_ranges.u32': pack('<2I', [(0,1),(1,1),(2,1),(3,1)]),
        'corner_indices.u32': pack('<I', [(0,),(1,),(2,),(3,)]),
        'offsets_vec4.f32': pack('<4f', [(0,0,0,1)]*4)}


class RuntimeTransactionFixture(GodotTransactionFixture):
    def __init__(self, root: Path):
        super().__init__(root)
        for name in FILES:
            (self.folder/name).write_bytes(('SYNTHETIC_NOT_RUNTIME_DATA:'+name).encode())
        self.review=self.folder/'unit-review.blend';self.review.write_bytes(b'UNIT_REVIEW_NOT_BLENDER')
        self.timeline=self.folder/'unit-timeline.json';self.timeline.write_bytes(b'{"unit_only":true}')
        digest=lambda p:sha256(p.read_bytes()).hexdigest()
        old=self.request
        self.request=NativeRuntimeRequest(old.job_id,old.project_id,old.revision,old.project_file_sha256,
            old.master_sha256,tuple((name,digest(self.folder/name)) for name in sorted(FILES)),
            old.source_bindings,(('native_review',digest(self.review)),('native_timeline',digest(self.timeline))),
            old.permissions,CAPABILITY)

    def kwargs(self) -> dict:
        return {'candidate_folder':self.folder,'motion_sources':{'motion:unit':self.motion},
                'native_evidence':{'native_review':self.review,'native_timeline':self.timeline}}
