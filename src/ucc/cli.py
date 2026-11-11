"""Minimal working developer CLI for project metadata and Blender diagnostics."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

from ucc.core.commands import CharacterSession
from ucc.core.errors import UCCError
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.core.anatomy import slot_catalog
from ucc.jobs.protocol import JobRequest
from ucc.jobs.runner import BlenderJobRunner
from ucc.sprites.plan import CameraProfile, build_plan
from ucc.sprites.atlas import pack_frames
from ucc.ai.probe import probe_comfyui, probe_webui
from ucc.export.inspect_glb import inspect_glb


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="UCC metadata/diagnostics CLI (not a graphical character creator)")
    sp = p.add_subparsers(dest="command", required=True)
    new = sp.add_parser("new", help="Create an empty character metadata project")
    new.add_argument("directory", type=Path)
    new.add_argument("--name", required=True)
    info = sp.add_parser("info", help="Display saved character project metadata")
    info.add_argument("directory", type=Path)
    morph = sp.add_parser("morph", help="Change an MPFB-independent normalized draft morph value")
    morph.add_argument("directory", type=Path)
    morph.add_argument("name", choices=["height", "muscle", "weight"])
    morph.add_argument("value", type=float)
    sp.add_parser("slots", help="List known humanoid attachment slots")
    validate = sp.add_parser("validate", help="Read and validate a project without modifying it")
    validate.add_argument("project_json", type=Path)
    glb = sp.add_parser("inspect-glb", help="Offline GLB structure inspection (not engine validation)")
    glb.add_argument("path", type=Path)
    api = sp.add_parser("probe-ai", help="Read-only probes of existing loopback AI APIs")
    api.add_argument("--comfyui", default="http://127.0.0.1:8188")
    api.add_argument("--webui", default="http://127.0.0.1:7860")
    probe = sp.add_parser("probe-blender", help="Run Blender inspect_environment via real subprocess")
    probe.add_argument("--blender", type=Path, required=True)
    probe.add_argument("--jobs", type=Path, required=True)
    render = sp.add_parser("plan-sprites", help="Output metadata only; no images are rendered")
    pack = sp.add_parser("pack-sprites", help="Pack existing PNG frames into actual atlases")
    for parser in (render, pack):
        parser.add_argument("--directions", type=int, default=8)
        parser.add_argument("--width", type=int, default=128)
        parser.add_argument("--height", type=int, default=128)
        parser.add_argument("--fps", type=int, default=12)
        parser.add_argument("--clip", action="append", required=True, help="ID:frame_count")
    pack.add_argument("--frames-dir", type=Path, required=True)
    pack.add_argument("--output-dir", type=Path, required=True)
    pack.add_argument("--max-sheet-side", type=int, default=2048)
    args = p.parse_args(argv)
    try:
        if args.command == "new":
            saved = ProjectStore(args.directory).save(CharacterProject.new(args.name))
            data = saved.to_dict()
        elif args.command == "info":
            proj = ProjectStore(args.directory).load()
            data = proj.to_dict() | {"export_readiness_blockers": list(proj.export_readiness())}
        elif args.command == "morph":
            store = ProjectStore(args.directory)
            original = store.load()
            session = CharacterSession(original)
            changed = session.set_morph(args.name, args.value)
            data = store.save(changed, expected_revision=original.revision).to_dict()
        elif args.command == "slots":
            data = [{"slot": s.name, "socket": s.socket, "allowed_kinds": sorted(s.allowed_kinds)}
                    for s in slot_catalog()]
        elif args.command == "validate":
            data = CharacterProject.from_dict(json.loads(args.project_json.read_text(encoding="utf-8"))).to_dict()
        elif args.command == "inspect-glb":
            data = inspect_glb(args.path).to_dict()
        elif args.command == "probe-ai":
            data = [probe_comfyui(args.comfyui).to_dict(), probe_webui(args.webui).to_dict()]
        elif args.command == "probe-blender":
            root = Path(__file__).resolve().parents[2]
            runner = BlenderJobRunner(args.blender, args.jobs, root / "blender_bridge" / "entrypoint.py")
            result, folder = runner.run(JobRequest.new("inspect_environment"))
            data = result.as_dict() | {"staged_job_dir": str(folder),
                                        "note": "Probe only: does not verify MPFB can create a human"}
        else:
            clips = {}
            for arg in args.clip:
                name, sep, frames = arg.partition(":")
                if not sep:
                    raise ValueError("clip must have ID:frame_count format")
                clips[name] = int(frames)
            render_plan = build_plan(clips, CameraProfile(directions=args.directions),
                                     width=args.width, height=args.height, fps=args.fps)
            if args.command == "pack-sprites":
                artifact = pack_frames(render_plan, args.frames_dir, args.output_dir,
                                       max_sheet_side=args.max_sheet_side)
                data = {"sheets": list(artifact.sheet_files), "manifest": artifact.manifest,
                        "frame_count": artifact.frame_count, "output_dir": str(args.output_dir),
                        "note": "PNG atlas generated; engine import and source geometry remain unverified"}
            else:
                data = render_plan.to_dict()
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return 0
    except (UCCError, ValueError, OSError, KeyError, TypeError) as exc:
        print(f"UCC ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
