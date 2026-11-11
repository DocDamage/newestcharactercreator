"""Private local asset index with fail-closed license permissions.

Registration is a user-invoked, read-only file hash operation. This module never
copies purchased assets, downloads model weights, or trains on their contents.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from ucc.core.errors import UCCError, ValidationError


class AssetPolicyError(UCCError):
    pass


@dataclass(frozen=True, slots=True)
class LicensePolicy:
    provider: str
    license_name: str
    source_uri: str
    reviewed: bool = False
    no_ai: bool = False
    ue_only: bool = False
    can_use_non_unreal: bool = False
    can_use_unreal: bool = False
    ai_input_allowed: bool = False
    redistribute_source_allowed: bool = False

    def __post_init__(self) -> None:
        for name in ("provider", "license_name", "source_uri"):
            val = getattr(self, name)
            if not isinstance(val, str) or not val.strip() or len(val) > 2048:
                raise ValidationError(f"License field {name} is invalid")
        for name in ("reviewed", "no_ai", "ue_only", "can_use_non_unreal", "can_use_unreal",
                     "ai_input_allowed", "redistribute_source_allowed"):
            if type(getattr(self, name)) is not bool:
                raise ValidationError(f"License flag {name} must be Boolean")

    def allow(self, operation: str, target: str | None = None) -> tuple[bool, str]:
        if operation == "inventory":
            return True, "inventory metadata only"
        if operation not in {"engine_export", "ai_input", "ship_source"}:
            return False, "unknown operation"
        if not self.reviewed:
            return False, "asset-specific license review missing"
        if operation == "engine_export":
            if target not in {"unreal", "unity", "godot"}:
                return False, "unrecognized target engine"
            if target == "unreal" and not self.can_use_unreal:
                return False, "Unreal-use permission not established"
            if target != "unreal" and (self.ue_only or not self.can_use_non_unreal):
                return False, "cross-engine license permission not established"
            return True, "reviewed engine-use permission"
        if operation == "ai_input":
            if self.no_ai or not self.ai_input_allowed:
                return False, "generative AI input permission not established"
            return True, "explicit reviewed AI-input permission"
        if not self.redistribute_source_allowed:
            return False, "source redistribution permission not established"
        return True, "explicit reviewed source redistribution permission"

    def to_dict(self) -> dict[str, Any]:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LicensePolicy":
        if not isinstance(data, dict) or not set(data).issubset(cls.__dataclass_fields__):
            raise ValidationError("Unknown license policy fields")
        return cls(**data)


@dataclass(frozen=True, slots=True)
class AssetEntry:
    asset_id: str
    source_path: str
    sha256: str
    size_bytes: int
    policy: LicensePolicy
    indexed_utc: str


def _sha256(path: Path) -> str:
    dig = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            dig.update(chunk)
    return dig.hexdigest()


class AssetLibrary:
    def __init__(self, db_path: str | Path):
        self.path = Path(db_path).expanduser()
        if self.path.is_symlink():
            raise AssetPolicyError("Catalog path cannot be a symlink")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.execute("PRAGMA journal_mode = WAL")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version > 1:
            self.db.close()
            raise AssetPolicyError("Catalog schema is newer; refusing a destructive downgrade")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS asset_sources (
                asset_id TEXT PRIMARY KEY NOT NULL,
                source_path TEXT NOT NULL,
                content_sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
                license_json TEXT NOT NULL,
                indexed_utc TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_asset_sha ON asset_sources(content_sha256);
            PRAGMA user_version=1;
        """)

    def __enter__(self) -> "AssetLibrary":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.db.close()

    def register(self, asset_id: str, path: Path, policy: LicensePolicy) -> AssetEntry:
        if not isinstance(asset_id, str) or not asset_id.strip() or len(asset_id) > 128:
            raise ValidationError("asset_id invalid")
        source = Path(path).expanduser()
        if source.is_symlink() or not source.is_file():
            raise AssetPolicyError("Only existing regular files can be indexed")
        # File is read only; path is user-provided, never discovered or uploaded here.
        resolved = source.resolve(strict=True)
        if not resolved.is_file():
            raise AssetPolicyError("Asset source inaccessible")
        before = resolved.stat()
        checksum = _sha256(resolved)
        after = resolved.stat()
        if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
            raise AssetPolicyError("Source changed during hashing; retry when file is stable")
        entry = AssetEntry(asset_id=asset_id, source_path=str(resolved),
                           sha256=checksum, size_bytes=after.st_size,
                           policy=policy, indexed_utc=datetime.now(timezone.utc).isoformat())
        previous = self.get(asset_id)
        if previous:
            if previous.sha256 != entry.sha256 or previous.policy != entry.policy:
                raise AssetPolicyError("Asset ID already refers to different content or permissions")
            return previous
        with self.db:
            self.db.execute("INSERT INTO asset_sources VALUES (?,?,?,?,?,?)",
                            (entry.asset_id, entry.source_path, entry.sha256, entry.size_bytes,
                             json.dumps(entry.policy.to_dict(), sort_keys=True), entry.indexed_utc))
        return entry

    def get(self, asset_id: str) -> AssetEntry | None:
        row = self.db.execute("SELECT asset_id,source_path,content_sha256,size_bytes,license_json,indexed_utc "
                              "FROM asset_sources WHERE asset_id=?", (asset_id,)).fetchone()
        if not row:
            return None
        return AssetEntry(asset_id=row[0], source_path=row[1], sha256=row[2],
                          size_bytes=row[3], policy=LicensePolicy.from_dict(json.loads(row[4])),
                          indexed_utc=row[5])

    def list_assets(self) -> tuple[AssetEntry, ...]:
        ids = self.db.execute("SELECT asset_id FROM asset_sources ORDER BY asset_id").fetchall()
        return tuple(self.get(row[0]) for row in ids)

    def require_permission(self, asset_id: str, operation: str, target: str | None = None) -> None:
        entry = self.get(asset_id)
        if entry is None:
            raise AssetPolicyError("Unknown asset: permission denied")
        allowed, reason = entry.policy.allow(operation, target)
        if not allowed:
            raise AssetPolicyError(f"Asset {asset_id} blocked: {reason}")
