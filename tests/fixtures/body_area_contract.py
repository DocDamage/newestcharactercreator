"""Invented polygon wrapper solely for closed-contract and transaction tests."""
from hashlib import sha256
import json
import struct


def wrap_body_areas(contacts,cache):
    # These invented fixture faces cover its changing synthetic triangles.
    # They are metadata for parser tests, never a physical Blender mesh claim.
    seen={}
    for frame in range(cache.frame_count):
        for face in struct.iter_unpack('<III',cache.frame(frame)[1]):seen.setdefault(tuple(sorted(face)),list(face))
    polygons=list(seen.values())
    return {'schema_version':1,'policy':'STATIC_EVALUATED_POLYGON_CONTACT_AREAS_V1','status':'CHECKED','reason':'',
        'bindings':dict(contacts['bindings']),'body_contacts':contacts,'polygons':polygons,
        'polygon_topology_sha256':sha256(json.dumps(polygons,separators=(',',':')).encode()).hexdigest(),
        'originals_unchanged':True,'contact_quality_verified':False,'animation_visual_quality_verified':False,'engine_import_verified':False}
