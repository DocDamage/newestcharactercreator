"""Fresh two-worker source-skeleton preparation; no target or catalog writes."""
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping

from ucc.animations.fbx_snapshot import MAX_SOURCE_BYTES, MAX_SNAPSHOT_BYTES
from ucc.animations.catalog_clip import text
from ucc.animations.source_rest_frames import is_sha256
from ucc.core.errors import ValidationError, ProjectStorageError
from ucc.library.provenance import LicensePolicy, AssetPolicyError
from .catalog_clip import _saved_reference
from .fbx_intake import inspect_selected_fbx
from .godot_saved_preview_catalog import final_catalog_guard
from .source_skeleton_files import capture, check_identities, watch_identity
from .target_action_context import operation_budget, protected


@dataclass(frozen=True, slots=True)
class LoadedSourceSkeletonPreview:
    cache: object
    clip_id: str
    source_sha256: str
    snapshot_sha256: str
    receipt_sha256: str
    database_path: Path
    watch_paths: tuple[Path, ...]
    watched_identities: Mapping[Path, tuple[int, int, int, int]]
    guard: Callable

    @property
    def source_clock(self):
        return self.cache.clock


def prepare_source_skeleton_preview(database_path: Path, clip_id: str, *,
        expected_source_sha256: str, expected_policy: LicensePolicy,
        local_preview_confirmed: bool, blender_exe: Path, worker_script: Path,
        jobs_root: Path, cancel=None, timeout_s: float = 300) -> LoadedSourceSkeletonPreview:
    """Use caller-bound selected identity and fresh private two-worker evidence.

    The returned guard performs heavy checks and belongs on a background worker.
    UI consumers invalidate using only watch events and cheap identity polling.
    """
    if (local_preview_confirmed is not True or not text(clip_id, 138)
            or not is_sha256(expected_source_sha256) or not isinstance(expected_policy, LicensePolicy)):
        raise ValidationError('Select an exact source and explicitly confirm private local playback')
    allowed, reason = expected_policy.allow('local_preview')
    if not allowed: raise AssetPolicyError(reason)
    database = protected(Path(database_path)); jobs = protected(Path(jobs_root))
    with operation_budget(cancel, timeout_s) as budget:
        original = _saved_reference(database, clip_id, expected_source_sha256, expected_policy)
        entry, indexed, receipt, receipt_sha = original
        source = protected(Path(entry.source_path))
        _, source_identity = capture(source, MAX_SOURCE_BYTES, budget, expected=entry.sha256)
        if source.stat().st_size != entry.size_bytes:
            raise ProjectStorageError('Selected source size differs from the catalog')
        report = inspect_selected_fbx(source, blender_exe=blender_exe, worker_script=worker_script,
            jobs_root=jobs, permission=expected_policy, cancel=budget.cancel, timeout_s=budget.remaining())
        budget.check()
        if (type(report) is not dict or report.get('status') != 'REAL_BLENDER_FBX_SOURCE_SNAPSHOT'
                or report.get('two_workers_agree') is not True or report.get('source_bytes_unchanged') is not True
                or report.get('source_sha256') != entry.sha256 or report.get('policy') != expected_policy.to_dict()
                or report.get('source_path') != str(source)
                or any(type(report.get(k)) is not type(v) or report[k] != v
                       for k, v in receipt['observation'].items())
                or type(report.get('snapshot')) is not dict
                or report['snapshot'].get('name') != 'source_snapshot.json'
                or report['snapshot'].get('sha256') != receipt['snapshot_sha256']
                or any(report.get(k) is not False for k in
                       ('retargeting_verified', 'animation_visual_quality_verified', 'engine_import_verified'))):
            raise ValidationError('Fresh source measurement differs from its selected catalog receipt')
        snapshot = protected(Path(report['private_snapshot']))
        if (snapshot.name != 'source_snapshot.json' or snapshot.parent.parent != jobs
                or snapshot == source):
            raise ValidationError('Fresh source snapshot escaped its private jobs namespace')
        payload, snapshot_identity = capture(snapshot, MAX_SNAPSHOT_BYTES, budget,
            expected=receipt['snapshot_sha256'], retain=True)
        if len(payload) != report['snapshot']['bytes']:
            raise ValidationError('Fresh source snapshot size differs')
        from ucc.animations.source_skeleton import build_source_skeleton_cache
        cache = build_source_skeleton_cache(payload, source_sha256=entry.sha256,
            snapshot_sha256=receipt['snapshot_sha256'], cancel_check=budget.check)
        identities = {source: source_identity, snapshot: snapshot_identity}
        for path in (source.parent, snapshot.parent, database.parent):
            identities[path] = watch_identity(path)

        def logical_check():
            budget.check()
            if _saved_reference(database, clip_id, entry.sha256, expected_policy) != original:
                raise ProjectStorageError('Selected source catalog identity or policy changed')

        capture(source, MAX_SOURCE_BYTES, budget, expected=entry.sha256)
        capture(snapshot, MAX_SNAPSHOT_BYTES, budget, expected=receipt['snapshot_sha256'])
        check_identities(identities, budget)
        identities.update(final_catalog_guard(database, budget, logical_check))
        check_identities(identities, budget)
        frozen = MappingProxyType(dict(identities))
        budget.check()

    def guard(*, cancel=None, timeout_s=300):
        with operation_budget(cancel, timeout_s) as fresh:
            check_identities(frozen, fresh)
            capture(source, MAX_SOURCE_BYTES, fresh, expected=entry.sha256)
            capture(snapshot, MAX_SNAPSHOT_BYTES, fresh, expected=receipt['snapshot_sha256'])
            def logical():
                fresh.check()
                if _saved_reference(database, clip_id, entry.sha256, expected_policy) != original:
                    raise ProjectStorageError('Source playback permissions or metadata changed')
            final_catalog_guard(database, fresh, logical)
            # This owned read may update SHM read marks. The fence checks its
            # current ownership; SHM is never permission authority. Do not
            # replace the returned UI baseline with these new coordination data.
            check_identities({p:v for p,v in frozen.items()
                              if p != database.with_name(database.name+'-shm')}, fresh)
        return True

    watches = tuple(sorted((p for p, value in frozen.items() if value != (0, 0, 0, 0)), key=str))
    return LoadedSourceSkeletonPreview(cache, clip_id, entry.sha256, receipt['snapshot_sha256'],
        receipt_sha, database, watches, frozen, guard)
