"""Read-only skeleton name compatibility report; NO retargeting, cloud, or downloads."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .candidate_mapping import BoneMappingError, PROFILES, propose_mapping
from .metadata import AnimationMetadataError, inspect_animation_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Explicitly selected BVH/GLB/glTF source")
    parser.add_argument("--target", required=True, type=Path, help="Explicitly selected BVH/GLB/glTF target")
    parser.add_argument("--source-profile", choices=sorted(PROFILES))
    parser.add_argument("--target-profile", choices=sorted(PROFILES))
    args = parser.parse_args(argv)
    try:
        source = inspect_animation_file(args.source)
        target = inspect_animation_file(args.target)
        if not source.bone_names or not target.bone_names:
            raise BoneMappingError("Both files require actual inspected bone names; FBX/uasset conversion is pending")
        report = propose_mapping(source.bone_names, target.bone_names,
                                 source_hint=args.source_profile, target_hint=args.target_profile)
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return 0
    except (AnimationMetadataError, BoneMappingError, OSError, ValueError) as exc:
        print(f"Skeleton mapping inspection blocked: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
