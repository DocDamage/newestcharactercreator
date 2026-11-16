"""Read-only facial playback with explicit owner/source and private bindings."""
from dataclasses import dataclass, replace
import json
import math
from pathlib import Path
from threading import Event

from ucc.animations.project_references import build_source_binding
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.expression_library import canonical_digest
from ucc.core.models import CharacterProject
from ucc.core.reference_master_intent import supports_referenced_master_intent
from ucc.library.provenance import LicensePolicy
from .animation_reference_storage import check_registered_source
from .catalog_clip import verify_catalog_fbx_clip
from .expression_preview import ExpressionPreview, preview_saved_expressions
from .expression_storage import check_cancel
from .master_preview import _digest
from .project_animation_references import _context, _neutral
from .reference_expression_context import ReferenceExpressionContext, prepare_reference_expression_context
from .reference_expression_intent import inspect_expression_body_intent, check_expression_face_intent
from .reference_expression_evidence import check_referenced_expression_preview, registered_reference_paths

POLICY = 'READ_ONLY_REFERENCED_EXPRESSION_PREVIEW_V1'


@dataclass(frozen=True, slots=True)
class ReferenceExpressionPreview:
    project: CharacterProject
    metadata_sha256: str
    context: ReferenceExpressionContext
    preview: ExpressionPreview
    references: tuple[dict, ...]
    body_observed: dict
    private_evidence: tuple[tuple[Path, str], ...]
    receipt_path: Path
    receipt_sha256: str
    database_path: Path
    source_paths: tuple[Path, ...]


def preview_referenced_expressions(store, database_path: Path, *, blender_exe: Path,
        worker_script: Path, mpfb_data_dir: Path, expected_project_id: str,
        expected_revision: int, expected_master_blend: str,
        cancel: Event | None = None, timeout_s: float = 300) -> ReferenceExpressionPreview:
    if type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not .05 <= timeout_s <= 3600:
        raise ValidationError('Referenced expression timeout_s is outside the supported range')
    database_path = Path(database_path)
    if database_path.is_symlink() or not database_path.is_file():
        raise ProjectStorageError('Select the existing registered source catalog')
    database_path = database_path.resolve(strict=True)
    initial, sha, metadata_sha, unchanged = _context(store, expected_project_id,
        expected_revision, expected_master_blend, cancel)
    if not supports_referenced_master_intent(initial):
        raise ValidationError('Referenced facial playback requires prepared MPFB expressions and a supported hand')
    runtime = dict(blender_exe=blender_exe, worker_script=worker_script, cancel=cancel, timeout_s=timeout_s)
    records = tuple(check_registered_source(store, database_path, initial.project_id, clip, cancel)
                    for clip in initial.animations)
    source_paths = registered_reference_paths(database_path, records)
    _neutral(store, initial, sha, metadata_sha, blender_exe, worker_script, cancel, timeout_s)
    for record in records:
        fresh = verify_catalog_fbx_clip(database_path, record['clip_id'],
            expected_source_sha256=record['source_sha256'], expected_policy=LicensePolicy.from_dict(record['license']),
            jobs_root=store.root/'.ucc-jobs', **runtime)
        if build_source_binding(initial.project_id, fresh) != record:
            raise ProjectStorageError('Fresh source differs from this facial preview reference binding')
    unchanged()
    context = prepare_reference_expression_context(store, initial, cancel)
    private = context.store; project = private.load()
    if project != replace(initial, animations=(), revision=project.revision):
        raise ProjectStorageError('Apply saved shape settings before previewing the registered physical hand')
    body, files = inspect_expression_body_intent(private, project, **runtime)
    result = preview_saved_expressions(private, mpfb_data_dir=mpfb_data_dir,
        expected_project_id=project.project_id, expected_revision=project.revision,
        expected_master_blend=project.master_blend, **runtime)
    check_expression_face_intent(initial, result.inspection.observed['observation'])
    files += ((result.inspection.report, result.inspection.report_sha256),)
    receipt = result.workdir/'reference_expression_preview.json'
    provisional = ReferenceExpressionPreview(initial, metadata_sha, context, result, records, body, files, receipt, '', database_path, source_paths)
    from .reference_expression_evidence import reference_expression_receipt
    data = json.dumps(reference_expression_receipt(provisional), sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode()
    if len(data) > 4*1024*1024:
        raise ProjectStorageError('Referenced facial preview receipt exceeds its metadata budget')
    unchanged(); context.recheck(store, cancel); check_cancel(cancel)
    with receipt.open('xb') as stream: stream.write(data)
    bound = replace(provisional, receipt_sha256=_digest(receipt, cancel))
    check_referenced_expression_preview(store, database_path, bound, cancel)
    unchanged()
    return bound
