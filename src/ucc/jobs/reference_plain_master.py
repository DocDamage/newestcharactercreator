"""Atomic existing body/face workflows for unprepared source-bound masters."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from threading import Event
from typing import TYPE_CHECKING, Callable

from ucc.animations.project_references import MAX_PROJECT_REFERENCES, build_source_binding
from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.expressions import validate_expression_part_rebind
from ucc.core.hand_parts import ensure_source_intent
from ucc.core.master_versions import stage_unverified_master
from ucc.core.models import CharacterProject
from ucc.core.storage import ProjectStore
from ucc.library.provenance import LicensePolicy
from .animation_reference_storage import check_registered_source
from .catalog_clip import verify_catalog_fbx_clip
from .customized_humanoid import generate_customized_humanoid, apply_saved_customized_body_revision
from .expression_hands import RebuiltExpressionHand, publish_rebuilt_hand
from .expression_storage import check_cancel, install_master_copy
from .face_revision import apply_saved_face_revision, bundled_face_assets
from .hand_library import build_hand_library
from .hand_revision import apply_hand_revision
from .hand_storage import installed_inputs, load_hand_library, load_hand_receipt
from .master_preview import _digest, _master_file
from .neutral_master import inspect_saved_neutral_master
from .project_animation_references import _neutral
from .reference_plain_context import prepare_plain_reference_context
from .reference_plain_intent import inspect_plain_body_intent

if TYPE_CHECKING:
    from .reference_master_revision import ReferencedMasterResult


def revise_plain_reference_master(store: ProjectStore, database_path: Path, *, initial: CharacterProject,
        master_sha: str, metadata_sha: str, unchanged: Callable[[], None], operation: str,
        blender_exe: Path, worker_script: Path, mpfb_data_dir: Path, cancel: Event | None,
        timeout_s: float) -> ReferencedMasterResult:
    """Called after the public coordinator validates operation, timeout and snapshot."""
    from .reference_master_revision import ReferencedMasterResult
    if (initial.family != 'humanoid.v1' or initial.base_provider != 'mpfb'
            or initial.expression is not None or not 0 < len(initial.animations) <= MAX_PROJECT_REFERENCES):
        raise ValidationError('Plain reference editing requires an unprepared MPFB master and source references')
    if operation == 'face_revision' and not initial.facial_parameters:
        raise ValidationError('Save explicit facial intent before a reference-aware face revision')
    runtime = dict(blender_exe=blender_exe, worker_script=worker_script, cancel=cancel, timeout_s=timeout_s)
    common = dict(runtime, mpfb_data_dir=mpfb_data_dir)
    records = {clip: check_registered_source(store, database_path, initial.project_id, clip, cancel)
               for clip in initial.animations}
    _neutral(store, initial, master_sha, metadata_sha, blender_exe, worker_script, cancel, timeout_s)
    for clip, record in records.items():
        source = verify_catalog_fbx_clip(database_path, clip, expected_source_sha256=record['source_sha256'],
            expected_policy=LicensePolicy.from_dict(record['license']), jobs_root=store.root/'.ucc-jobs', **runtime)
        if build_source_binding(initial.project_id, source) != record:
            raise ProjectStorageError('Fresh source differs from the exact project reference binding')
    unchanged()
    context = prepare_plain_reference_context(store, initial, cancel)
    private = context.store

    def expected():
        current = private.load()
        return dict(expected_project_id=current.project_id, expected_revision=current.revision,
                    expected_master_blend=current.master_blend)

    if context.old_hand is not None:
        reset = apply_hand_revision(private, manifest_sha256=context.old_hand.sha256,
                                    selection='neutral', **common, **expected())
        if reset.revision is None or reset.project.parts:
            raise ProjectStorageError('Existing plain hand did not actually reset to its admitted source')
    current = private.load()
    _, base_sha = _master_file(private, current.master_blend)
    desired = replace(current, parameters=initial.parameters, facial_parameters=initial.facial_parameters,
                      height_m=initial.height_m)
    if desired != current:
        private.save(replace(desired, revision=current.revision+1), expected_revision=current.revision,
                     expected_project=current)
    if operation == 'face_revision':
        inspect_plain_body_intent(private, **runtime, **expected())
        edited = apply_saved_face_revision(private, **common, **expected())
    elif operation == 'body_generation':
        args = expected(); args.pop('expected_master_blend')
        edited = generate_customized_humanoid(private, **common, **args)
    else:
        edited = apply_saved_customized_body_revision(private, **common, **expected())
    body_project = private.load(); body_path, body_sha = _master_file(private, body_project.master_blend)
    if edited.revision is None:
        if body_sha != base_sha:
            raise ProjectStorageError('Verified plain face no-op changed its admitted master')
        context.recheck(store, cancel); unchanged()
        for clip, record in records.items():
            if check_registered_source(store, database_path, initial.project_id, clip, cancel) != record:
                raise ProjectStorageError('Reference changed during verified plain face no-op')
        return ReferencedMasterResult(initial, None, operation,
            context.old_hand.sha256 if context.old_hand else None,
            {'source_references_preserved': True, 'verified_noop': True, 'engine_import_verified': False})
    inspect_plain_body_intent(private, **runtime, **expected())
    rebuilt = None
    if context.old_hand is not None:
        built = build_hand_library(private, **common, **expected())
        selected = apply_hand_revision(private, manifest_sha256=built.library.sha256,
                                       selection=context.selection, **common, **expected())
        if selected.revision is None or not selected.project.parts:
            raise ProjectStorageError('Revised plain body did not receive a genuinely rebuilt compatible hand')
        parts = (replace(selected.project.parts[0], part_id=initial.parts[0].part_id),)
        validate_expression_part_rebind(initial.parts, parts)
        scene, sha = _master_file(private, selected.project.master_blend)
        receipt = load_hand_receipt(private, built.library, sha, context.selection, cancel)
        rebuilt = RebuiltExpressionHand(private, built.library, scene, sha, receipt, parts,
            {'rebuilt_library': built.observed, 'selection': selected.observed})
    final = private.load()
    expected_final = replace(initial, animations=(), master_blend=final.master_blend,
        parts=final.parts, revision=final.revision, geometry_state='generated_unverified', rig_profile=None)
    if final != expected_final:
        raise ProjectStorageError('Private plain master edit changed unrelated character intent')
    inspect_saved_neutral_master(private, **runtime, **expected())
    output, output_sha = _master_file(private, final.master_blend)
    private_metadata_sha = _digest(private.file, cancel)
    proposed_parts = rebuilt.parts if rebuilt else final.parts

    def recheck():
        check_cancel(cancel); unchanged(); context.recheck(store, cancel)
        for clip, record in records.items():
            if check_registered_source(store, database_path, initial.project_id, clip, cancel) != record:
                raise ProjectStorageError('Source reference changed during plain body/face editing')
        if (private.load() != final or _digest(private.file, cancel) != private_metadata_sha
                or _master_file(private, final.master_blend) != (output, output_sha)
                or _digest(output, cancel) != output_sha or _digest(body_path, cancel) != body_sha):
            raise ProjectStorageError('Verified plain body/hand output changed before publication')
        if rebuilt:
            library = load_hand_library(private, rebuilt.library.sha256, cancel)
            ensure_source_intent(final, library.manifest['recipe'])
            if load_hand_receipt(private, library, output_sha, context.selection, cancel) != rebuilt.receipt:
                raise ProjectStorageError('Verified rebuilt plain hand receipt changed')
            installed_inputs(mpfb_data_dir, cancel)
        if initial.facial_parameters: bundled_face_assets(mpfb_data_dir, cancel)

    recheck()
    if rebuilt:
        install_master_copy(store, body_path, body_sha, private.root, cancel)
        publish_rebuilt_hand(store, rebuilt, cancel)

    def at_commit():
        recheck()
        if rebuilt:
            candidate = replace(initial, animations=(), master_blend='master/versions/'+output_sha+'.blend',
                                parts=proposed_parts)
            library = load_hand_library(store, rebuilt.library.sha256, cancel)
            ensure_source_intent(candidate, library.manifest['recipe'])
            if load_hand_receipt(store, library, output_sha, context.selection, cancel) != rebuilt.receipt:
                raise ProjectStorageError('Installed rebuilt plain hand receipt changed')

    revision = stage_unverified_master(store, output, authorized_source_root=private.root,
        expected_project=initial, expected_project_id=initial.project_id, expected_revision=initial.revision,
        expected_sha256=output_sha, proposed_parts=proposed_parts, cancel=cancel, before_project_save=at_commit)
    return ReferencedMasterResult(revision.project, revision, operation,
        rebuilt.library.sha256 if rebuilt else None, {'source_references_preserved': True,
        'fresh_source_count': len(records), 'registered_hand_rebuilt': rebuilt is not None,
        'expression_controls_introduced': False, 'original_master_preserved': True,
        'target_animation_verified': False, 'engine_import_verified': False})
