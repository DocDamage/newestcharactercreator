"""SQLite-backed private animation intake with explicit source provenance.

The catalog stores extracted metadata and content hashes, never proprietary
motion bytes. An indexed clip is NOT retargeted, previewed or engine-ready.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import sqlite3
from pathlib import Path
from typing import Any

from ucc.animations.metadata import (
    AnimationInspection, AnimationMetadataError, ClipMetadata, inspect_animation_file,
)
from ucc.core.errors import ValidationError
from ucc.library.provenance import AssetEntry, AssetLibrary, AssetPolicyError, LicensePolicy


@dataclass(frozen=True, slots=True)
class IndexedAnimation:
    asset_id: str
    sha256: str
    source_format: str
    status: str
    skeleton_fingerprint: str | None
    bone_names: tuple[str, ...]
    clips: tuple[ClipMetadata, ...]
    warnings: tuple[str, ...]
    rights: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1, "asset_id": self.asset_id, "sha256": self.sha256, "format": self.source_format,
            "status": self.status, "skeleton_fingerprint": self.skeleton_fingerprint,
            "bone_names": list(self.bone_names),
            "clips": [{"clip_id": f"{self.asset_id}#clip-{c.ordinal:04d}", **c.to_dict()}
                      for c in self.clips],
            "warnings": list(self.warnings), "permissions": self.rights,
            "preview_verified": False, "retarget_verified": False, "engine_validated": False,
        }


def _policy_rights(policy: LicensePolicy) -> dict[str, str]:
    decisions: dict[str, str] = {}
    for target in ("unreal", "godot", "unity"):
        permitted, reason = policy.allow("engine_export", target)
        decisions[target] = "allowed_by_reviewed_policy" if permitted else "BLOCKED: " + reason
    for operation in ("ai_input", "ship_source"):
        permitted, reason = policy.allow(operation)
        decisions[operation] = "allowed_by_reviewed_policy" if permitted else "BLOCKED: " + reason
    return decisions


class AnimationCatalog:
    """Optional tables inside a local AssetLibrary database (non-destructive)."""

    def __init__(self, database_path: str | Path, *, read_only: bool = False):
        self.library = AssetLibrary(database_path, read_only=read_only)
        self.db = self.library.db
        if read_only:
            try:
                self.library._require_table('animation_sources',
                    ('asset_id', 'format', 'status', 'fingerprint', 'bone_names_json', 'warnings_json'))
                self.library._require_table('animation_clips', ('clip_id', 'asset_id', 'ordinal', 'metadata_json'))
                self.library._require_table('animation_fbx_intakes', ('asset_id', 'receipt_json'))
            except (AssetPolicyError, sqlite3.Error) as error:
                self.library.close()
                if isinstance(error, AssetPolicyError):
                    raise
                raise AnimationMetadataError("Stored animation catalog cannot be read safely") from error
            return
        # Both tables can be added to a v1 source DB without altering its existing rows.
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS animation_sources (
                asset_id TEXT PRIMARY KEY REFERENCES asset_sources(asset_id) ON DELETE RESTRICT,
                format TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('METADATA_EXTRACTED','REQUIRES_CONVERSION')),
                fingerprint TEXT,
                bone_names_json TEXT NOT NULL,
                warnings_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS animation_clips (
                clip_id TEXT PRIMARY KEY,
                asset_id TEXT NOT NULL REFERENCES animation_sources(asset_id) ON DELETE RESTRICT,
                ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
                metadata_json TEXT NOT NULL,
                UNIQUE(asset_id, ordinal)
            );
            CREATE INDEX IF NOT EXISTS idx_clips_asset ON animation_clips(asset_id, ordinal);
            CREATE TABLE IF NOT EXISTS animation_fbx_intakes (
                asset_id TEXT PRIMARY KEY REFERENCES animation_sources(asset_id) ON DELETE RESTRICT,
                receipt_json TEXT NOT NULL
            );
        """)

    def __enter__(self) -> "AnimationCatalog":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.library.close()

    def index_file(self, asset_id: str, file_path: str | Path, policy: LicensePolicy) -> IndexedAnimation:
        """Only inspects the single user-selected file, no recursive scanning."""
        source = Path(file_path).expanduser()
        if source.is_symlink() or not source.is_file():
            raise AnimationMetadataError("Animation source must be an existing regular file")
        before = source.stat()
        # Extract *before* registering, so malformed input cannot create an asset row.
        inspected = inspect_animation_file(source)
        after = source.stat()
        if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
            raise AnimationMetadataError("Animation file changed while reading metadata")
        asset = self.library.register(asset_id, source, policy)
        previous = self.get(asset_id)
        if previous is not None:
            if previous.sha256 != asset.sha256:
                raise AssetPolicyError("Cannot change indexed animation content under the same ID")
            return previous
        # Our schema has bounded per-file metadata, but still guard bad dynamic content.
        if len(inspected.clips) > 10_000 or len(inspected.bone_names) > 20_000:
            raise AnimationMetadataError("Too many clips or joints to catalog")
        bone_json = json.dumps(inspected.bone_names, ensure_ascii=False)
        warnings_json = json.dumps(inspected.warnings, ensure_ascii=False)
        with self.db:
            self.db.execute("""INSERT INTO animation_sources
                (asset_id,format,status,fingerprint,bone_names_json,warnings_json)
                VALUES (?,?,?,?,?,?)""", (asset.asset_id, inspected.format, inspected.status,
                                             inspected.skeleton_fingerprint, bone_json, warnings_json))
            for clip in inspected.clips:
                # Stable within an immutable source; distinct source IDs remain distinct.
                clip_id = f"{asset.asset_id}#clip-{clip.ordinal:04d}"
                self.db.execute("""INSERT INTO animation_clips
                    (clip_id,asset_id,ordinal,metadata_json) VALUES (?,?,?,?)""",
                    (clip_id, asset.asset_id, clip.ordinal, json.dumps(clip.to_dict(),
                            ensure_ascii=False, sort_keys=True, allow_nan=False)))
        result = self.get(asset_id)
        if result is None:
            raise RuntimeError("Indexed animation is missing after transaction")
        return result

    def record_fbx_intake(self, asset_id: str, data: dict, report: dict, *,
                          expected_entry: AssetEntry, cancel_check=lambda: None) -> None:
        """Publish one measured clip and bounded receipt in a single transaction.

        The job coordinator supplies two-worker intake, never a filename-derived
        clip. Existing policies and any incompatible measured identities stay
        immutable. This cannot grant target-preview or engine approval.
        """
        from ucc.animations.fbx_catalog import POLICY, measured_metadata
        from ucc.animations.fbx_snapshot import validate_snapshot
        from ucc.animations.source_rest_frames import is_sha256
        inspected = measured_metadata(data, expected_entry.sha256, cancel_check=cancel_check)
        observed = validate_snapshot(data, expected_entry.sha256, cancel_check=cancel_check)
        if (type(report) is not dict or report.get('status') != 'REAL_BLENDER_FBX_SOURCE_SNAPSHOT'
                or report.get('source_sha256') != expected_entry.sha256
                or report.get('two_workers_agree') is not True or report.get('source_bytes_unchanged') is not True
                or report.get('policy') != expected_entry.policy.to_dict()
                or any(type(report.get(k)) is not type(v) or report[k] != v for k, v in observed.items())
                or any(report.get(k) is not False for k in
                       ('retargeting_verified', 'animation_visual_quality_verified', 'engine_import_verified'))):
            raise AnimationMetadataError('Measured FBX report differs from its complete source snapshot')
        snapshot = report.get('snapshot')
        if (type(snapshot) is not dict or set(snapshot) != {'name', 'bytes', 'sha256'}
                or snapshot['name'] != 'source_snapshot.json' or type(snapshot['bytes']) is not int
                or not 0 < snapshot['bytes'] <= 64*1024*1024 or not is_sha256(snapshot['sha256'])):
            raise AnimationMetadataError('Measured FBX requires a bound private snapshot identity')
        receipt = {'schema_version': 1, 'policy': POLICY, 'source_sha256': expected_entry.sha256,
                   'snapshot_sha256': snapshot['sha256'], 'observation': observed,
                   'skeleton_fingerprint': inspected.skeleton_fingerprint,
                   'clip': inspected.clips[0].to_dict()}
        encoded = json.dumps(receipt, sort_keys=True, separators=(',', ':'), allow_nan=False)
        with self.db:
            self.db.execute('BEGIN IMMEDIATE')
            if expected_entry.asset_id != asset_id or self.library.get(asset_id) != expected_entry:
                raise AssetPolicyError('Indexed FBX identity or permissions changed during measurement')
            self.library.require_permission(asset_id, 'local_preview')
            source = Path(expected_entry.source_path)
            if (source.suffix.lower() != '.fbx' or source.is_symlink() or not source.is_file()
                    or source.stat().st_size != expected_entry.size_bytes):
                raise AssetPolicyError('Indexed FBX source is missing, redirected or changed')
            checksum = sha256()
            with source.open('rb') as stream:
                for block in iter(lambda: stream.read(1024*1024), b''):
                    cancel_check(); checksum.update(block)
            if source.is_symlink() or checksum.hexdigest() != expected_entry.sha256:
                raise AssetPolicyError('Indexed FBX bytes changed before metadata publication')
            previous = self.get(asset_id)
            saved = self.db.execute('SELECT receipt_json FROM animation_fbx_intakes WHERE asset_id=?',
                                    (asset_id,)).fetchone()
            expected = IndexedAnimation(asset_id, expected_entry.sha256, 'fbx', inspected.status,
                inspected.skeleton_fingerprint, inspected.bone_names, inspected.clips,
                inspected.warnings, _policy_rights(expected_entry.policy))
            if saved is not None:
                if saved[0] != encoded or previous != expected:
                    raise AnimationMetadataError('Existing measured FBX identity differs; original clip retained')
                cancel_check()
                return
            if (previous is None or previous.source_format != 'fbx'
                    or previous.status != 'REQUIRES_CONVERSION' or previous.clips):
                raise AnimationMetadataError('FBX measurement requires an indexed source without existing clips')
            self.db.execute('''UPDATE animation_sources SET status=?,fingerprint=?,bone_names_json=?,warnings_json=?
                               WHERE asset_id=?''', (inspected.status, inspected.skeleton_fingerprint,
                json.dumps(inspected.bone_names), json.dumps(inspected.warnings), asset_id))
            self.db.execute('INSERT INTO animation_clips VALUES (?,?,?,?)',
                (asset_id+'#clip-0000', asset_id, 0, json.dumps(inspected.clips[0].to_dict(), allow_nan=False)))
            self.db.execute('INSERT INTO animation_fbx_intakes VALUES (?,?)', (asset_id, encoded))
            cancel_check()

    def get(self, asset_id: str) -> IndexedAnimation | None:
        entry = self.library.get(asset_id)
        if entry is None:
            return None
        row = self.db.execute("""SELECT format,status,fingerprint,bone_names_json,warnings_json
            FROM animation_sources WHERE asset_id=?""", (asset_id,)).fetchone()
        if row is None:
            return None
        clips: list[ClipMetadata] = []
        for (metadata,) in self.db.execute("""SELECT metadata_json FROM animation_clips
            WHERE asset_id=? ORDER BY ordinal""", (asset_id,)):
            data = json.loads(metadata)
            data["animated_bones"] = tuple(data["animated_bones"])
            data["warnings"] = tuple(data["warnings"])
            clips.append(ClipMetadata(**data))
        return IndexedAnimation(entry.asset_id, entry.sha256, row[0], row[1], row[2],
                                tuple(json.loads(row[3])), tuple(clips),
                                tuple(json.loads(row[4])), _policy_rights(entry.policy))

    def list_sources(self) -> tuple[IndexedAnimation, ...]:
        ids = self.db.execute("SELECT asset_id FROM animation_sources ORDER BY asset_id").fetchall()
        return tuple(found for (name,) in ids if (found := self.get(name)) is not None)
