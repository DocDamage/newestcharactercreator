"""Master-bound expression-preservation receipts and conservative admission."""
import json
from threading import Event

from ucc.core.errors import CompatibilityError, ProjectStorageError, ValidationError
from ucc.core.expression_library import canonical_digest, build_expression_receipt, validate_expression_receipt
from ucc.core.expression_recipe import build_expression_recipe
from ucc.core.expressions import is_sha256
from ucc.core.storage import ProjectStore, _unique_project_fields, _nonfinite_project_number
from .expression_inspection import CheckedExpressionMaster
from .expression_storage import ExpressionLibrary, check_cancel, safe_directory, _install_bytes, _read_json
from .master_preview import _master_file, _digest


def publish_expression_receipt(store: ProjectStore, library: ExpressionLibrary, source_sha256: str,
                                checked: CheckedExpressionMaster, operation: str,
                                cancel: Event | None = None) -> dict:
    proof = checked.observed
    receipt = build_expression_receipt(library.sha256, source_sha256, checked.sha256, operation,
        checked.report_sha256, canonical_digest(proof['observation']), proof['expression_keys_sha256'])
    if checked.report.is_symlink() or not checked.report.is_file():
        raise ProjectStorageError('Verified expression inspection report is missing or redirected')
    _install_bytes(safe_directory(store, 'expressions', 'inspections', create=True),
                   checked.report_sha256, checked.report.read_bytes(), cancel)
    data = json.dumps(receipt, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    _install_bytes(safe_directory(store, 'expressions', 'revisions', create=True), canonical_digest(receipt),
                   data, cancel, basename=checked.sha256+'.json')
    return receipt


def read_expression_receipt(store: ProjectStore, library: ExpressionLibrary, master_sha256: str,
                            cancel: Event | None = None) -> dict:
    if not is_sha256(master_sha256):
        raise ValidationError('Expression receipt requires a content-addressed master')
    path = safe_directory(store, 'expressions', 'revisions')/(master_sha256+'.json')
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 64*1024:
        raise ProjectStorageError('Prepared master has no registered expression receipt; external adoption is unsupported')
    try:
        raw = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique_project_fields,
                         parse_constant=_nonfinite_project_number)
    except (ValueError, RecursionError) as error:
        raise ValidationError('Invalid expression revision JSON') from error
    receipt = validate_expression_receipt(raw)
    if (receipt['master_sha256'] != master_sha256 or receipt['library_sha256'] != library.sha256
            or _digest(path, cancel) != canonical_digest(receipt)):
        raise ProjectStorageError('Expression revision receipt differs from this master/library binding')
    report_path = safe_directory(store, 'expressions', 'inspections')/(receipt['inspection_sha256']+'.json')
    report = _read_json(report_path, receipt['inspection_sha256'], 4*1024*1024, cancel)
    if (type(report) is not dict or type(report.get('schema_version')) is not int or report['schema_version'] != 1
            or report.get('policy') != library.manifest['policy']
            or report.get('master_sha256') != master_sha256
            or report.get('recipe_sha256') != canonical_digest(build_expression_recipe(master_sha256))
            or type(report.get('sample_count')) is not int or report['sample_count'] != 20
            or canonical_digest(report.get('observation')) != receipt['observation_sha256']
            or report.get('expression_keys_sha256') != receipt['expression_keys_sha256']
            or report.get('exact_neutral_restoration') is not True
            or report.get('visual_quality_approved') is not False or report.get('engine_import_verified') is not False):
        raise ProjectStorageError('Registered expression inspection differs from its saved-master receipt')
    return receipt


def admit_expression_source(store: ProjectStore, library: ExpressionLibrary, master_sha256: str,
                             cancel: Event | None = None) -> dict | None:
    """Require a registered chain rooted at the genuinely prepared original.

    This is provenance admission, never deformation or whole-body approval.
    The caller must still run fresh canonical-key/surface inspection.
    """
    root_sha = library.manifest['prepared_master_sha256']; current = master_sha256
    seen = set(); first = None
    for _ in range(1024):
        check_cancel(cancel)
        if current in seen:
            raise ProjectStorageError('Cyclic expression revision provenance')
        seen.add(current)
        path, _ = _master_file(store, 'master/versions/'+current+'.blend')
        if _digest(path, cancel) != current:
            raise ProjectStorageError('Expression provenance master changed')
        if current == root_sha:
            return first
        receipt = read_expression_receipt(store, library, current, cancel)
        if first is None: first = receipt
        current = receipt['source_master_sha256']
    raise CompatibilityError('Expression provenance chain exceeds the bounded inspection limit')
