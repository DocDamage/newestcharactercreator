"""Private admission of an unprepared master before reference-aware edits."""
from dataclasses import dataclass, replace
from pathlib import Path
import re
from threading import Event
from uuid import uuid4

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from .expression_storage import check_cancel, install_master_copy, safe_directory
from .hand_storage import HandLibrary, load_hand_library
from .master_preview import _digest, _master_file
from .reference_edit_scratch import create_hand_edit_scratch


@dataclass(frozen=True, slots=True)
class PlainReferenceContext:
    store: ProjectStore
    project: CharacterProject
    old_hand: HandLibrary | None
    selection: str | None
    dependencies: tuple[tuple[Path, str], ...]

    def recheck(self, original: ProjectStore, cancel: Event | None) -> None:
        for path, sha in self.dependencies:
            check_cancel(cancel)
            relative = path.relative_to(original.root)
            safe_directory(original, *relative.parent.parts)
            if path.is_symlink() or not path.is_file() or _digest(path, cancel) != sha:
                raise ProjectStorageError('Reference-aware plain dependency changed: '+str(relative))


def prepare_plain_reference_context(store: ProjectStore, initial: CharacterProject,
                                    cancel: Event | None) -> PlainReferenceContext:
    if initial.expression is not None or initial.master_blend is None:
        raise ValidationError('Plain reference editing requires an unprepared saved master')
    jobs = safe_directory(store, '.ucc-jobs', create=True)
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
        compact = jobs/('rp-'+uuid4().hex[:12])
        if (private.store.root.parent != jobs or not private.store.root.resolve().is_relative_to(jobs.resolve())
                or compact.parent.resolve() != jobs.resolve() or compact.exists() or compact.is_symlink()):
            raise ProjectStorageError('Plain reference scratch move escaped its explicit jobs directory')
        check_cancel(cancel)
        private.store.root.rename(compact)
        scratch = ProjectStore(compact)
        if scratch.load() != private.project:
            raise ProjectStorageError('Compact plain projection changed its metadata')
        return PlainReferenceContext(scratch, private.project, hand, match[2], private.dependencies)
    source, sha = _master_file(store, initial.master_blend)
    root = jobs/('rp-'+uuid4().hex[:12]); root.mkdir(exist_ok=False)
    scratch = ProjectStore(root)
    projected = replace(initial, animations=(), revision=0)
    context = PlainReferenceContext(scratch, projected, None, None, ((source, sha),))
    context.recheck(store, cancel)
    install_master_copy(scratch, source, sha, source.parent, cancel)
    context = replace(context, project=scratch.save(projected))
    context.recheck(store, cancel)
    return context
