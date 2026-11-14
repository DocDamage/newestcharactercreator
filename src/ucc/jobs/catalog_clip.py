"""Fresh verification of one exact source-catalog clip before project admission."""
from hashlib import sha256
from pathlib import Path
from threading import Event

from ucc.animations.catalog import AnimationCatalog
from ucc.animations.catalog_clip import MAX_RECEIPT_BYTES, VerifiedCatalogClip, checked_receipt, text
from ucc.animations.metadata import AnimationMetadataError
from ucc.animations.source_rest_frames import is_sha256
from ucc.jobs.fbx_catalog import measure_catalog_fbx
from ucc.jobs.runner import WorkerFailure
from ucc.library.provenance import AssetPolicyError, LicensePolicy


def _saved_reference(database_path, clip_id, source_sha, policy):
    with AnimationCatalog(database_path) as catalog:
        row = catalog.db.execute('''SELECT substr(asset_id,1,129),ordinal,
            length(CAST(metadata_json AS BLOB)),typeof(metadata_json) FROM animation_clips WHERE clip_id=?''', (clip_id,)).fetchone()
        if (row is None or not text(row[0], 128) or type(row[1]) is not int or row[1] != 0
                or clip_id != row[0]+'#clip-0000'):
            raise AnimationMetadataError('Select an existing measured single-Action FBX clip ID')
        sizes = catalog.db.execute('''SELECT length(CAST(license_json AS BLOB)),length(CAST(source_path AS BLOB))
            FROM asset_sources WHERE asset_id=?''', (row[0],)).fetchone()
        source_sizes = catalog.db.execute('''SELECT length(CAST(bone_names_json AS BLOB)),typeof(bone_names_json),
            length(CAST(warnings_json AS BLOB)),typeof(warnings_json) FROM animation_sources WHERE asset_id=?''', (row[0],)).fetchone()
        receipt_size = catalog.db.execute('''SELECT length(CAST(receipt_json AS BLOB)),typeof(receipt_json)
            FROM animation_fbx_intakes WHERE asset_id=?''', (row[0],)).fetchone()
        if receipt_size is None:
            raise AnimationMetadataError('Catalog clip has no measured FBX intake receipt')
        if (sizes is None or source_sizes is None or any(type(n) is not int or not 0 < n <= 128*1024 for n in sizes)
                or any(type(n) is not int or not 0 < n <= MAX_RECEIPT_BYTES
                       for n in (row[2], source_sizes[0], source_sizes[2], receipt_size[0]))
                or any(t != 'text' for t in (row[3], source_sizes[1], source_sizes[3], receipt_size[1]))):
            raise AnimationMetadataError('Catalog clip metadata is missing, oversized or not text')
        entry = catalog.library.get(row[0])
        if entry is None or entry.sha256 != source_sha or entry.policy != policy:
            raise AssetPolicyError('Catalog clip differs from its bound source hash or exact reviewed policy')
        try:
            indexed = catalog.get(entry.asset_id)
        except (ValueError, TypeError, KeyError, RecursionError, UnicodeError) as error:
            raise AnimationMetadataError('Stored catalog clip metadata is malformed') from error
        raw = catalog.db.execute('SELECT receipt_json FROM animation_fbx_intakes WHERE asset_id=?', (entry.asset_id,)).fetchone()
        if indexed is None or raw is None:
            raise AnimationMetadataError('Catalog clip has no measured FBX intake receipt')
        receipt = checked_receipt(indexed, raw[0], source_sha)
        return entry, indexed, receipt, sha256(raw[0].encode('utf-8')).hexdigest()


def verify_catalog_fbx_clip(database_path: Path, clip_id: str, *, expected_source_sha256: str,
                            expected_policy: LicensePolicy, blender_exe: Path, worker_script: Path,
                            jobs_root: Path, cancel: Event | None = None, timeout_s: float = 300) -> VerifiedCatalogClip:
    """Require caller-bound identity and a fresh complete two-worker source check.

    The result says nothing about an editable target master, retargeting, root
    or loop quality. Project registration must independently verify those.
    """
    def check_cancel():
        if cancel is not None and cancel.is_set():
            raise WorkerFailure('Catalog clip verification cancelled; project unchanged')
    check_cancel()
    if not text(clip_id, 138) or not is_sha256(expected_source_sha256) or not isinstance(expected_policy, LicensePolicy):
        raise AnimationMetadataError('Catalog verification requires an exact clip ID, source SHA and reviewed policy')
    allowed, reason = expected_policy.allow('local_preview')
    if not allowed: raise AssetPolicyError(reason)
    before = _saved_reference(database_path, clip_id, expected_source_sha256, expected_policy)
    measured = measure_catalog_fbx(database_path, before[0].asset_id, blender_exe=blender_exe,
        worker_script=worker_script, jobs_root=jobs_root, cancel=cancel, timeout_s=timeout_s)
    check_cancel()
    after = _saved_reference(database_path, clip_id, expected_source_sha256, expected_policy)
    if after != before or measured != before[1].to_dict():
        raise AnimationMetadataError('Catalog clip changed during fresh source verification')
    entry, indexed, receipt, receipt_sha = after
    observation = receipt['observation']
    return VerifiedCatalogClip(clip_id, entry.asset_id, entry.sha256, entry.policy,
        receipt['snapshot_sha256'], receipt_sha, receipt['skeleton_fingerprint'],
        observation['first_frame'], observation['last_frame'], indexed.clips[0])
