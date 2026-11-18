"""Read-only current idle sources and runtime guards; never loads a motion."""
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Callable

from ucc.core.authored_idle import AuthoredIdleInspectionRequest, saved_authoring_sources
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.target_action_format import canonical_bytes, document_sha256
from .expression_storage import load_expression_library, safe_directory
from .expression_revisions import admit_expression_source
from .hand_storage import load_hand_library, load_hand_receipt
from .master_preview import _master_file, _digest
from .godot_candidate_inputs import identity
from .target_action_context import operation_budget, protected
from .target_action_storage import source_state, ancestry
from .target_action_resources import host_code_snapshot, worker_namespace_snapshot, blender_helper_inventory
from .worker_resources import worker_dependency_files
from .authored_idle_policy import IdleSourcePolicyRecord, admit_policies
from .authored_idle_io import private_sha


@dataclass(frozen=True, slots=True)
class IdleAuthoringSource:
    asset_id: str
    sha256: str
    provenance_sha256: str


@dataclass(frozen=True, slots=True)
class IdleAuthoringContext:
    master: Path
    sources: tuple[IdleAuthoringSource, ...]
    policy_documents: tuple[dict, ...]
    project_file_sha256: str
    executable_sha256: str
    worker_files: tuple[Path, ...]
    guard: Callable[[], None]


def _registered_character_sources(store, project, cancel):
    """Admit actual master/expression/hand receipts, without any clip reader."""
    source = dict(saved_authoring_sources(project))
    master_sha = source['master_and_derived_rig']
    paths = {'master_and_derived_rig': _master_file(store, project.master_blend)[0]}
    library = None
    if project.expression is not None:
        library = load_expression_library(store, project.expression.library_sha256, cancel)
        paths['expression_library'] = library.manifest_path
    if project.parts:
        part = project.parts[0]
        match = re.fullmatch(r'ucc-hand-v1-([a-f0-9]{64})-(shorter|longer)', part.part_asset_id)
        if match is None:
            raise ValidationError('Idle authoring requires the exact supported registered hand')
        hand = load_hand_library(store, match[1], cancel)
        expected = {'project_id': project.project_id, 'body_parameters': dict(project.parameters),
                    'facial_parameters': dict(project.facial_parameters), 'height_m': project.height_m}
        if canonical_bytes(hand.manifest['recipe']['source']) != canonical_bytes(expected):
            raise ProjectConflict('Registered idle hand differs from saved body/face intent')
        load_hand_receipt(store, hand, master_sha, match[2], cancel)
        if library is not None:
            admit_expression_source(store, library, hand.manifest['recipe']['bindings']['master_sha256'], cancel)
        paths['part:'+part.part_asset_id] = hand.manifest_path
    elif library is not None:
        admit_expression_source(store, library, master_sha, cancel)
    if {name: _digest(protected(path), cancel) for name, path in paths.items()} != source:
        raise ProjectConflict('Idle source files differ from the complete saved intent')
    return paths


def _review(store, project, budget):
    paths = _registered_character_sources(store, project, budget.cancel)
    # Opaque preservation hashes of registered immutable character provenance.
    # Existing animation namespaces are never a source of these measurements.
    state = source_state(store, budget)
    proofs = {name: row[1] for name, row in state.items()
              if isinstance(row, tuple) and len(row) == 2
              and name.split('/')[0] in {'master', 'expressions', 'parts'}}
    sources = tuple(IdleAuthoringSource(name, digest, private_sha({
        'asset_id': name, 'source_sha256': digest, 'registered_character_files': proofs}))
        for name, digest in saved_authoring_sources(project))
    return paths, sources, state


def inspect_idle_authoring_sources(store, *, cancel=None, timeout_s=60) -> tuple[IdleAuthoringSource, ...]:
    """Return identities for caller review; never manufacture a consent record."""
    with operation_budget(cancel, timeout_s) as budget:
        project = store.load(); snapshot = _digest(store.file, budget.cancel)
        _, sources, state = _review(store, project, budget)
        if store.load() != project or _digest(store.file, budget.cancel) != snapshot or source_state(store, budget) != state:
            raise ProjectConflict('Saved sources changed during idle authoring review')
        return sources


def prepare_idle_context(store, request, records, database, blender, worker, destination, budget, *,
                         create_jobs=True, capture_authority=None):
    if type(request) is not AuthoredIdleInspectionRequest:
        raise ValidationError('Original idle starts with its typed pre-measurement inspection request')
    if type(records) is not tuple or any(type(row) is not IdleSourcePolicyRecord for row in records):
        raise ValidationError('Select explicit typed idle source-policy records')
    initial = store.load()
    if canonical_bytes(initial.to_dict()) != request.project_snapshot_json:
        raise ProjectConflict('Idle inspection differs from the complete current saved character')
    database, blender, worker = map(protected, (database, blender, worker))
    for path in (database, blender, worker):
        if not path.is_file() or path.stat().st_nlink != 1:
            raise ValidationError('Select canonical single-link catalog, Blender and worker files')
    if destination is not None and destination.path.is_relative_to(store.root):
        raise ValidationError('Choose a new private idle destination outside the saved project')
    for record in records:
        if record.path.is_relative_to(store.root):
            raise ValidationError('Idle review records must be external to immutable character provenance')
    jobs = safe_directory(store, '.ucc-jobs', create=create_jobs)
    if not jobs.is_dir():
        raise ProjectStorageError('Retained idle worker records are missing')
    paths, sources, state = _review(store, initial, budget)
    documents = admit_policies(request, sources, records, budget)
    workers = tuple(sorted(worker_dependency_files(worker)|{worker}, key=str))
    inputs = {store.file, blender, *paths.values(), *workers, *(record.path for record in records)}
    if destination is not None and any(path.is_relative_to(destination.path.parent) for path in (*inputs, database)):
        raise ValidationError('Idle output parent must be separate from guarded input namespaces')
    snapshots = {path: (identity(protected(path)), _digest(path, budget.cancel)) for path in inputs}
    if (any(snapshots[row.path][1] != row.sha256 for row in records)
            or any(snapshots[path][1] != dict(saved_authoring_sources(initial))[name] for name, path in paths.items())):
        raise ProjectConflict('Idle selected source or policy changed during admission')
    catalog = {}
    for suffix in ('', '-wal', '-shm', '-journal'):
        path = protected(Path(str(database)+suffix))
        if path.exists():
            if not path.is_file() or path.stat().st_nlink != 1:
                raise ValidationError('Idle catalog coordination file is redirected or shared')
            catalog[path] = (identity(path), _digest(path, budget.cancel))
        else:
            catalog[path] = None
    parents = ancestry(inputs|{database, jobs})
    host = host_code_snapshot(budget); namespace = worker_namespace_snapshot(worker, budget)
    helpers = blender_helper_inventory(blender, budget)
    if capture_authority is not None:
        # Transfer the stamps that the authored-source guard already checks.
        # Taking a new baseline at the end would admit post-verification replacements.
        capture_authority(parents)
        capture_authority({path: row[0] for path, row in snapshots.items()})
        capture_authority({path: None if row is None else row[0] for path, row in catalog.items()})
        capture_authority({store.root/name: row[0] if len(row) == 2 else row
                           for name, row in state.items() if row is not None})
        capture_authority({store.root/name: None for name, row in state.items() if row is None})
        capture_authority({Path(name): row[0] if len(row) == 2 else row
                           for name, row in helpers.items() if row is not None})
        capture_authority({Path(name): None for name, row in helpers.items() if row is None})
    if _review(store, initial, budget) != (paths, sources, state):
        raise ProjectConflict('Idle registered provenance changed during admission')
    def guard():
        budget.check()
        if store.load() != initial or _digest(store.file, budget.cancel) != snapshots[store.file][1]:
            raise ProjectConflict('Saved character changed during original idle authoring')
        for path, expected in {**snapshots, **catalog}.items():
            if expected is None:
                if path.exists() or path.is_symlink():
                    raise ProjectStorageError('Idle catalog coordination namespace changed')
            elif (path.stat().st_nlink != 1 or (identity(protected(path)), _digest(path, budget.cancel)) != expected):
                raise ProjectStorageError('Idle source, review, catalog or runtime bytes changed')
        if any(identity(protected(path)) != stamp for path, stamp in parents.items()):
            raise ProjectStorageError('Idle guarded input ancestry changed')
        if (source_state(store, budget) != state or host_code_snapshot(budget) != host
                or worker_namespace_snapshot(worker, budget) != namespace
                or blender_helper_inventory(blender, budget) != helpers
                or tuple(sorted(worker_dependency_files(worker)|{worker}, key=str)) != workers):
            raise ProjectStorageError('Idle immutable provenance or execution closure changed')
    guard()
    return IdleAuthoringContext(paths['master_and_derived_rig'], sources, documents,
        snapshots[store.file][1], snapshots[blender][1], workers, guard)
