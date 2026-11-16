"""Freshly source-bound hand edits retaining external animation references.

This authorizes one reconstructed hand transaction, never source motion,
general master adoption, target quality or engine export.
"""
from dataclasses import replace
from pathlib import Path
from threading import Event

from ucc.animations.project_references import MAX_PROJECT_REFERENCES, build_source_binding
from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.hand_parts import hand_selection
from ucc.core.master_versions import stage_unverified_master
from ucc.library.provenance import LicensePolicy
from .animation_reference_storage import check_registered_source
from .catalog_clip import verify_catalog_fbx_clip
from .expression_storage import check_cancel
from .expression_verification import verify_saved_expression_master
from .hand_revision import HandRevisionResult, apply_hand_revision
from .hand_storage import load_hand_receipt, publish_hand_receipt
from .master_preview import _digest, _master_file
from .neutral_master import inspect_saved_neutral_master
from .project_animation_references import _context, _neutral
from .reference_edit_scratch import create_hand_edit_scratch


def apply_referenced_hand_revision(store, database_path: Path, *, manifest_sha256: str,
        selection: str, blender_exe: Path, worker_script: Path, mpfb_data_dir: Path,
        expected_project_id: str, expected_revision: int, expected_master_blend: str,
        cancel: Event | None = None, timeout_s: float = 300) -> HandRevisionResult:
    if type(selection) is not str or selection not in {'neutral', 'shorter', 'longer'}:
        raise ValidationError('Select neutral, shorter or longer from the registered hand library')
    initial, master_sha, metadata_sha, unchanged = _context(store, expected_project_id,
        expected_revision, expected_master_blend, cancel)
    if not 0 < len(initial.animations) <= MAX_PROJECT_REFERENCES:
        raise ValidationError('Reference-aware hand editing requires registered source references')
    common = dict(blender_exe=blender_exe, worker_script=worker_script, cancel=cancel, timeout_s=timeout_s)
    records = {clip: check_registered_source(store, database_path, initial.project_id, clip, cancel)
               for clip in initial.animations}
    _neutral(store, initial, master_sha, metadata_sha, blender_exe, worker_script, cancel, timeout_s)
    for clip, record in records.items():
        source = verify_catalog_fbx_clip(database_path, clip, expected_source_sha256=record['source_sha256'],
            expected_policy=LicensePolicy.from_dict(record['license']), jobs_root=store.root/'.ucc-jobs', **common)
        if build_source_binding(initial.project_id, source) != record:
            raise ProjectStorageError('Fresh animation source differs from its immutable project binding')
    unchanged()
    private = create_hand_edit_scratch(store, initial, manifest_sha256, cancel)
    expected = dict(expected_project_id=private.project.project_id,
                    expected_revision=private.project.revision,
                    expected_master_blend=private.project.master_blend)
    if initial.expression is not None:
        verify_saved_expression_master(private.store, mpfb_data_dir=mpfb_data_dir, **expected, **common)
    edited = apply_hand_revision(private.store, manifest_sha256=manifest_sha256, selection=selection,
        mpfb_data_dir=mpfb_data_dir, **expected, **common)
    final = private.store.load()
    expected_final = private.project if edited.revision is None else replace(private.project,
        revision=private.project.revision+1, master_blend=final.master_blend, parts=final.parts,
        rig_profile=None, geometry_state='generated_unverified')
    if final != expected_final or edited.project != final or hand_selection(final, manifest_sha256) != selection:
        raise ProjectStorageError('Private hand transaction changed unrelated character intent or selection')
    # Existing reconstruction validates current original/assets/receipt; canonical
    # expression inspection additionally proves preserved prepared keys/neutrality.
    if initial.expression is not None and edited.revision is not None:
        verify_saved_expression_master(private.store, mpfb_data_dir=mpfb_data_dir,
            expected_project_id=final.project_id, expected_revision=final.revision,
            expected_master_blend=final.master_blend, **common)
    inspect_saved_neutral_master(private.store, expected_project_id=final.project_id,
        expected_revision=final.revision, expected_master_blend=final.master_blend, **common)
    output, output_sha = _master_file(private.store, final.master_blend)
    private_metadata_sha = _digest(private.store.file, cancel)

    def recheck():
        check_cancel(cancel); unchanged(); private.recheck(store, cancel)
        for clip, record in records.items():
            if check_registered_source(store, database_path, initial.project_id, clip, cancel) != record:
                raise ProjectStorageError('Registered source changed during hand editing')
        current_output, current_sha = _master_file(private.store, final.master_blend)
        if (current_output != output or current_sha != output_sha or _digest(output, cancel) != output_sha
                or private.store.load() != final or _digest(private.store.file, cancel) != private_metadata_sha):
            raise ProjectStorageError('Verified reference-aware hand output changed before publication')

    recheck()
    observed = {**edited.observed, 'external_source_references_preserved': True,
        'freshly_verified_source_count': len(records), 'target_animation_verified': False,
        'engine_import_verified': False}
    if edited.revision is None:
        if output_sha != master_sha or final != private.project:
            raise ProjectStorageError('Reference-aware hand no-op changed its private master or intent')
        return HandRevisionResult(initial, None, manifest_sha256, observed,
                                  edited.stage_job_id, edited.reopen_job_id)
    receipt = None
    if selection != 'neutral':
        receipt = load_hand_receipt(private.store, private.library, output_sha, selection, cancel)
        publish_hand_receipt(store, receipt, cancel)

    def at_commit():
        recheck()
        if receipt is not None and load_hand_receipt(store, private.library, output_sha, selection, cancel) != receipt:
            raise ProjectStorageError('Reference-aware hand receipt changed before atomic commit')

    revision = stage_unverified_master(store, output, authorized_source_root=private.store.root,
        expected_project_id=initial.project_id, expected_revision=initial.revision,
        expected_project=initial, expected_sha256=output_sha, proposed_parts=final.parts,
        cancel=cancel, before_project_save=at_commit)
    return HandRevisionResult(revision.project, revision, manifest_sha256, observed,
                              edited.stage_job_id, edited.reopen_job_id)
