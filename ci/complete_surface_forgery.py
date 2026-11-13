"""Coherent false contacts for real original-source worker rejection tests."""
from hashlib import sha256
import json
from pathlib import Path
import struct

from ucc.preview.central_surface import _parse_variant


def forged_complete_contact(review,cache,path,*,variant='original'):
    full=json.loads(Path(review.private_full_trunk_report).read_text(encoding='utf-8'))
    volume=json.loads(Path(review.private_enclosure_report).read_text(encoding='utf-8'))
    polygons=json.loads(Path(review.private_report).read_text(encoding='utf-8'))['polygons']
    row=next(r for r in full[variant]['frames'] if r['observation']['left']['pair_count']==0)
    hit=row['observation']['left'];hand=hit['selected_hand_triangles'][0];body=row['observation']['body_triangle_ids'][0]
    _,indices=cache.frame(row['frame']-1)
    def polygon(triangle):
        vertices=struct.unpack_from('<III',indices,triangle*12)
        return next(i for i,p in enumerate(polygons) if set(vertices)<=set(p))
    hit.update(pair_count=1,pair_sha256=sha256(struct.pack('<II',hand,body)).hexdigest(),hand_triangles=[hand],
        central_triangles=[body],hand_polygons=[polygon(hand)],body_polygons=[polygon(body)])
    # Metadata is internally coherent; a fresh physical comparison is required.
    _parse_variant(full[variant],cache,volume[variant],polygons)
    with path.open('x',encoding='utf-8') as stream:json.dump(full,stream)
    return path
