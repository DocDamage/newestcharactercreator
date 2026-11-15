"""Original-only plain reference gate; retain its closed aggregate JSON only."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT)]
from ci.regional_sources import require, digest
from ci.plain_reference_setup import setup
from ci.plain_reference_positive import verify_cases
from ci.plain_reference_guards import PlainGuards
from ci.plain_reference_summary import STATUS, FLAGS, validate_summary


def verify(blender: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    stores, database, common, protected, source_sha = setup(blender, out)
    with closing(sqlite3.connect(database)) as db:
        catalog_rows = tuple(db.iterdump())
    positive = verify_cases(stores, database, common, source_sha)
    guard_root = out/'guards'; guard_root.mkdir(exist_ok=False)
    guards = PlainGuards(out, guard_root, database, common)
    guards.admission(); guards.live(); guards.late()
    require(all(digest(Path(p)) == sha for p, sha in protected.items()),
            'Original masters, source, baselines or installed assets changed')
    with closing(sqlite3.connect(database)) as db:
        require(tuple(db.iterdump()) == catalog_rows, 'Plain creator altered the source catalog')
    summary = {'status': STATUS, **{flag: True for flag in FLAGS},
        'source_frames': 300, 'source_bones': 71, 'setup_source_workers': 6,
        'setup_source_frame_observations': 1800,
        'positive_source_frame_observations': sum(v['inspect_fbx_animation'] for v in positive.values())*300,
        'changed_master_transactions': 6, 'verified_noop_transactions': 2,
        'positive_workers': positive, 'guards': guards.completed,
        'visual_quality_approved': False, 'engine_import_verified': False}
    return validate_summary(summary)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--blender', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.blender, args.outdir)
    (args.outdir/'plain_reference_summary.json').write_text(
        json.dumps(result, indent=2)+'\n', encoding='utf-8', newline='\n')
    print(STATUS, flush=True)
