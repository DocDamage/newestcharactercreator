"""Explicit immutable dependencies for a private reference-aware hand edit.

The source project is never cleared or rewritten. Only the private projection
omits external source IDs, after the caller has freshly verified those IDs.
Existing hand and expression admission still runs on every copied dependency.
"""
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event
from uuid import uuid4

from ucc.core.errors import ProjectStorageError
from ucc.core.hand_parts import ensure_source_intent, hand_selection
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from .expression_revisions import read_expression_receipt
from .expression_storage import check_cancel, install_master_copy, safe_directory, _install_bytes
from .expression_verification import registered_expression_source
from .hand_storage import HandLibrary, load_hand_library, load_hand_receipt, publish_asset
from .master_preview import _digest, _master_file


@dataclass(frozen=True, slots=True)
class HandEditScratch:
    store: ProjectStore
    project: CharacterProject
    library: HandLibrary
    dependencies: tuple[tuple[Path, str], ...]

    def recheck(self, original: ProjectStore, cancel: Event | None) -> None:
        for path, expected in self.dependencies:
            check_cancel(cancel)
            relative = path.relative_to(original.root)
            safe_directory(original, *relative.parent.parts)
            if path.is_symlink() or not path.is_file() or _digest(path, cancel) != expected:
                raise ProjectStorageError('Reference-aware hand dependency changed: '+str(relative))


def create_hand_edit_scratch(store: ProjectStore, initial: CharacterProject, identity: str,
                             cancel: Event | None) -> HandEditScratch:
    """Copy only validated current/library/receipt ancestors; never whole trees."""
    projected = replace(initial, animations=(), revision=0)
    library = load_hand_library(store, identity, cancel)
    ensure_source_intent(projected, library.manifest['recipe'])
    current = hand_selection(projected, identity)
    master, master_sha = _master_file(store, initial.master_blend)
    dependencies = {master: master_sha, library.manifest_path: identity,
                    library.source_master: library.manifest['recipe']['bindings']['master_sha256']}
    for variant, path in library.assets.items():
        dependencies[path] = library.manifest['assets'][variant]['sha256']
    if current != 'neutral':
        load_hand_receipt(store, library, master_sha, current, cancel)
        path = safe_directory(store, 'parts', 'revisions')/(master_sha+'.json')
        dependencies[path] = _digest(path, cancel)
    if initial.expression is not None:
        expression, _ = registered_expression_source(store, projected, cancel)
        dependencies.update({expression.manifest_path: expression.sha256,
            expression.original_master: expression.manifest['recipe']['bindings']['master_sha256'],
            expression.prepared_master: expression.manifest['prepared_master_sha256'],
            expression.report_path: expression.manifest['report_sha256']})
        ancestor = library.manifest['recipe']['bindings']['master_sha256'] if current != 'neutral' else master_sha
        seen = set()
        while ancestor != expression.manifest['prepared_master_sha256']:
            # registered_expression_source has already admitted this bounded chain.
            if ancestor in seen or len(seen) >= 1024:
                raise ProjectStorageError('Reference-aware expression ancestry is cyclic or oversized')
            seen.add(ancestor)
            path, sha = _master_file(store, 'master/versions/'+ancestor+'.blend')
            dependencies[path] = sha
            receipt = read_expression_receipt(store, expression, ancestor, cancel)
            receipt_path = safe_directory(store, 'expressions', 'revisions')/(ancestor+'.json')
            dependencies[receipt_path] = _digest(receipt_path, cancel)
            inspection = safe_directory(store, 'expressions', 'inspections')/(receipt['inspection_sha256']+'.json')
            dependencies[inspection] = receipt['inspection_sha256']
            ancestor = receipt['source_master_sha256']
    root = safe_directory(store, '.ucc-jobs', create=True)/('reference-hand-'+str(uuid4()))
    root.mkdir(exist_ok=False)
    scratch = ProjectStore(root)
    result = HandEditScratch(scratch, projected, library, tuple(dependencies.items()))
    result.recheck(store, cancel)
    for source, expected in dependencies.items():
        relative = source.relative_to(store.root)
        if relative.parts[:2] == ('master', 'versions'):
            install_master_copy(scratch, source, expected, source.parent, cancel)
        elif relative.parts[:2] == ('parts', 'objects'):
            publish_asset(scratch, source, expected, source.parent, cancel)
        else:
            # All JSON paths above came from closed, bounded provenance readers.
            if source.stat().st_size > 4*1024*1024:
                raise ProjectStorageError('Reference-aware provenance exceeds its metadata budget')
            with source.open('rb') as stream:
                data = stream.read(4*1024*1024+1)
            if len(data) > 4*1024*1024:
                raise ProjectStorageError('Reference-aware provenance grew while copying')
            _install_bytes(safe_directory(scratch, *relative.parent.parts, create=True),
                           expected, data, cancel, basename=relative.name)
    result = replace(result, project=scratch.save(projected))
    result.recheck(store, cancel)
    return result
