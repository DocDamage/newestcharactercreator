"""Closed project-side source bindings, using existing catalog clip identifiers."""
from ucc.animations.catalog_clip import VerifiedCatalogClip, text
from ucc.animations.metadata import ClipMetadata
from ucc.animations.source_rest_frames import is_sha256
from ucc.core.errors import ValidationError
from ucc.library.provenance import LicensePolicy

POLICY = 'PROJECT_EXTERNAL_FBX_SOURCE_REFERENCE_V1'
MAX_REFERENCE_BYTES = 512*1024
MAX_PROJECT_REFERENCES = 128
HASHES = {'source_sha256', 'snapshot_sha256', 'source_receipt_sha256', 'skeleton_fingerprint'}
FLAGS = {'source_only': True, 'source_rights_retained': True, 'target_preview_verified': False,
         'engine_import_verified': False, 'editing_authorized': False}


def build_source_binding(project_id: str, reference: VerifiedCatalogClip) -> dict:
    record = {'schema_version': 1, 'policy': POLICY, 'project_id': project_id,
        'clip_id': reference.clip_id, 'asset_id': reference.asset_id, 'source_sha256': reference.source_sha256,
        'license': reference.license_policy.to_dict(), 'snapshot_sha256': reference.snapshot_sha256,
        'source_receipt_sha256': reference.receipt_sha256, 'skeleton_fingerprint': reference.skeleton_fingerprint,
        'first_frame': reference.first_frame, 'last_frame': reference.last_frame,
        'clip': reference.clip.to_dict(), **FLAGS}
    return validate_source_binding(record, project_id, reference.clip_id)


def validate_source_binding(raw: object, project_id: str, clip_id: str) -> dict:
    fields = {'schema_version', 'policy', 'project_id', 'clip_id', 'asset_id', 'license', 'first_frame', 'last_frame', 'clip'}|HASHES|set(FLAGS)
    if (type(raw) is not dict or set(raw) != fields or type(raw['schema_version']) is not int or raw['schema_version'] != 1
            or raw['policy'] != POLICY or raw['project_id'] != project_id or raw['clip_id'] != clip_id
            or not text(project_id, 200) or not text(clip_id, 138) or not text(raw['asset_id'], 128)
            or clip_id != raw['asset_id']+'#clip-0000' or any(not is_sha256(raw[k]) for k in HASHES)
            or any(type(raw[k]) is not bool or raw[k] is not v for k, v in FLAGS.items())
            or any(type(raw[k]) is not int or abs(raw[k]) > 100000 for k in ('first_frame', 'last_frame'))
            or not 2 <= raw['last_frame']-raw['first_frame']+1 <= 2400
            or type(raw['clip']) is not dict or set(raw['clip']) != set(ClipMetadata.__dataclass_fields__)):
        raise ValidationError('Invalid or foreign source-only project animation binding')
    policy = LicensePolicy.from_dict(raw['license'])
    allowed, reason = policy.allow('local_preview')
    if not allowed: raise ValidationError('Registered source lacks reviewed local preview rights: '+reason)
    return raw
