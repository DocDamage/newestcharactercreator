#!/usr/bin/env python3
"""Collect real Stage0_Starter output; never invent a PASS.

Generates P0_SPIKE evidence only when underlying reports and saved .blend exist.
The final gate verifier hashes/rechecks each source artifact.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from verify_gate import safe_evidence_path, sha256_file


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def make_item(ident: str, passes: bool, evidence_root: Path, sources: list[Path], reason: str) -> dict:
    artifacts = []
    for path in sources:
        try:
            rel = path.resolve(strict=True).relative_to(evidence_root.resolve(strict=True))
            if path.is_file() and path.stat().st_size:
                artifacts.append({"path": str(rel).replace('\\', '/'), "sha256": sha256_file(path)})
        except (FileNotFoundError, ValueError, OSError):
            continue
    return {
        "id": ident,
        "status": "pass" if passes and len(artifacts) == len(sources) else "blocked",
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "notes": reason,
        "artifacts": artifacts,
    }


def gather(evidence_root: Path, audit: Path, smoke_dir: Path) -> dict:
    """Expects audit and smoke_dir WITHIN the evidence root (for proof locality)."""
    for p in [audit, smoke_dir / "summary.json"]:
        safe_evidence_path(evidence_root, str(p.resolve().relative_to(evidence_root.resolve())))
    a = load_json(audit)
    summary_path = smoke_dir / "summary.json"
    summary = load_json(summary_path)
    creation = smoke_dir / "mpfb_create_result.json"
    reopen = smoke_dir / "reopen_result.json"
    blend = smoke_dir / "mpfb_created.blend"
    c = load_json(creation) if creation.exists() else {}
    r = load_json(reopen) if reopen.exists() else {}
    audit_ok = bool(a.get("read_only") and a.get("blender", {}).get("found")
                    and a["blender"].get("version_probe", {}).get("exit_code") == 0)
    created = bool(summary.get("create", {}).get("return_code") == 0
                   and c.get("status") == "ok"
                   and isinstance(c.get("new_mesh_vertices"), list)
                   and any(isinstance(n, int) and n > 100 for n in c["new_mesh_vertices"])
                   and blend.is_file() and blend.stat().st_size > 0)
    reloaded = bool(created and summary.get("reopen", {}).get("return_code") == 0
                    and r.get("status") == "ok" and r.get("vertex_count", 0) > 100
                    and summary.get("passed") is True)
    return {
        "schema_version": 1,
        "gate": "P0_SPIKE",
        "tests": [
            make_item("ENV-PROBE", audit_ok, evidence_root, [audit],
                      "Read-only local audit and Blender version probe"),
            make_item("MPFB-CREATE", created, evidence_root,
                      [summary_path, creation, blend], "Real MPFB operator-generated mesh and .blend"),
            make_item("MPFB-REOPEN", reloaded, evidence_root,
                      [summary_path, reopen, blend], "Fresh-process reopen nonzero mesh verification"),
        ],
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--evidence-dir", type=Path, required=True)
    p.add_argument("--audit", type=Path, required=True)
    p.add_argument("--smoke-dir", type=Path, required=True)
    opt = p.parse_args()
    root = opt.evidence_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    try:
        result = gather(root, opt.audit.resolve(), opt.smoke_dir.resolve())
    except (OSError, ValueError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"Could not collect Stage 0 evidence: {type(exc).__name__}: {exc}")
        return 2
    output = root / "P0_SPIKE.evidence.json"
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    for test in result["tests"]:
        print(test["id"], test["status"])
    print("Evidence written:", output)
    return 0 if all(t["status"] == "pass" for t in result["tests"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
