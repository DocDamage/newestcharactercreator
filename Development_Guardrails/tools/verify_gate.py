#!/usr/bin/env python3
"""Fail-closed structural acceptance gate; standard library only.

Evidence file paths are relative to --evidence-dir. A passed test must have real
nonempty files with matching SHA-256; this proves artifact integrity, NOT semantic
correctness. Manual review entries also require reviewer and review_note.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_evidence_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise ValueError("empty evidence path")
    path_input = Path(relative)
    if path_input.is_absolute() or ".." in path_input.parts:
        raise ValueError("absolute or parent-traversing evidence path")
    canonical_root = root.resolve(strict=True)
    candidate = (canonical_root / path_input).resolve(strict=True)
    if not candidate.is_relative_to(canonical_root):
        raise ValueError("evidence path escapes evidence directory")
    if not candidate.is_file() or candidate.stat().st_size == 0:
        raise ValueError("evidence is not a nonempty file")
    return candidate


def read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def validate_gate(gates: dict[str, Any], evidence: dict[str, Any], root: Path, gate: str) -> list[str]:
    errors: list[str] = []
    spec = gates.get("gates", {}).get(gate)
    if not spec:
        return [f"unknown gate: {gate}"]
    if evidence.get("schema_version") != 1 or evidence.get("gate") != gate:
        errors.append("wrong evidence schema version or gate name")
    observed_tests: dict[str, Any] = {}
    for item in evidence.get("tests", []):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            errors.append("malformed test entry")
            continue
        ident = item["id"]
        if ident in observed_tests:
            errors.append(f"duplicate test: {ident}")
        observed_tests[ident] = item
    expected = {r["id"] for r in spec["required"]}
    unexpected = observed_tests.keys() - expected
    if unexpected:
        errors.append("unexpected tests: " + ", ".join(sorted(unexpected)))
    for needed in spec["required"]:
        ident = needed["id"]
        item = observed_tests.get(ident)
        if not item:
            errors.append(f"{ident}: MISSING")
            continue
        if item.get("status") != "pass":
            errors.append(f"{ident}: {item.get('status', 'no status')}, not pass")
            continue
        if not isinstance(item.get("observed_at_utc"), str) or not item["observed_at_utc"]:
            errors.append(f"{ident}: missing observed_at_utc")
        if needed.get("manual_review"):
            if not (isinstance(item.get("reviewed_by"), str) and item["reviewed_by"].strip()):
                errors.append(f"{ident}: missing human reviewer")
            if not (isinstance(item.get("review_note"), str) and item["review_note"].strip()):
                errors.append(f"{ident}: missing review note")
        artifacts = item.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            errors.append(f"{ident}: no evidence artifacts")
            continue
        for i, artifact in enumerate(artifacts):
            if not isinstance(artifact, dict) or not isinstance(artifact.get("path"), str):
                errors.append(f"{ident}: invalid artifact {i}")
                continue
            recorded = artifact.get("sha256", "")
            if not isinstance(recorded, str) or len(recorded) != 64:
                errors.append(f"{ident}: missing valid SHA-256 for {artifact['path']}")
                continue
            try:
                path = safe_evidence_path(root, artifact["path"])
                actual = sha256_file(path)
                if recorded.lower() != actual:
                    errors.append(f"{ident}: checksum mismatch: {artifact['path']}")
            except (ValueError, FileNotFoundError, OSError) as exc:
                errors.append(f"{ident}: bad evidence path: {artifact['path']} ({exc})")
    if gate == "P0_SPIKE":
        errors.extend(validate_p0_semantics(root))
    return errors



def validate_p0_semantics(root: Path) -> list[str]:
    """Stage 0 has enough structured evidence to validate more than file hashes.

    This does not prove correct visual shape or future skeleton/animation support.
    """
    failures: list[str] = []
    paths = {
        "audit": "preflight.json",
        "summary": "mpfb_smoke/summary.json",
        "created": "mpfb_smoke/mpfb_create_result.json",
        "reopen": "mpfb_smoke/reopen_result.json",
        "blend": "mpfb_smoke/mpfb_created.blend",
    }
    content: dict[str, Any] = {}
    for name, relative in paths.items():
        try:
            target = safe_evidence_path(root, relative)
            if name != "blend":
                content[name] = read_json(target)
        except (ValueError, FileNotFoundError, OSError, json.JSONDecodeError) as exc:
            failures.append(f"P0 missing/invalid {relative}: {exc}")
    if failures:
        return failures
    a = content["audit"]
    s = content["summary"]
    c = content["created"]
    r = content["reopen"]
    if a.get("read_only") is not True or not a.get("blender", {}).get("found"):
        failures.append("P0 audit not read-only or Blender missing")
    if a.get("blender", {}).get("version_probe", {}).get("exit_code") != 0:
        failures.append("P0 Blender version probe did not succeed")
    if s.get("create", {}).get("return_code") != 0 or s.get("reopen", {}).get("return_code") != 0 or s.get("passed") is not True:
        failures.append("P0 Blender creation/reopen subprocess did not succeed")
    verts = c.get("new_mesh_vertices")
    if c.get("status") != "ok" or not isinstance(verts, list) or not any(type(v) is int and v > 100 for v in verts):
        failures.append("P0 MPFB did not report a substantial created mesh")
    if r.get("status") != "ok" or type(r.get("vertex_count")) is not int or r["vertex_count"] <= 100:
        failures.append("P0 freshly reopened .blend has insufficient geometry")
    # A Blender .blend binary begins with this 7-byte signature.
    with safe_evidence_path(root, paths["blend"]).open("rb") as f:
        if f.read(7) != b"BLENDER":
            failures.append("P0 master file lacks Blender file signature")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", choices=list(read_json(ROOT / "config" / "gates.json")["gates"]))
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--evidence", type=Path, help="defaults to evidence-dir/GATE.evidence.json")
    parser.add_argument("--list", action="store_true", help="list all required test IDs")
    opt = parser.parse_args(argv)
    gates = read_json(ROOT / "config" / "gates.json")
    if opt.list:
        for name, spec in gates["gates"].items():
            print(f"{name}: {', '.join(t['id'] for t in spec['required'])}")
        return 0
    if not opt.gate or not opt.evidence_dir:
        parser.error("--gate and --evidence-dir required unless --list")
    path = opt.evidence or opt.evidence_dir / f"{opt.gate}.evidence.json"
    try:
        issues = validate_gate(gates, read_json(path), opt.evidence_dir, opt.gate)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"FAIL {opt.gate}: cannot load evidence: {exc}", file=sys.stderr)
        return 2
    if issues:
        print(f"FAIL {opt.gate} ({len(issues)} issue(s))")
        for issue in issues:
            print(" - " + issue)
        return 1
    print(f"STRUCTURAL PASS {opt.gate}: required proof files and review fields present")
    print("NOTE: this does not establish that the engine or animation actually works.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
