#!/usr/bin/env python3
"""Conservative policy precheck, not a legal interpretation or DRM decision."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED = {"asset_id", "provider", "source_uri", "license_name", "license_reviewed",
            "no_ai_training", "ue_only", "can_redistribute_source",
            "can_use_in_non_unreal", "ai_training_permission"}


def validate_record(item: dict, operation: str, target: str | None) -> list[str]:
    errors: list[str] = []
    missing = REQUIRED - item.keys()
    if missing:
        return ["missing required fields: " + ", ".join(sorted(missing))]
    for key in ("license_reviewed", "no_ai_training", "ue_only", "can_redistribute_source",
                "can_use_in_non_unreal", "ai_training_permission"):
        if not isinstance(item.get(key), bool):
            errors.append(key + " must be boolean")
    for key in ("asset_id", "provider", "source_uri", "license_name"):
        if not isinstance(item.get(key), str) or not item[key].strip():
            errors.append(key + " must be a nonempty string")
    if operation == "private_inventory":
        return errors
    if not item["license_reviewed"] or not item["license_name"]:
        errors.append("license review incomplete")
    if operation == "engine_export":
        if target not in {"godot", "unreal", "unity"}:
            errors.append("target engine missing")
        if target != "unreal" and (item["ue_only"] or not item["can_use_in_non_unreal"]):
            errors.append("cross-engine use not approved")
    elif operation == "ship_creator":
        if not item["can_redistribute_source"]:
            errors.append("standalone source redistribution not approved")
    elif operation == "ai_input":
        if item["no_ai_training"] or not item["ai_training_permission"]:
            errors.append("generative AI input use not approved")
    else:
        errors.append("unknown operation")
    return errors


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--operation", required=True,
                   choices=["private_inventory", "engine_export", "ship_creator", "ai_input"])
    p.add_argument("--target", choices=["godot", "unreal", "unity"])
    opt = p.parse_args(argv)
    try:
        m = json.loads(opt.manifest.read_text(encoding="utf-8"))
        assets = m["assets"]
        if m.get("schema_version") != 1 or not isinstance(assets, list):
            raise ValueError("schema_version=1 and assets array required")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Invalid manifest: {exc}")
        return 2
    if opt.operation != "private_inventory" and not assets:
        print("FAIL: no assets to evaluate; cannot approve empty release/export")
        return 1
    issue_count = 0
    seen = set()
    for idx, item in enumerate(assets):
        if not isinstance(item, dict):
            print(f"FAIL asset[{idx}]: not a record")
            issue_count += 1
            continue
        ident = item.get("asset_id", f"#{idx}")
        if ident in seen:
            print(f"FAIL {ident}: duplicate asset ID")
            issue_count += 1
        seen.add(ident)
        issues = validate_record(item, opt.operation, opt.target)
        for issue in issues:
            print(f"FAIL {ident}: {issue}")
        issue_count += len(issues)
    if issue_count:
        print(f"POLICY BLOCKED: {issue_count} issue(s)")
        return 1
    print(f"POLICY PRECHECK PASS: {len(assets)} asset record(s); manual license verification still required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
