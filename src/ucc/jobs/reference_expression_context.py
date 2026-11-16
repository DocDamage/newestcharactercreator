"""Explicit prepared-expression provenance for private reference-aware edits."""
from dataclasses import dataclass, replace
from pathlib import Path
import re
from threading import Event
from uuid import uuid4

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from .expression_revisions import read_expression_receipt, admit_expression_source
from .expression_storage import (ExpressionLibrary, check_cancel, safe_directory,
    install_master_copy, load_expression_library, _install_bytes)
from .expression_verification import registered_expression_source
from .hand_storage import HandLibrary, load_hand_library
from .master_preview import _master_file, _digest
from .reference_edit_scratch import create_hand_edit_scratch


@dataclass(frozen=True, slots=True)
class ReferenceExpressionContext:
    store: ProjectStore
    project: CharacterProject
    expression_library: ExpressionLibrary
    old_hand: HandLibrary | None
    selection: str | None
    dependencies: tuple[tuple[Path, str], ...]

    def recheck(self, original: ProjectStore, cancel: Event | None) -> None:
        for path, sha in self.dependencies:
            check_cancel(cancel)
            relative = path.relative_to(original.root)
            safe_directory(original, *relative.parent.parts)
            if path.is_symlink() or not path.is_file() or _digest(path, cancel) != sha:
                raise ProjectStorageError('Reference-aware expression dependency changed: '+str(relative))


def install_json_copy(destination: Path, source: Path, sha: str, cancel: Event | None) -> None:
    if source.is_symlink() or not source.is_file() or source.stat().st_size > 4*1024*1024:
        raise ProjectStorageError('Reference-aware expression provenance is missing or oversized')
    with source.open('rb') as stream:
        data = stream.read(4*1024*1024+1)
    if len(data) > 4*1024*1024:
        raise ProjectStorageError('Reference-aware expression provenance grew while reading')
    _install_bytes(destination, sha, data, cancel, basename=source.name)


def prepare_reference_expression_context(store: ProjectStore, initial: CharacterProject,
                                          cancel: Event | None) -> ReferenceExpressionContext:
    """Admit old physical provenance before applying newly saved shape intent.

    A selected hand's immutable recipe describes the existing master. Desired
    body/face parameters may already differ; only a private projection uses the
    old recipe to reconstruct that hand. The outer metadata is never reverted.
    """
    if initial.expression is None or initial.master_blend is None:
        raise ValidationError('Reference-aware body/face editing requires prepared expression provenance')
    if initial.parts:
        if len(initial.parts) != 1:
            raise ValidationError('Reference-aware editing supports one registered compatible left hand')
        part = initial.parts[0]
        match = re.fullmatch(r'ucc-hand-v1-([a-f0-9]{64})-(shorter|longer)', part.part_asset_id)
        if match is None or part.slot != 'hand.L' or part.visible is not True or part.status != 'proposed':
            raise ValidationError('Reference-aware editing requires a visible registered compatible hand')
        hand = load_hand_library(store, match[1], cancel)
        source = hand.manifest['recipe']['source']
        old_intent = replace(initial, parameters=tuple(source['body_parameters'].items()),
            facial_parameters=tuple(source['facial_parameters'].items()), height_m=source['height_m'])
        private = create_hand_edit_scratch(store, old_intent, hand.sha256, cancel)
        library, _ = registered_expression_source(store, private.project, cancel)
        jobs = safe_directory(store, '.ucc-jobs')
        compact = jobs/('rx-'+uuid4().hex[:12])
        # Move only this newly created private projection, never originals.
        # Nested existing expression transactions otherwise exceed Blender's
        # Windows path limit. Verify both absolute targets before the move.
        if (private.store.root.parent != jobs or not private.store.root.resolve().is_relative_to(jobs.resolve())
                or compact.parent.resolve() != jobs.resolve() or compact.exists() or compact.is_symlink()):
            raise ProjectStorageError('Private reference scratch move escaped its explicit jobs directory')
        check_cancel(cancel)
        private.store.root.rename(compact)
        scratch = ProjectStore(compact)
        if scratch.load() != private.project:
            raise ProjectStorageError('Compact private projection changed its metadata')
        return ReferenceExpressionContext(scratch, private.project, library, hand,
                                          match[2], private.dependencies)
    projected = replace(initial, animations=(), revision=0)
    library, _ = registered_expression_source(store, projected, cancel)
    current, sha = _master_file(store, initial.master_blend)
    dependencies = {current: sha, library.manifest_path: library.sha256,
        library.original_master: library.manifest['recipe']['bindings']['master_sha256'],
        library.prepared_master: library.manifest['prepared_master_sha256'],
        library.report_path: library.manifest['report_sha256']}
    seen = set()
    while sha != library.manifest['prepared_master_sha256']:
        if sha in seen or len(seen) >= 1024:
            raise ProjectStorageError('Reference-aware expression ancestry is cyclic or oversized')
        seen.add(sha)
        path, _ = _master_file(store, 'master/versions/'+sha+'.blend'); dependencies[path] = sha
        receipt = read_expression_receipt(store, library, sha, cancel)
        path = safe_directory(store, 'expressions', 'revisions')/(sha+'.json')
        dependencies[path] = _digest(path, cancel)
        path = safe_directory(store, 'expressions', 'inspections')/(receipt['inspection_sha256']+'.json')
        dependencies[path] = receipt['inspection_sha256']
        sha = receipt['source_master_sha256']
    # Keep the additional projection short enough for existing nested Blender
    # transactions on Windows; all storage remains inside this project.
    root = safe_directory(store, '.ucc-jobs', create=True)/('rx-'+uuid4().hex[:12])
    root.mkdir(exist_ok=False); scratch = ProjectStore(root)
    context = ReferenceExpressionContext(scratch, projected, library, None, None, tuple(dependencies.items()))
    context.recheck(store, cancel)
    for source, sha in dependencies.items():
        relative = source.relative_to(store.root)
        if relative.parts[:2] == ('master', 'versions'):
            install_master_copy(scratch, source, sha, source.parent, cancel)
        else:
            install_json_copy(safe_directory(scratch, *relative.parent.parts, create=True), source, sha, cancel)
    context = replace(context, project=scratch.save(projected))
    context.recheck(store, cancel)
    return context


def publish_expression_edit(store: ProjectStore, private: ProjectStore, library_sha: str,
        source_sha: str, master_sha: str, operation: str, cancel: Event | None) -> None:
    """Install the one verified expression revision produced by the old API."""
    library = load_expression_library(private, library_sha, cancel)
    master, _ = _master_file(private, 'master/versions/'+master_sha+'.blend')
    install_master_copy(store, master, master_sha, private.root, cancel)
    if master_sha != source_sha:
        receipt = read_expression_receipt(private, library, master_sha, cancel)
        if receipt['source_master_sha256'] != source_sha or receipt['operation'] != operation:
            raise ProjectStorageError('Private expression revision does not extend the admitted source/operation')
        report = safe_directory(private, 'expressions', 'inspections')/(receipt['inspection_sha256']+'.json')
        install_json_copy(safe_directory(store, 'expressions', 'inspections', create=True),
                          report, receipt['inspection_sha256'], cancel)
        path = safe_directory(private, 'expressions', 'revisions')/(master_sha+'.json')
        install_json_copy(safe_directory(store, 'expressions', 'revisions', create=True), path, _digest(path, cancel), cancel)
    installed = load_expression_library(store, library_sha, cancel)
    admit_expression_source(store, installed, master_sha, cancel)
