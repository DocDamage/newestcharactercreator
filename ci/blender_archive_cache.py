"""Verify the exact public Blender archive cache; no network or Blender execution."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

ARCHIVE_NAME = "blender-5.3.0-linux-x64.tar.xz"
CHECKSUM_NAME = "blender-5.3.0.sha256"
ARCHIVE_SHA256 = "dacb8264197a3f7fda6001285a5a506fc97ee943881261c2c3bd63c882f22e05"
CHECKSUM_SHA256 = "94f6b7fddba74a12b39a18b8f0b5ddb2859a0f5db825001335a9ca6705665f5d"
CACHE_KEY = f"ucc-blender-archive-v1-linux-x64-5.3.0-{ARCHIVE_SHA256}-{CHECKSUM_SHA256}"
MAX_CHECKSUM_BYTES = 64 * 1024
MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024
_MEMBERS = {ARCHIVE_NAME, CHECKSUM_NAME}


def _stamp(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return value.st_dev, value.st_ino, value.st_nlink, value.st_size, value.st_mtime_ns


def _file(path: Path, limit: int, *, retain: bool = False) -> tuple[str, int, bytes]:
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= limit:
        raise ValueError("Cache member must be one bounded, regular, single-link file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    digest = hashlib.sha256()
    content: list[bytes] = []
    count = 0
    with os.fdopen(os.open(path, flags), "rb") as stream:
        if _stamp(os.fstat(stream.fileno())) != _stamp(before):
            raise ValueError("Cache member changed before its guarded read")
        while block := stream.read(min(1024 * 1024, limit + 1 - count)):
            count += len(block)
            if count > limit:
                raise ValueError("Cache member exceeds its bounded read")
            digest.update(block)
            if retain:
                content.append(block)
        if _stamp(os.fstat(stream.fileno())) != _stamp(before):
            raise ValueError("Cache member changed during its guarded read")
    if count != before.st_size or _stamp(path.lstat()) != _stamp(before):
        raise ValueError("Cache member changed after its guarded read")
    return digest.hexdigest(), count, b"".join(content)


def checksum_entry(payload: bytes) -> str:
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_CHECKSUM_BYTES:
        raise ValueError("Official checksum metadata exceeds its bound")
    lines = [line for line in payload.decode("ascii").splitlines() if ARCHIVE_NAME in line]
    match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *]" + re.escape(ARCHIVE_NAME), lines[0]) if len(lines) == 1 else None
    if match is None:
        raise ValueError("Expected one exact Linux archive checksum entry")
    return match.group(1).lower()


def verify_checksum(path: Path, *, _archive_sha: str = ARCHIVE_SHA256,
                    _checksum_sha: str = CHECKSUM_SHA256) -> dict[str, object]:
    """Private keyword overrides exist only for isolated non-shipping unit fixtures."""
    digest, count, payload = _file(path, MAX_CHECKSUM_BYTES, retain=True)
    entry = checksum_entry(payload)
    if digest != _checksum_sha or entry != _archive_sha:
        raise ValueError("Official checksum bytes or Linux entry differ from the reviewed pin")
    return {"checksum_sha256": digest, "checksum_bytes": count, "archive_sha256": entry}


def verify_cache(directory: Path, *, _archive_sha: str = ARCHIVE_SHA256,
                 _checksum_sha: str = CHECKSUM_SHA256) -> dict[str, object]:
    directory = directory.absolute()
    if directory.resolve(strict=True) != directory:
        raise ValueError("Archive cache directory must be canonical")
    for path in (directory, *directory.parents):
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
            raise ValueError("Archive cache directory must not be redirected")
    if not directory.is_dir() or {p.name for p in directory.iterdir()} != _MEMBERS:
        raise ValueError("Archive cache must contain exactly the tar and official checksum")
    receipt = verify_checksum(directory/CHECKSUM_NAME, _archive_sha=_archive_sha,
                              _checksum_sha=_checksum_sha)
    digest, count, _ = _file(directory/ARCHIVE_NAME, MAX_ARCHIVE_BYTES)
    if digest != _archive_sha:
        raise ValueError("Blender archive SHA-256 differs from the reviewed pin")
    return receipt | {"status": "PINNED_PUBLIC_BLENDER_ARCHIVE_BYTES_VERIFIED",
                      "archive_bytes": count, "archive_integrity_verified": True,
                      "blender_executed": False, "domain_suites_verified": False}


def check_restore(cache_hit: str, matched_key: str, *, allow_miss: bool = False) -> None:
    if cache_hit == "true" and matched_key == CACHE_KEY:
        return
    if allow_miss and cache_hit in ("", "false") and matched_key == "":
        return
    raise ValueError("Only the exact reviewed cache key is admitted; consumer misses fail")


def curl_failure_code(status: int) -> int:
    """Only known transport/setup failures permit the reviewed alternate origin.

    Curl 35 denotes a connection handshake error; certificate verification (60),
    local writes (23), content size limits (63), config and unknown codes fail shut.
    """
    if type(status) is not int or not 1 <= status <= 255:
        raise ValueError("Expected an actual nonzero curl exit status")
    transport = {5, 6, 7, 18, 22, 28, 35, 47, 52, 55, 56}
    return 10 if status in transport else 20


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    sub.add_parser("cache-key")
    failure = sub.add_parser("classify-curl")
    failure.add_argument("--exit-code", type=int, required=True)
    checksum = sub.add_parser("checksum")
    checksum.add_argument("--input", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--directory", type=Path, required=True)
    restore = sub.add_parser("check-restore")
    restore.add_argument("--cache-hit", required=True)
    restore.add_argument("--matched-key", required=True)
    restore.add_argument("--allow-miss", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.operation == "classify-curl":
            print(curl_failure_code(args.exit_code))
            return 0
        if args.operation == "cache-key":
            print(f"cache_key={CACHE_KEY}")
            return 0
        if args.operation == "checksum":
            result = verify_checksum(args.input)
        elif args.operation == "verify":
            result = verify_cache(args.directory)
        else:
            check_restore(args.cache_hit, args.matched_key, allow_miss=args.allow_miss)
            result = {"exact_cache_hit": args.cache_hit == "true", "consumer_miss_allowed": args.allow_miss}
    except (OSError, ValueError) as error:
        print(f"BLENDER_ARCHIVE_CACHE_REJECTED: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
