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
from ucc.core.master_versions import stage_unverified_master
from ucc.core.anatomy import slot_catalog
from ucc.jobs.protocol import JobRequest
from ucc.jobs.runner import BlenderJobRunner
from ucc.sprites.plan import CameraProfile, build_plan
from ucc.sprites.atlas import pack_frames
from ucc.ai.probe import probe_comfyui, probe_webui
from ucc.export.inspect_glb import inspect_glb
from ucc.animations.metadata import inspect_animation_file
from ucc.animations.catalog import AnimationCatalog
from ucc.library.provenance import LicensePolicy


def _prepare_godot_animation(args: argparse.Namespace) -> dict:
    from ucc.core.errors import ValidationError
    from ucc.jobs.godot_first_party_animation import prepare_first_party_godot_animation
    from ucc.jobs.godot_first_party_authorization import load_first_party_godot_authorization
    from ucc.jobs.export_destination import plan_destination
    from ucc.jobs.target_action_context import operation_budget, protected

    authorization = load_first_party_godot_authorization(args.authorization)
    worker = Path(__file__).resolve().parents[2]/'blender_bridge/entrypoint.py'
    store = ProjectStore(args.project)
    destination = None
    if args.command == 'export-godot-animation':
        destination = plan_destination(args.destination, store.root)
        if (destination.path.is_relative_to(store.root)
                or destination.path.is_relative_to(protected(args.database).parent)):
            raise ValidationError('Choose an export folder outside the project and catalog')
    def authorization_guard() -> None:
        if load_first_party_godot_authorization(args.authorization) != authorization:
            raise ValidationError('The selected local Godot authorization changed')

    def progress(phase: str) -> None:
        authorization_guard()
        print(phase, file=sys.stderr, flush=True)

    shared = dict(selection=authorization.selection, database_path=args.database, permissions=authorization.permissions,
                  godot_exe=args.godot, godot_main_exe=args.godot_main, progress=progress)
    with operation_budget(None, args.timeout) as budget:
        result = prepare_first_party_godot_animation(store, **shared, blender_exe=args.blender,
            worker_script=worker, purpose=authorization.purpose, private_local_execution_confirmed=True,
            cancel=budget.cancel, timeout_s=budget.remaining())
        authorization_guard()
        if destination is not None:
            from ucc.jobs.godot_first_party_playback import publish_first_party_godot_playback
            published = publish_first_party_godot_playback(store, **shared, result=result,
                destination=destination, cancel=budget.cancel, timeout_s=budget.remaining(),
                authorization_guard=authorization_guard)
            return {'status': 'PRIVATE_GODOT_ANIMATION_EXPORTED_AND_REOPENED',
                    'directory': str(published.directory), 'receipt_sha256': published.receipt_sha256,
                    'engine_project_exported': True, 'distribution_review_complete': False}
    return {
        'status': 'PRIVATE_GODOT_ANIMATION_GEOMETRY_VERIFIED',
        'retained_inputs': str(result.retained.directory),
        'retention_manifest_sha256': result.retained.manifest_sha256,
        'diagnostic': str(result.diagnostic.directory),
        'diagnostic_receipt_sha256': result.diagnostic.receipt_sha256,
        'engine_project_exported': False,
    }


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
    staged = sp.add_parser("stage-blend", help="Preserve worker-produced .blend as an UNVERIFIED immutable revision")
    staged.add_argument("project", type=Path)
    staged.add_argument("blend", type=Path)
    staged.add_argument("--worker-output-root", type=Path, required=True)
    glb = sp.add_parser("inspect-glb", help="Offline GLB structure inspection (not engine validation)")
    glb.add_argument("path", type=Path)
    anim = sp.add_parser("inspect-animation", help="Read BVH/glTF metadata without retargeting or moving files")
    anim.add_argument("file", type=Path)
    fbx = sp.add_parser("inspect-fbx", help="Private two-worker native FBX full-frame/rest inspection; no retargeting")
    fbx.add_argument("file", type=Path)
    fbx.add_argument("--blender", type=Path, required=True)
    fbx.add_argument("--jobs", type=Path, required=True)
    fbx.add_argument("--policy-file", type=Path, required=True, help="Reviewed local-preview LicensePolicy JSON")
    native=sp.add_parser("preview-fbx",help="Experimental complete native FBX motion on a private saved-character copy")
    native.add_argument("file",type=Path)
    native.add_argument("--project",type=Path,required=True)
    native.add_argument("--blender",type=Path,required=True)
    native.add_argument("--mapping",type=Path,help="Optional explicit reviewed body map; otherwise only the measured humanoid family is supported")
    native.add_argument("--include-hands",action="store_true",help="Include measured hand/finger chains in automatic mapping; incompatible with --mapping")
    native.add_argument("--policy-file",type=Path,required=True)
    prepare_godot = sp.add_parser("prepare-godot-animation",
        help="Prepare one saved animation and verify private Godot body deformation")
    export_godot = sp.add_parser("export-godot-animation",
        help="Verify and export one saved animation to a new private Godot project")
    for parser in (prepare_godot, export_godot):
        parser.add_argument("project", type=Path)
        parser.add_argument("--authorization", required=True, type=Path)
        parser.add_argument("--database", required=True, type=Path)
        parser.add_argument("--blender", required=True, type=Path)
        parser.add_argument("--godot", required=True, type=Path, help="Installed Godot 4.7.1 console executable")
        parser.add_argument("--godot-main", required=True, type=Path, help="Matching installed main executable")
        parser.add_argument("--timeout", default=1800., type=float, help="Total local deadline in seconds")
    export_godot.add_argument("--destination", required=True, type=Path)
    index_anim = sp.add_parser("index-animation", help="Index one explicitly chosen animation with fail-closed provenance")
    index_anim.add_argument("file", type=Path)
    index_anim.add_argument("--database", type=Path, required=True, help="Private local SQLite catalog")
    index_anim.add_argument("--asset-id", required=True)
    index_anim.add_argument("--provider", required=True, help="Exact source provider, e.g. Fab")
    index_anim.add_argument("--license-name", required=True, help="Actual license name or 'unreviewed'")
    index_anim.add_argument("--source-uri", required=True, help="Original listing/source URI")
    index_anim.add_argument("--policy-file", type=Path, help="Optional user-reviewed JSON LicensePolicy flags")
    list_anim = sp.add_parser("list-animations", help="Read local catalog only; no scanning or network access")
    list_anim.add_argument("--database", type=Path, required=True)
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
        elif args.command == "stage-blend":
            result = stage_unverified_master(ProjectStore(args.project), args.blend,
                                             authorized_source_root=args.worker_output_root)
            data = {"revision": result.project.revision, "geometry_state": result.status,
                    "sha256": result.sha256, "bytes": result.bytes_copied,
                    "master": str(result.master_path), "reused": result.reused,
                    "note": "UNVERIFIED: Blender must reopen/inspect before engine export"}
        elif args.command == "inspect-glb":
            data = inspect_glb(args.path).to_dict()
        elif args.command == "inspect-animation":
            data = inspect_animation_file(args.file).to_dict()
        elif args.command == "inspect-fbx":
            from ucc.jobs.fbx_intake import inspect_selected_fbx
            policy = LicensePolicy.from_dict(json.loads(args.policy_file.read_text(encoding="utf-8")))
            data = inspect_selected_fbx(args.file, blender_exe=args.blender, jobs_root=args.jobs,
                worker_script=Path(__file__).resolve().parents[3]/"blender_bridge/entrypoint.py", permission=policy)
        elif args.command == "preview-fbx":
            from ucc.jobs.native_body import preview_native_body
            store=ProjectStore(args.project);project=store.load()
            policy=LicensePolicy.from_dict(json.loads(args.policy_file.read_text(encoding="utf-8")))
            result=preview_native_body(store,source_fbx=args.file,mapping_profile=args.mapping,include_hands=args.include_hands,blender_exe=args.blender,
                worker_script=Path(__file__).resolve().parents[3]/"blender_bridge/entrypoint.py",permission=policy,
                expected_project_id=project.project_id,expected_revision=project.revision,expected_master_blend=project.master_blend)
            data={"status":"EXPERIMENTAL_NATIVE_BODY_PREVIEW","frames":result.evidence["source_frame_count"],
                  "mapped_bones":len(result.evidence["mapped_pairs"]),"private_animation":result.private_visual_review_blend,
                  "private_rendered_review":result.private_render_review,"private_timeline":result.private_timeline,
                  "mapping_profile":result.mapping_profile_used,"retargeting_verified":False,"animation_visual_quality_verified":False}
        elif args.command in {"prepare-godot-animation", "export-godot-animation"}:
            data = _prepare_godot_animation(args)
        elif args.command == "index-animation":
            if args.policy_file is not None:
                policy_data = json.loads(args.policy_file.read_text(encoding="utf-8"))
                policy = LicensePolicy.from_dict(policy_data)
                if (policy.provider != args.provider or policy.license_name != args.license_name
                        or policy.source_uri != args.source_uri):
                    raise ValueError("Policy JSON source fields must match explicit CLI source arguments")
            else:
                policy = LicensePolicy(args.provider, args.license_name, args.source_uri)
            with AnimationCatalog(args.database) as catalog:
                data = catalog.index_file(args.asset_id, args.file, policy).to_dict()
        elif args.command == "list-animations":
            with AnimationCatalog(args.database) as catalog:
                data = [entry.to_dict() for entry in catalog.list_sources()]
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
