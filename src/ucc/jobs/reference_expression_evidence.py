"""Revalidate referenced preview ownership and complete private cache evidence."""
from dataclasses import replace
from pathlib import Path

from ucc.core.errors import ProjectConflict, ProjectStorageError
from ucc.core.expression_clip import build_expression_clip
from ucc.core.expression_library import canonical_digest
from ucc.core.expressions import TARGETS
from ucc.preview.expression_cache import read_json, read_expression_cache, validate_clip_report
from .animation_reference_storage import check_registered_source
from .catalog_clip import _saved_reference
from ucc.library.provenance import LicensePolicy
from .expression_storage import check_cancel, safe_directory
from .expression_verification import registered_expression_source
from .master_preview import _digest
from .reference_expression_intent import check_expression_face_intent


def reference_expression_receipt(result) -> dict:
    from .reference_expression_preview import POLICY
    preview = result.preview
    return {'schema_version': 1, 'policy': POLICY,
        'owner_project_sha256': canonical_digest(result.project.to_dict()),
        'owner_metadata_sha256': result.metadata_sha256,
        'private_project_sha256': canonical_digest(result.context.project.to_dict()),
        'master_sha256': preview.master_sha256, 'library_sha256': preview.library_sha256,
        'clip_sha256': preview.clip_sha256, 'preview_bindings': preview.bindings,
        'verified_observation_sha256': canonical_digest(preview.observed),
        'body_observation_sha256': canonical_digest(result.body_observed),
        'references': list(result.references), 'catalog_path': str(result.database_path),
        'source_paths': [str(p) for p in result.source_paths],
        'owner_dependencies': {str(p): sha for p, sha in result.context.dependencies},
        'private_evidence': {str(p): sha for p, sha in result.private_evidence},
        'source_references_preserved': True, 'editable_master_unchanged': True,
        'source_motion_applied': False, 'engine_import_verified': False, 'visual_quality_approved': False}


def registered_reference_paths(database_path, records) -> tuple[Path, ...]:
    paths = []
    for record in records:
        entry, _, _, _ = _saved_reference(database_path, record['clip_id'], record['source_sha256'],
                                          LicensePolicy.from_dict(record['license']))
        path = Path(entry.source_path)
        if path.is_symlink() or not path.is_file():
            raise ProjectStorageError('Registered facial-preview source path is missing or redirected')
        paths.append(path.resolve(strict=True))
    return tuple(paths)


def _owned_file(store, path: Path, sha: str, cancel) -> None:
    try: relative = path.relative_to(store.root)
    except ValueError as error:
        raise ProjectStorageError('Referenced preview evidence escaped its project') from error
    safe_directory(store, *relative.parent.parts)
    if path.is_symlink() or not path.is_file() or _digest(path, cancel) != sha:
        raise ProjectStorageError('Referenced facial preview evidence changed: '+str(relative))


def _check_cache_evidence(store, result, cancel) -> None:
    preview = result.preview; project = result.context.project
    if (preview.workdir == preview.verify_dir or preview.workdir.name != preview.stage_job_id
            or preview.verify_dir.name != preview.reopen_job_id):
        raise ProjectStorageError('Facial playback requires its two distinct bound worker directories')
    expected_clip = build_expression_clip(project, preview.master_sha256)
    for directory in (preview.workdir, preview.verify_dir):
        if directory.parent != result.context.store.root/'.ucc-jobs':
            raise ProjectStorageError('Facial cache workers belong to another private project')
        for target in TARGETS:
            _owned_file(store, directory/target.staged_name,
                        preview.bindings[target.role+'_'+target.family+'_sha256'], cancel)
        clip = read_json(directory/'expression_clip.json', preview.clip_sha256, 128*1024)
        if canonical_digest(clip) != canonical_digest(expected_clip):
            raise ProjectConflict('Private expression strengths or project snapshot differ from their bound owner')
        for name, field in (('candidate.blend', 'master_sha256'), ('expression_motion.blend', 'motion_sha256')):
            _owned_file(store, directory/name, preview.bindings[field], cancel)
        report = read_json(directory/'expression_motion.json', preview.bindings['motion_report_sha256'], 4*1024*1024)
        validate_clip_report(report, preview.bindings)
        if report['neutral_state_sha256'] != canonical_digest(preview.inspection.observed['observation']):
            raise ProjectStorageError('Facial clip does not preserve its verified neutral observation')
        checked = read_expression_cache(directory, preview.bindings, preview.observed, report,
                                       cancel_check=lambda: check_cancel(cancel))
        if checked != preview.cache:
            raise ProjectStorageError('Facial playback buffers differ from their independently reopened evidence')


def check_referenced_expression_preview(store, database_path, result, cancel=None) -> None:
    from .reference_expression_preview import ReferenceExpressionPreview
    if not isinstance(result, ReferenceExpressionPreview):
        raise ProjectStorageError('Expected an explicitly owner-bound referenced facial preview')
    database_path = Path(database_path)
    if database_path.is_symlink() or not database_path.is_file() or database_path.resolve(strict=True) != result.database_path:
        raise ProjectStorageError('Facial preview belongs to another registered source catalog')
    check_cancel(cancel); project = result.project; context = result.context; preview = result.preview
    if store.load() != project or _digest(store.file, cancel) != result.metadata_sha256:
        raise ProjectConflict('Saved owner changed during referenced facial playback')
    private_root = context.store.root
    if private_root.parent != safe_directory(store, '.ucc-jobs') or private_root.is_symlink():
        raise ProjectStorageError('Private expression projection is outside the owner jobs directory')
    if (context.store.load() != context.project or context.project != replace(project, animations=(), revision=context.project.revision)
            or preview.project_id != project.project_id or preview.revision != context.project.revision
            or preview.master_blend != project.master_blend or preview.master_sha256 != Path(project.master_blend).stem
            or preview.library_sha256 != project.expression.library_sha256):
        raise ProjectConflict('Private facial preview does not describe the exact saved owner')
    if tuple(r['clip_id'] for r in result.references) != project.animations:
        raise ProjectStorageError('Referenced facial preview changed source identifiers or their order')
    for record in result.references:
        if check_registered_source(store, database_path, project.project_id, record['clip_id'], cancel) != record:
            raise ProjectStorageError('A bound source or its policy changed before facial playback')
    if registered_reference_paths(database_path, result.references) != result.source_paths:
        raise ProjectStorageError('Registered facial-preview source paths changed')
    context.recheck(store, cancel)
    registered_expression_source(context.store, context.project, cancel)
    registered_expression_source(store, replace(project, animations=()), cancel)
    inspection = preview.inspection
    if (inspection.sha256 != preview.master_sha256 or inspection.master != private_root/project.master_blend
            or (inspection.report, inspection.report_sha256) not in result.private_evidence):
        raise ProjectStorageError('Neutral expression inspection belongs to another private master')
    for path, sha in result.private_evidence: _owned_file(store, path, sha, cancel)
    if read_json(inspection.report, inspection.report_sha256, 4*1024*1024) != inspection.observed:
        raise ProjectStorageError('Neutral expression observation differs from its saved inspection')
    _owned_file(store, context.store.root/project.master_blend, preview.master_sha256, cancel)
    _owned_file(store, store.root/project.master_blend, preview.master_sha256, cancel)
    check_expression_face_intent(project, preview.inspection.observed['observation'])
    if result.receipt_path != preview.workdir/'reference_expression_preview.json':
        raise ProjectStorageError('Referenced facial receipt was substituted')
    _owned_file(store, result.receipt_path, result.receipt_sha256, cancel)
    actual = read_json(result.receipt_path, result.receipt_sha256, 4*1024*1024)
    if canonical_digest(actual) != canonical_digest(reference_expression_receipt(result)):
        raise ProjectStorageError('Referenced facial receipt differs from its exact owner/source/private bindings')
    _check_cache_evidence(store, result, cancel)
    check_cancel(cancel)
