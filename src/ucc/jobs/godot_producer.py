"""Saved-master production bridge to a private, independently verified candidate.

The selected scene supplies its compatible rig Action only. No registered
source-only motion, default engine permission or public readiness is inferred.
"""
import math
from pathlib import Path
import struct
from threading import Event
import time
from uuid import uuid4

from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.expression_clip import build_expression_clip
from ucc.core.expressions import TARGETS
from ucc.core.storage import ProjectStore
from ucc.export.godot_blender_recipe import build_recipe, OUTPUTS, POLICY
from ucc.export.godot_candidate_contract import EngineInputPermission, GodotCandidateRequest, FILES, canonical_bytes
from ucc.export.godot_skin_plan import build_skin_plan
from .expression_keys import installed_expression_inputs
from .expression_storage import safe_directory
from .godot_candidate import PrivateGodotCandidate, verify_staged_godot_candidate
from .godot_candidate_inputs import project_sources, regular_file, identity, check_cancel
from .master_preview import _digest
from .protocol import JobRequest
from .runner import BlenderJobRunner, WorkerFailure


def produce_private_godot_candidate(store: ProjectStore, runner: BlenderJobRunner, *,
        motion_source: Path, authorized_motion_root: Path, motion_asset_id: str,
        permissions: tuple[EngineInputPermission, ...], mpfb_data_dir: Path,
        godot_exe: Path, adapter_directory: Path, cancel: Event | None = None,
        timeout_s: float = 600) -> PrivateGodotCandidate:
    """Stage, reopen, import and verify without altering saved character state."""
    if type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not .05 <= timeout_s <= 3600:
        raise ValidationError('Producer needs a bounded total timeout')
    start = time.monotonic()
    check_cancel(cancel); store._check_safety()
    project = store.load(); project_sha = _digest(store.file, cancel)
    sources = project_sources(store, project, cancel)
    motion = regular_file(Path(motion_source), Path(authorized_motion_root), 512*1024*1024)
    if type(motion_asset_id) is not str or not motion_asset_id.startswith('motion:') or motion_asset_id in sources:
        raise ValidationError('Producer requires an explicit selected target Action identity')
    sources[motion_asset_id] = motion
    bindings = {name: _digest(path, cancel) for name, path in sources.items()}
    clip = build_expression_clip(project, bindings['master'])
    recipe = build_recipe(project, project_sha, bindings['master'], motion_asset_id, bindings, permissions, clip)
    installed = installed_expression_inputs(mpfb_data_dir, cancel)
    watched = {store.file, store.root, Path(authorized_motion_root), *sources.values(), *installed.values()}
    for path in tuple(watched):
        root = next((root for root in (store.root, Path(authorized_motion_root), Path(mpfb_data_dir))
                     if path.is_relative_to(root)), None)
        if root is None:
            raise ProjectStorageError('Producer input escaped its explicitly selected source directory')
        for parent in path.parents:
            if not parent.is_relative_to(root): break
            watched.add(parent)
            if parent == root: break
    identities = {path: identity(path) for path in watched}
    hashes = {path: _digest(path, cancel) for path in watched if path.is_file()}
    worker = Path(runner.worker_script)
    regular_file(worker, worker.parent, 256*1024)
    worker_sha = _digest(worker, cancel)
    blender = Path(runner.blender_exe)
    regular_file(blender, blender.parent, 512*1024*1024)
    blender_sha = _digest(blender, cancel)

    def remaining() -> float:
        check_cancel(cancel)
        value = timeout_s-(time.monotonic()-start)
        if value < .05:
            raise WorkerFailure('Blender/Godot candidate exceeded its total time limit')
        return value

    def unchanged() -> None:
        remaining()
        current = store.load()
        if (current.project_id != project.project_id or current.revision != project.revision
                or _digest(store.file, cancel) != project_sha):
            raise ProjectConflict('Saved character changed during Blender/Godot production')
        for path, before in identities.items():
            if path.is_symlink() or not path.exists() or identity(path) != before:
                raise ProjectStorageError('Producer source or parent directory identity changed')
        for path, expected in hashes.items():
            if _digest(path, cancel) != expected:
                raise ProjectStorageError('Producer original input content changed')
        if _digest(worker, cancel) != worker_sha or _digest(blender, cancel) != blender_sha:
            raise ProjectStorageError('Blender worker or executable changed during production')
        build_recipe(current, project_sha, bindings['master'], motion_asset_id, bindings, permissions, clip)

    jobs = safe_directory(store, '.ucc-jobs', create=True)
    if Path(runner.jobs_root) != jobs:
        raise ValidationError('Producer Blender runner must use this project private jobs directory')
    prepared = jobs/('godot-producer-'+str(uuid4())); prepared.mkdir(exist_ok=False)
    def write(path: Path, data: bytes) -> None:
        with path.open('xb') as stream: stream.write(data)
    write(prepared/'expression_clip.json', canonical_bytes(clip).rstrip(b'\n'))
    write(prepared/'export_recipe.json', canonical_bytes(recipe))
    staged = {target.staged_name: installed[target.staged_name] for target in TARGETS}
    staged.update({'candidate.blend':sources['master'], 'target_motion.blend':motion,
        'expression_clip.json':prepared/'expression_clip.json', 'export_recipe.json':prepared/'export_recipe.json'})
    options = {'master_sha256':bindings['master'], 'target_motion_sha256':bindings[motion_asset_id],
        'export_recipe_sha256':_digest(prepared/'export_recipe.json', cancel),
        'clip_sha256':_digest(prepared/'expression_clip.json', cancel),
        **{target.role+'_'+target.family+'_sha256':target.sha256 for target in TARGETS}}
    unchanged()
    stage_job = JobRequest.new('stage_mpfb_godot_candidate', input_project='candidate.blend', options=options)
    stage, folder = runner.run(stage_job, staged_inputs=staged, timeout_s=remaining(), cancel=cancel)
    unchanged()
    if (stage.details.get('policy') != POLICY or stage.details.get('engine_import_verified') is not False
            or any(stage.details.get(field) != _digest(folder/name, cancel) for name,field in OUTPUTS.items())):
        raise ValidationError('Blender producer did not bind every real staged output')
    verify_options = {**options, **{field:_digest(folder/name, cancel) for name,field in OUTPUTS.items()}}
    verification_inputs = {name:folder/name for name in set(staged)|set(OUTPUTS)}
    verify_job = JobRequest.new('verify_mpfb_godot_candidate', input_project='candidate.blend', options=verify_options)
    verified, reopened = runner.run(verify_job, staged_inputs=verification_inputs, timeout_s=remaining(), cancel=cancel)
    unchanged()
    if (verified.details.get('status') != 'FRESH_SAVED_COMBINED_ACTION_AND_FULL_SURFACE_VERIFIED'
            or verified.details.get('verification_sha256') != _digest(reopened/'blender_verification.json', cancel)):
        raise ValidationError('Fresh Blender process did not independently bind its saved candidate verification')
    write(reopened/'skin_plan.json', canonical_bytes(build_skin_plan(reopened/'character.glb').to_dict()))
    bind = (reopened/'bind_positions.bin').read_bytes()
    if len(bind) != 13380*12:
        raise ValidationError('Producer bind reference is incomplete')
    indices = {}
    for index in range(13380):
        point = struct.unpack_from('<3f', bind, index*12)
        if not all(math.isfinite(value) for value in point):
            raise ValidationError('Producer bind positions are nonfinite')
        key = struct.pack('<3f', *(0. if value == 0 else value for value in point)).hex()
        if key in indices:
            raise ValidationError('Producer bind correspondence is ambiguous')
        indices[key] = index
    write(reopened/'bind_source_indices.json', canonical_bytes(indices))
    request = GodotCandidateRequest(str(uuid4()), project.project_id, project.revision, project_sha,
        bindings['master'], tuple((name,_digest(reopened/name, cancel)) for name in sorted(FILES)),
        permissions, tuple(bindings.items()))
    write(prepared/'candidate_request.json', canonical_bytes(request.to_dict()))
    unchanged()
    return verify_staged_godot_candidate(store, request, candidate_folder=reopened,
        motion_sources={motion_asset_id:reopened/'target_motion.blend'}, godot_exe=godot_exe,
        adapter_directory=adapter_directory, cancel=cancel, timeout_s=remaining(), source_guard=unchanged)
