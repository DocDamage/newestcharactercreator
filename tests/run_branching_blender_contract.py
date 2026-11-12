"""Opt-in real Blender test on a NON-SHIPPING synthetic weighted fixture.

No MPFB installation, downloads or user assets. Does not prove real character
quality. Output must be a new directory; all generated assets remain private.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "ci")]

from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.jobs.bvh_clip_diagnostic import check_selected_bvh
from ucc.jobs.runner import WorkerFailure
from ucc.library.provenance import LicensePolicy
from verify_branching_review import verify_branching


def run(blender: Path, output: Path) -> dict:
    if output.exists() or output.is_symlink():
        raise ValueError("Output must be a new private directory")
    subprocess.run([str(blender), "--background", "--factory-startup", "--disable-autoexec",
                    "--python-exit-code", "13", "--python",
                    str(ROOT / "tests/fixtures/blender_branching_contract.py"), "--",
                    "--output", str(output)], check=True, timeout=180)
    store = ProjectStore(output / "synthetic-project")
    digest = sha256((output / "synthetic.blend").read_bytes()).hexdigest()
    relative = f"master/versions/{digest}.blend"
    master = store.root / relative
    master.parent.mkdir(parents=True)
    shutil.copy2(output / "synthetic.blend", master)
    project = store.save(replace(CharacterProject.new("SYNTHETIC CONTRACT ONLY"),
                                 master_blend=relative, geometry_state="generated_unverified"))
    policy = LicensePolicy("UCC original synthetic test fixture", "CC0",
                           "ci-original://synthetic-contract", reviewed=True,
                           local_preview_allowed=True, no_ai=True)
    report = verify_branching(store, blender, master, project, policy, output)
    pairs = json.loads((output / "original-branching-contract.json").read_text(encoding="utf-8"))
    source = output / "original-branching-contract.bvh"
    source_bytes, metadata_bytes, master_bytes = source.read_bytes(), (
        store.root / "project.ucc.json").read_bytes(), master.read_bytes()
    # Genuine subprocess rejection, not a mocked result or weakened assertion.
    bad = [dict(p) for p in pairs]
    bad[4]["target"], bad[6]["target"] = bad[6]["target"], bad[4]["target"]
    try:
        check_selected_bvh(
            store, blender_exe=blender, worker_script=ROOT / "blender_bridge/entrypoint.py",
            source_bvh=source, permission=policy, expected_project_id=project.project_id,
            expected_revision=project.revision, expected_master_blend=relative,
            multi_axis_profile="Y_UP_TO_Z_UP", calibrate_rest_axes=True,
            reviewed_mapping=bad, timeout_s=180)
    except WorkerFailure as error:
        if "parents differ" not in str(error):
            raise
    else:
        raise AssertionError("Crossed target hierarchy was accepted by genuine Blender")
    if (source.read_bytes() != source_bytes or master.read_bytes() != master_bytes or
            (store.root / "project.ucc.json").read_bytes() != metadata_bytes):
        raise AssertionError("Negative-path worker modified original files")
    report.update(provenance="SYNTHETIC_NOT_MPFB_NOT_FAB", crossed_hierarchy_rejected=True,
                  negative_path_original_bytes_unchanged=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blender", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.blender.resolve(strict=True), args.output.resolve())
    (args.output / "synthetic-contract-summary.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
