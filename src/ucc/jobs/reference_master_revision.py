"""Atomic prepared-body/face edits retaining references and a rebuilt hand."""
from dataclasses import dataclass, replace
import math
from pathlib import Path
from threading import Event

from ucc.animations.project_references import MAX_PROJECT_REFERENCES, build_source_binding
from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.expressions import validate_expression_part_rebind
from ucc.core.master_versions import MasterRevision, stage_unverified_master
from ucc.core.models import CharacterProject
from ucc.library.provenance import LicensePolicy
from .animation_reference_storage import check_registered_source
from .catalog_clip import verify_catalog_fbx_clip
from .expression_hands import RebuiltExpressionHand, publish_rebuilt_hand
from .expression_keys import installed_expression_inputs
from .expression_mutation import preserve_expressions
from .expression_storage import check_cancel
from .expression_verification import registered_expression_source, verify_saved_expression_master
from .face_revision import bundled_face_assets
from .hand_library import build_hand_library
from .hand_revision import apply_hand_revision
from .hand_storage import load_hand_library, load_hand_receipt, installed_inputs
from .master_preview import _master_file, _digest
from .neutral_master import inspect_saved_neutral_master
from .project_animation_references import _context, _neutral
from .reference_expression_context import prepare_reference_expression_context, publish_expression_edit


@dataclass(frozen=True, slots=True)
class ReferencedMasterResult:
    project: CharacterProject
    revision: MasterRevision | None
    operation: str
    hand_manifest_sha256: str | None
    observed: dict


def revise_referenced_master(store, database_path: Path, *, operation: str,
        blender_exe: Path, worker_script: Path, mpfb_data_dir: Path,
        expected_project_id: str, expected_revision: int, expected_master_blend: str,
        cancel: Event | None = None, timeout_s: float = 300) -> ReferencedMasterResult:
    if type(operation) is not str or operation not in {'body_generation', 'body_refit', 'face_revision'}:
        raise ValidationError('Select body generation, body refit or face revision')
    if type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not .05 <= timeout_s <= 3600:
        raise ValidationError('Reference-aware master timeout_s is outside the supported range')
    initial, master_sha, metadata_sha, unchanged = _context(store, expected_project_id,
        expected_revision, expected_master_blend, cancel)
    if (initial.family != 'humanoid.v1' or initial.base_provider != 'mpfb' or initial.expression is None
            or not 0 < len(initial.animations) <= MAX_PROJECT_REFERENCES):
        raise ValidationError('Reference-aware editing requires a prepared MPFB expression master and source references')
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
    context = prepare_reference_expression_context(store, initial, cancel)
    private = context.store
    def expected():
        current = private.load()
        return dict(expected_project_id=current.project_id, expected_revision=current.revision,
                    expected_master_blend=current.master_blend)
    if context.old_hand is not None:
        # Replay the immutable old recipe, not the newly requested dimensions.
        verify_saved_expression_master(private, **common, **expected())
        reset = apply_hand_revision(private, manifest_sha256=context.old_hand.sha256,
                                    selection='neutral', **common, **expected())
        if reset.revision is None or reset.project.parts:
            raise ProjectStorageError('Existing hand did not actually reset to its admitted source')
    current = private.load()
    _, base_sha = _master_file(private, current.master_blend)
    desired = replace(current, parameters=initial.parameters, facial_parameters=initial.facial_parameters,
                      height_m=initial.height_m)
    if desired != current:
        private.save(replace(desired, revision=current.revision+1), expected_revision=current.revision,
                     expected_project=current)
    edited = preserve_expressions(private, operation=operation, **common, **expected())
    body_project = private.load(); body_path, body_sha = _master_file(private, body_project.master_blend)
    if edited.revision is None:
        if body_sha != base_sha:
            raise ProjectStorageError('Verified face no-op unexpectedly changed its admitted master')
        context.recheck(store, cancel); unchanged()
        for clip, record in records.items():
            if check_registered_source(store, database_path, initial.project_id, clip, cancel) != record:
                raise ProjectStorageError('Reference changed during verified face no-op')
        return ReferencedMasterResult(initial, None, operation,
            context.old_hand.sha256 if context.old_hand else None,
            {'source_references_preserved': True, 'verified_noop': True, 'engine_import_verified': False})
    rebuilt = None
    if context.old_hand is not None:
        built = build_hand_library(private, **common, **expected())
        selected = apply_hand_revision(private, manifest_sha256=built.library.sha256,
                                       selection=context.selection, **common, **expected())
        if selected.revision is None or not selected.project.parts:
            raise ProjectStorageError('Revised body did not receive a genuinely rebuilt compatible hand')
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
        raise ProjectStorageError('Private reference-aware master edit changed unrelated character intent')
    verify_saved_expression_master(private, **common, **expected())
    inspect_saved_neutral_master(private, **runtime, **expected())
    output, output_sha = _master_file(private, final.master_blend)
    private_metadata_sha = _digest(private.file, cancel)
    proposed_parts = rebuilt.parts if rebuilt else final.parts

    def recheck():
        check_cancel(cancel); unchanged(); context.recheck(store, cancel)
        for clip, record in records.items():
            if check_registered_source(store, database_path, initial.project_id, clip, cancel) != record:
                raise ProjectStorageError('Source reference changed during body/face editing')
        if (private.load() != final or _digest(private.file, cancel) != private_metadata_sha
                or _master_file(private, final.master_blend) != (output, output_sha)
                or _digest(output, cancel) != output_sha or _digest(body_path, cancel) != body_sha):
            raise ProjectStorageError('Verified body/hand/expression output changed before publication')
        registered_expression_source(private, final, cancel)
        if rebuilt:
            load_hand_library(private, rebuilt.library.sha256, cancel)
            if load_hand_receipt(private, rebuilt.library, output_sha, context.selection, cancel) != rebuilt.receipt:
                raise ProjectStorageError('Verified rebuilt hand receipt changed')
        installed_expression_inputs(mpfb_data_dir, cancel)
        if rebuilt: installed_inputs(mpfb_data_dir, cancel)
        if initial.facial_parameters: bundled_face_assets(mpfb_data_dir, cancel)

    recheck()
    publish_expression_edit(store, private, initial.expression.library_sha256,
                            base_sha, body_sha, operation, cancel)
    if rebuilt: publish_rebuilt_hand(store, rebuilt, cancel)
    def at_commit():
        recheck()
        # Validate the installed chain with original part IDs before its pointer
        # can become authoritative. This is admission, not source-motion approval.
        # Source IDs were separately rechecked above; project metadata is never
        # cleared. This read-only recipe projection checks the installed hand
        # and expression chain with the old unanimated admission guards intact.
        candidate = replace(initial, animations=(), master_blend='master/versions/'+output_sha+'.blend',
                            parts=proposed_parts)
        registered_expression_source(store, candidate, cancel)
    revision = stage_unverified_master(store, output, authorized_source_root=private.root,
        expected_project=initial, expected_project_id=initial.project_id, expected_revision=initial.revision,
        expected_sha256=output_sha, proposed_parts=proposed_parts, cancel=cancel, before_project_save=at_commit)
    return ReferencedMasterResult(revision.project, revision, operation,
        rebuilt.library.sha256 if rebuilt else None, {'source_references_preserved': True,
        'fresh_source_count': len(records), 'registered_hand_rebuilt': rebuilt is not None,
        'expression_strengths_preserved': True, 'original_master_preserved': True,
        'target_animation_verified': False, 'engine_import_verified': False})
