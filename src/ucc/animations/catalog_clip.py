"""Closed source-catalog reference checks; no target animation approval."""
from dataclasses import dataclass
import json
import math

from ucc.animations.fbx_catalog import POLICY, WARNING
from ucc.animations.source_rest_frames import is_sha256
from ucc.animations.source_clip_clock import SourceClipClock
from ucc.animations.metadata import AnimationMetadataError, ClipMetadata
from ucc.library.provenance import LicensePolicy

MAX_RECEIPT_BYTES = 512*1024
OBSERVATION = {'bone_count', 'root_count', 'frame_count', 'first_frame', 'last_frame', 'fps', 'action', 'blender_version'}


@dataclass(frozen=True, slots=True)
class VerifiedCatalogClip:
    clip_id: str
    asset_id: str
    source_sha256: str
    license_policy: LicensePolicy
    snapshot_sha256: str
    receipt_sha256: str
    skeleton_fingerprint: str
    first_frame: int
    last_frame: int
    clip: ClipMetadata

    @property
    def source_clock(self) -> SourceClipClock:
        """Timing of this source reference, without target-clock coercion."""
        return SourceClipClock(self.first_frame, self.last_frame,
                               self.clip.frame_count, self.clip.fps)

    @property
    def target_preview_verified(self) -> bool:
        return False

    @property
    def engine_import_verified(self) -> bool:
        return False


def text(value, maximum):
    return type(value) is str and 0 < len(value) <= maximum and all(ord(c) >= 32 for c in value)


def _unique(rows):
    result = {}
    for key, value in rows:
        if key in result: raise ValueError('Duplicate catalog receipt field')
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError('Nonfinite catalog receipt number')


def checked_receipt(indexed, raw: str, expected_source_sha256: str) -> dict:
    """Check saved metadata coherence; a fresh Blender intake is still required."""
    if type(raw) is not str or len(raw) > MAX_RECEIPT_BYTES:
        raise AnimationMetadataError('Catalog receipt is missing or oversized')
    try:
        if len(raw.encode('utf-8')) > MAX_RECEIPT_BYTES:
            raise ValueError('Oversized catalog receipt bytes')
        receipt = json.loads(raw, object_pairs_hook=_unique, parse_constant=_nonfinite)
        fields = {'schema_version', 'policy', 'source_sha256', 'snapshot_sha256', 'observation', 'skeleton_fingerprint', 'clip'}
        if (type(receipt) is not dict or set(receipt) != fields or type(receipt['schema_version']) is not int
                or receipt['schema_version'] != 1 or receipt['policy'] != POLICY
                or not is_sha256(expected_source_sha256) or receipt['source_sha256'] != expected_source_sha256
                or not is_sha256(receipt['snapshot_sha256']) or not is_sha256(receipt['skeleton_fingerprint'])):
            raise ValueError('Catalog receipt identity differs')
        obs = receipt['observation']
        if (type(obs) is not dict or set(obs) != OBSERVATION
                or any(type(obs[k]) is not int for k in ('bone_count', 'root_count', 'frame_count', 'first_frame', 'last_frame'))
                or not 1 <= obs['root_count'] <= obs['bone_count'] <= 256
                or not 2 <= obs['frame_count'] == obs['last_frame']-obs['first_frame']+1 <= 2400
                or obs['bone_count']*obs['frame_count'] > 100000
                or max(abs(obs['first_frame']), abs(obs['last_frame'])) > 100000
                or type(obs['fps']) not in (int, float) or not math.isfinite(obs['fps']) or not 1 <= obs['fps'] <= 240
                or not text(obs['action'], 512) or not text(obs['blender_version'], 64)):
            raise ValueError('Catalog receipt source observations are incomplete')
        names = indexed.bone_names
        if (type(names) is not tuple or len(names) != obs['bone_count'] or any(not text(n, 128) for n in names)
                or len({n.casefold() for n in names}) != len(names)):
            raise ValueError('Catalog skeleton names differ')
        clip = receipt['clip']
        if (type(clip) is not dict or set(clip) != set(ClipMetadata.__dataclass_fields__)
                or type(clip['ordinal']) is not int or clip['ordinal'] != 0 or clip['name'] != obs['action']
                or type(clip['frame_count']) is not int or clip['frame_count'] != obs['frame_count']
                or type(clip['fps']) is not type(obs['fps']) or clip['fps'] != obs['fps']
                or type(clip['duration_seconds']) is not float
                or clip['duration_seconds'] != (obs['last_frame']-obs['first_frame'])/obs['fps']
                or type(clip['track_count']) is not int or not 1 <= clip['track_count'] <= obs['bone_count']+1
                or type(clip['animated_bones']) is not list or any(not text(n, 128) for n in clip['animated_bones'])
                or len(set(clip['animated_bones'])) != len(clip['animated_bones'])
                or clip['animated_bones'] != [n for n in names if n in set(clip['animated_bones'])]
                or not len(clip['animated_bones']) <= clip['track_count'] <= len(clip['animated_bones'])+1
                or clip['warnings'] != [WARNING]):
            raise ValueError('Catalog clip differs from its complete source observations')
        if (indexed.source_format != 'fbx' or indexed.status != 'METADATA_EXTRACTED'
                or indexed.sha256 != expected_source_sha256 or indexed.skeleton_fingerprint != receipt['skeleton_fingerprint']
                or indexed.warnings != ('Complete source sampled by independent Blender workers; target preview and quality remain unverified.',)
                or len(indexed.clips) != 1
                or json.dumps(indexed.clips[0].to_dict(), sort_keys=True, allow_nan=False)
                    != json.dumps(clip, sort_keys=True, allow_nan=False)):
            raise ValueError('Catalog row and measured receipt disagree')
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError, OverflowError) as error:
        raise AnimationMetadataError('Invalid measured catalog clip receipt: '+str(error)) from error
    return receipt
