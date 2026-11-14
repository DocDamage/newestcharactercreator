"""Aggregate clip metadata derived from a complete validated native snapshot.

Only the existing single-Action FBX importer is supported. Measured tracks
describe sampled transforms, not original FCurves or target motion quality.
"""
from hashlib import sha256
import json

from ucc.animations.fbx_snapshot import validate_snapshot
from ucc.animations.metadata import AnimationInspection, ClipMetadata

POLICY = 'MEASURED_SINGLE_ACTION_FBX_CLIP_METADATA_V1'
WARNING = 'Track count describes changing sampled transforms, not original animation channels.'


def measured_metadata(data: dict, source_sha256: str, *, cancel_check=lambda: None) -> AnimationInspection:
    validate_snapshot(data, source_sha256, cancel_check=cancel_check)
    first = data['frames'][0]
    changed = set()
    object_changed = False
    for row in data['frames'][1:]:
        cancel_check()
        object_changed |= row['armature_world'] != first['armature_world']
        changed.update(i for i, matrix in enumerate(row['poses']) if matrix != first['poses'][i])
    fingerprint = sha256(json.dumps(data['bones'], sort_keys=True, separators=(',', ':'),
                                    allow_nan=False).encode('utf-8')).hexdigest()
    clip = ClipMetadata(0, data['action'], (data['last_frame']-data['first_frame'])/data['fps'],
        len(data['frames']), data['fps'], len(changed)+int(object_changed),
        tuple(b['name'] for i, b in enumerate(data['bones']) if i in changed), (WARNING,))
    return AnimationInspection('fbx', 'METADATA_EXTRACTED', fingerprint,
        tuple(b['name'] for b in data['bones']), (clip,),
        ('Complete source sampled by independent Blender workers; target preview and quality remain unverified.',))
