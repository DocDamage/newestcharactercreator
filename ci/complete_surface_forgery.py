"""Coherent false contacts for real original-source worker rejection tests."""
from hashlib import sha256
import json
from pathlib import Path
import struct

from ucc.preview.central_surface import _parse_variant

MAX_REPORT_BYTES=64*1024*1024


def _write_bounded_forgery(path,data):
    # Match the producer's compact encoding. Whitespace can otherwise push a
    # valid paired report over the worker bound before physical comparison.
    payload=json.dumps(data,allow_nan=False,separators=(',',':')).encode('utf-8')
    if not 0<len(payload)<=MAX_REPORT_BYTES:
        raise RuntimeError('Coherent complete-contact fixture exceeds the worker input bound')
    with path.open('xb') as stream:stream.write(payload)


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
    _write_bounded_forgery(path,full)
    return path
