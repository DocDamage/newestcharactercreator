"""Bounded public checksum metadata receipt; never downloads or runs Blender."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

MAX_CHECKSUM_BYTES = 64 * 1024
CHECKSUM_URL = "https://download.blender.org/release/Blender5.3/blender-5.3.0.sha256"
ARCHIVE_NAME = "blender-5.3.0-linux-x64.tar.xz"
_ENTRY = re.compile(r"([0-9a-fA-F]{64}) [ *]" + re.escape(ARCHIVE_NAME))


def _official_url(value: str) -> None:
    if type(value) is not str or len(value) > 1024 or any(char.isspace() for char in value):
        raise ValueError("Checksum URL must be bounded HTTPS metadata text")
    parts = urlsplit(value)
    expected = urlsplit(CHECKSUM_URL)
    if (parts.scheme != expected.scheme or parts.netloc != expected.netloc
            or parts.path != expected.path or parts.fragment
            or (parts.query and not re.fullmatch(r"ucc_ci=[0-9]+-[0-9]+-checksum-receipt", parts.query))):
        raise ValueError("Checksum URL must identify the exact official HTTPS metadata file")


def make_receipt(payload: bytes, *, source_url: str, effective_url: str,
                 head_sha: str, run_id: int, run_attempt: int) -> dict[str, object]:
    """Capture the exact public bytes without adopting an executable archive pin."""
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_CHECKSUM_BYTES:
        raise ValueError("Official checksum metadata must contain 1 to 65536 bytes")
    _official_url(source_url)
    _official_url(effective_url)
    if type(head_sha) is not str or re.fullmatch(r"[0-9a-f]{40}", head_sha) is None:
        raise ValueError("Receipt requires the exact workflow head SHA")
    if any(type(value) is not int or value < 1 for value in (run_id, run_attempt)):
        raise ValueError("Receipt requires positive workflow run and attempt identities")
    text = payload.decode("ascii")
    candidates = [line for line in text.splitlines() if ARCHIVE_NAME in line]
    if len(candidates) != 1 or (match := _ENTRY.fullmatch(candidates[0])) is None:
        raise ValueError("Expected exactly one complete official Linux archive checksum entry")
    return {
        "status": "OFFICIAL_BLENDER_CHECKSUM_METADATA_RECEIPT_ONLY_V1",
        "metadata_only": True,
        "workflow_event": "workflow_dispatch",
        "checksum_receipt_only_input": True,
        "head_sha": head_sha,
        "run_id": run_id,
        "run_attempt": run_attempt,
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "source_url": source_url,
        "effective_url": effective_url,
        "checksum_bytes": len(payload),
        "checksum_sha256": hashlib.sha256(payload).hexdigest(),
        "public_checksum_text": text,
        "archive_name": ARCHIVE_NAME,
        "archive_sha256": match.group(1).lower(),
        "archive_downloaded": False,
        "archive_integrity_verified": False,
        "blender_installed_or_executed": False,
        "domain_suites_executed": False,
        "cache_pin_adopted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--effective-url", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        if args.input.is_symlink() or not args.input.is_file():
            raise ValueError("Checksum input must be a regular metadata file")
        with args.input.open("rb") as stream:
            payload = stream.read(MAX_CHECKSUM_BYTES + 1)
        receipt = make_receipt(payload, source_url=args.source_url,
                               effective_url=args.effective_url, head_sha=args.head_sha,
                               run_id=args.run_id, run_attempt=args.run_attempt)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        if args.out.parent.is_symlink():
            raise ValueError("Receipt destination must not be redirected")
        with args.out.open("x", encoding="utf-8") as stream:
            json.dump(receipt, stream, indent=2, allow_nan=False)
            stream.write("\n")
    except (OSError, ValueError) as error:
        print(f"CHECKSUM_RECEIPT_REJECTED: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"metadata_only": True, "checksum_sha256": receipt["checksum_sha256"],
                      "archive_sha256": receipt["archive_sha256"],
                      "blender_installed_or_executed": False, "cache_pin_adopted": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
