"""Fresh registered source admission without detaching project references."""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
import re

from ucc.animations.fbx_snapshot import read_snapshot
from ucc.core.body_sprites import BodySpriteRequest, authored_idle_sprite_origin
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.target_action_format import canonical_bytes, checked_sha
from .expression_storage import load_expression_library
from .expression_revisions import admit_expression_source
from .hand_storage import load_hand_library, load_hand_receipt
from .target_action_storage import load_target_action, source_state
from .target_action_context import source_review, protected
from .native_source_authority import bind_native_catalog_source
from .target_action_resources import host_code_snapshot, worker_namespace_snapshot, blender_helper_inventory
from .worker_resources import worker_dependency_files
from .godot_candidate_inputs import identity, read_json
from .master_preview import _digest
from .fbx_intake import inspect_selected_fbx
from .body_sprite_provenance import OriginalMotionProvenance, review_authored_idle_sprite_origin


@dataclass(frozen=True, slots=True)
class AuthoredIdleSpriteProof:
    record_path: Path
    expected_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.record_path, Path):
            raise ValidationError('Choose a local authored idle proof file')
        checked_sha(self.expected_sha256)


@dataclass(frozen=True, slots=True)
class BodySpriteContext:
    loaded: object
    sources: tuple[tuple[str, Path], ...]
    worker_files: tuple[Path, ...]
    executable_sha256: str
    source_policy: object
    guard: Callable[[], None]
    snapshot: Path
    source_admission: dict


def _character_sources(store, project, binding, cancel):
    library = load_expression_library(store, project.expression.library_sha256, cancel)
    sources = {'master': store.root/project.master_blend, 'expression_library': library.manifest_path}
    if project.parts:
        part = project.parts[0]
        match = re.fullmatch(r'ucc-hand-v1-([a-f0-9]{64})-(shorter|longer)', part.part_asset_id)
        if match is None: raise ValidationError('Unsupported registered body-sprite hand')
        hand = load_hand_library(store, match[1], cancel)
        expected = {'project_id': project.project_id, 'body_parameters': dict(project.parameters),
                    'facial_parameters': dict(project.facial_parameters), 'height_m': project.height_m}
        if canonical_bytes(hand.manifest['recipe']['source']) != canonical_bytes(expected):
            raise ProjectConflict('Body-sprite hand no longer matches saved body and face intent')
        load_hand_receipt(store, hand, binding.target.master_sha256, match[2], cancel)
        admit_expression_source(store, library, hand.manifest['recipe']['bindings']['master_sha256'], cancel)
        sources['part:'+part.part_asset_id] = hand.manifest_path
    else:
        admit_expression_source(store, library, binding.target.master_sha256, cancel)
    return sources


def prepare_body_sprite_context(store, request: BodySpriteRequest, database: Path,
                                blender: Path, worker: Path, budget,
                                provenance: OriginalMotionProvenance | AuthoredIdleSpriteProof,
                                *, destination: Path | None = None) -> BodySpriteContext:
    """Admit the selected origin proof and two fresh actual source observations."""
    binding = request.target_binding; target = binding.target; source = binding.source
    initial = store.load(); database = protected(database); blender = protected(blender); worker = protected(worker)
    if canonical_bytes(initial.to_dict()) != request.project_snapshot_json or _digest(store.file, budget.cancel) != target.project_sha256:
        raise ProjectConflict('Body-sprite canonical snapshot or actual saved project bytes changed')
    loaded = load_target_action(store, binding_sha256=binding.sha256, database_path=database,
        expected_project_id=target.project_id, expected_revision=target.revision,
        expected_master_blend=initial.master_blend, expected_project_sha256=target.project_sha256,
        expected_clip_id=source.clip_id, expected_source_binding_sha256=source.source_binding_sha256,
        expected_catalog_record_sha256=source.catalog_record_sha256,
        cancel=budget.cancel, timeout_s=budget.remaining())
    if loaded.binding_sha256 != binding.sha256 or _digest(loaded.binding_path, budget.cancel) != binding.sha256:
        raise ProjectConflict('Loaded body-sprite Action differs from its exact reviewed binding')
    review = source_review(store, database, source.clip_id, target.project_id, target.revision,
                           initial.master_blend, target.project_sha256, budget)
    if review.source != source:
        raise ProjectConflict('Body-sprite current source policy/receipt differs from the target binding')
    idle = None
    if type(provenance) is AuthoredIdleSpriteProof:
        idle = review_authored_idle_sprite_origin(store, proof_file=provenance.record_path,
            binding=binding, database_path=database, current_policy=review.policy,
            expected_proof_sha256=provenance.expected_sha256, cancel=budget.cancel,
            timeout_s=budget.remaining())
        if destination is not None and any(destination.is_relative_to(scope) or scope.is_relative_to(destination)
                                          for scope in idle.protected_output_scopes):
            raise ValidationError('Body-sprite destination must be outside the authored idle proof closure')
        evidence = idle.review_identity
        origin = authored_idle_sprite_origin(binding, proof_sha256=evidence.proof_sha256,
            receipt_sha256=evidence.receipt_sha256, mapping_sha256=evidence.mapping_sha256,
            cache_sha256=evidence.cache_sha256)
    elif type(provenance) is OriginalMotionProvenance:
        origin = provenance.read(request, review.policy, budget)
    else:
        raise ValidationError('Body sprites need a separately pinned original-motion origin review')
    # This preserves source policy independently of the new per-use sprite grants.
    authority = bind_native_catalog_source(database, source.clip_id,
        expected_source_sha256=source.source_sha256, expected_policy=review.policy,
        local_preview_confirmed=True, cancel=budget.cancel, timeout_s=budget.remaining())
    paths = _character_sources(store, initial, binding, budget.cancel)
    paths['motion:'+source.clip_id] = review.source_path
    if {key: _digest(protected(path), budget.cancel) for key, path in paths.items()} != dict(request.source_bindings):
        raise ProjectConflict('Body-sprite per-use source review differs from current immutable inputs')
    workers = tuple(sorted(worker_dependency_files(worker), key=str))
    exe_sha = _digest(blender, budget.cancel)
    if exe_sha != binding.producer.blender_executable_sha256:
        raise ProjectConflict('Select the Blender executable bound to this existing Action')
    protected_paths = {store.file, blender, provenance.record_path, *paths.values(), *workers,
                       *(path for path, _ in loaded.watched_inputs)}
    frozen = {path: (identity(protected(path)), _digest(path, budget.cancel)) for path in protected_paths}
    if frozen[provenance.record_path][1] != provenance.expected_sha256:
        raise ProjectConflict('Original-author record changed before body-sprite admission')
    state = source_state(store, budget); host = host_code_snapshot(budget)
    namespace = worker_namespace_snapshot(worker, budget); helpers = blender_helper_inventory(blender, budget)
    fresh = {}

    def guard():
        budget.check()
        if store.load() != initial or _digest(store.file, budget.cancel) != target.project_sha256:
            raise ProjectConflict('Saved project changed during private body-sprite rendering')
        authority.guard(cancel=budget.cancel, timeout_s=budget.remaining())
        if idle is not None:
            idle.assert_current()
        for path, (stamp, digest) in {**frozen, **fresh}.items():
            if identity(protected(path)) != stamp or _digest(path, budget.cancel) != digest:
                raise ProjectStorageError('Body-sprite source, native proof or runtime changed: '+str(path))
        for path, stamp in loaded.watched_identities:
            current = identity(protected(path))
            if (current[:2] != stamp[:2] if path == database else current != stamp):
                raise ProjectStorageError('Body-sprite original proof ancestry changed')
        if (source_state(store, budget) != state or host_code_snapshot(budget) != host
                or worker_namespace_snapshot(worker, budget) != namespace
                or blender_helper_inventory(blender, budget) != helpers
                or tuple(sorted(worker_dependency_files(worker), key=str)) != workers):
            raise ProjectStorageError('Body-sprite complete provenance or code closure changed')

    records = []; ids = []
    def observe(job, result, folder):
        budget.check(); folder = protected(folder)
        if (folder != store.root/'.ucc-jobs'/job.job_id or job.operation != 'inspect_fbx_animation'
                or result.job_id != job.job_id or result.operation != job.operation or result.status != 'ok'
                or job.options != {'source_sha256': source.source_sha256}):
            raise ValidationError('Body-sprite intake observation lost its actual fresh worker identity')
        if read_json(folder/'request.json', 256*1024) != job.as_dict():
            raise ProjectStorageError('Fresh body-sprite intake request changed')
        report = read_json(folder/'result.json', 4*1024*1024)
        if report != result.as_dict():
            raise ProjectStorageError('Fresh body-sprite intake result changed')
        snapshot = folder/result.details['snapshot']['name']
        for path in (folder/'request.json', folder/'result.json', folder/'source.fbx', snapshot):
            fresh[path] = (identity(protected(path)), _digest(path, budget.cancel))
        ids.append(job.job_id)
        records.append({'request_sha256': fresh[folder/'request.json'][1], 'result_sha256': fresh[folder/'result.json'][1]})

    guard()
    intake = inspect_selected_fbx(review.source_path, blender_exe=blender, worker_script=worker,
        jobs_root=store.root/'.ucc-jobs', permission=review.policy, cancel=budget.cancel,
        timeout_s=budget.remaining(), source_guard=guard, observer=observe)
    if len(ids) != 2 or len(set(ids)) != 2 or intake.get('two_workers_agree') is not True or intake.get('source_bytes_unchanged') is not True:
        raise ValidationError('Body sprites require two distinct fresh source workers')
    snapshot = protected(Path(intake['private_snapshot']))
    data, _ = read_snapshot(snapshot.parent, intake, source.source_sha256, cancel_check=budget.check)
    authority.require_snapshot(data, intake['snapshot']['sha256'])
    retained = loaded.directory/'source_snapshot.json'
    if (intake['snapshot']['sha256'] != source.snapshot_sha256
            or _digest(snapshot, budget.cancel) != source.snapshot_sha256
            or snapshot.read_bytes() != retained.read_bytes()):
        raise ProjectStorageError('Fresh complete FBX trajectory differs from its registered Action snapshot')
    guard()
    admission = {'source_sha256': source.source_sha256, 'snapshot_sha256': source.snapshot_sha256,
                 'worker_job_ids': ids, 'worker_records': records,'original_motion_provenance':origin}
    return BodySpriteContext(loaded, tuple(sorted(paths.items())), workers, exe_sha, review.policy,
                             guard, snapshot, admission)
