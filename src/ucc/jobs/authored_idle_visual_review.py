"""Retain a human visual declaration for one authenticated private idle target."""

from dataclasses import dataclass
from pathlib import Path

from ucc.animations.target_action_diagnostic_contract import TargetActionDiagnosticSelection
from ucc.core.authored_idle_visual_review import AuthoredIdleVisualDecision
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.storage import MAX_JSON_BYTES, ProjectStore
from ucc.core.target_action_format import MAX_BYTES, MAX_FILE_BYTES, canonical_bytes
from .authored_idle_io import MAX_EVIDENCE_BYTES
from .authored_idle_loop_preview import AuthoredIdleReviewIdentity, _path, _pointer, load_authored_idle_loop_preview
from .authored_idle_transactions import publish_idle_document
from .export_destination import ExportDestination, plan_destination
from .godot_saved_preview_files import ProofReads
from .target_action_context import check_target_action_catalog, operation_budget


POLICY = 'UCC_PRIVATE_AUTHORED_IDLE_VISUAL_DECISION_V1'
DECISION_FILENAME = 'idle-visual-decision.json'


@dataclass(frozen=True, slots=True)
class PublishedAuthoredIdleVisualDecision:
    path: Path
    sha256: str


def publish_authored_idle_visual_decision(store: ProjectStore, *, proof_file: Path,
        selection: TargetActionDiagnosticSelection, database_path: Path,
        expected_identity: AuthoredIdleReviewIdentity, decision: AuthoredIdleVisualDecision,
        destination: ExportDestination, cancel=None, timeout_s=300) -> PublishedAuthoredIdleVisualDecision:
    """Save the supplied declaration separately from project, proof and runtime records."""
    if type(decision) is not AuthoredIdleVisualDecision:
        raise ValidationError('Supply your own explicit visual decision and review confirmation')
    if (type(expected_identity) is not AuthoredIdleReviewIdentity
            or type(selection) is not TargetActionDiagnosticSelection or expected_identity.selection != selection):
        raise ValidationError('Choose the exact authenticated target and authored idle proof you reviewed')
    if type(destination) is not ExportDestination or plan_destination(destination.path, store.root) != destination:
        raise ValidationError('Choose a new local folder for the visual decision')
    target_root, proof, database, output = (_path(str(path)) for path in
                                            (store.root, proof_file, database_path, destination.path))
    if output.is_relative_to(target_root) or output.is_relative_to(proof.parent):
        raise ValidationError('Choose a decision folder outside the saved target project and proof folder')

    try:
        with operation_budget(cancel, timeout_s) as budget:
            preview = load_authored_idle_loop_preview(store, proof_file=proof, selection=selection,
                database_path=database, local_preview_confirmed=decision.personally_reviewed,
                cancel=budget.cancel, timeout_s=budget.remaining())
            if preview.review_identity != expected_identity:
                raise ProjectConflict('The current idle proof differs from the exact preview you reviewed')
            if any(output.is_relative_to(scope) for scope in preview._protected_output_scopes):
                raise ValidationError('Choose a decision folder outside the authoring project, candidate, catalogs and runtime')
            stamps = dict(preview.watched_identities)
            binding = target_root/'animations/actions'/selection.binding_sha256
            receipt = preview._candidate_directory/'authored_idle_receipt.json'

            def guard():
                budget.check()
                preview.assert_current()
                reads = ProofReads(budget)
                raw = reads.capture(proof, MAX_BYTES, expected_identity.proof_sha256)
                for record in _pointer(raw)['source_policy_records']:
                    reads.record(_path(record['path']), MAX_BYTES, record['sha256'])
                reads.record(receipt, MAX_EVIDENCE_BYTES, expected_identity.receipt_sha256)
                reads.record(store.file, MAX_JSON_BYTES, selection.project_sha256)
                reads.record(binding/'binding.json', MAX_BYTES, selection.binding_sha256)
                reads.record(binding/'native_mapping.json', MAX_BYTES, expected_identity.mapping_sha256)
                reads.record(binding/'playback/motion_skin.bin', MAX_FILE_BYTES, expected_identity.cache_sha256)
                check_target_action_catalog(database, preview._target_source,
                    expected_database_identity=stamps[database], expected_parent_identity=stamps[database.parent])
                preview.assert_current()

            payload = canonical_bytes({'schema_version': 1, 'policy': POLICY, 'private_local_only': True,
                'reviewed_identity': preview.review_identity.to_dict(), 'visual_decision': decision.to_dict()})
            digest = publish_idle_document(store, destination, DECISION_FILENAME, payload, guard, budget)
            return PublishedAuthoredIdleVisualDecision(output/DECISION_FILENAME, digest)
    except OSError as error:
        failure = ProjectStorageError('Cannot verify the current idle evidence or save the local visual decision')
        for note in getattr(error, '__notes__', ()):
            failure.add_note(note)
        raise failure from error
