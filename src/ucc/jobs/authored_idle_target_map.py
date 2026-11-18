"""Publish a private target map from an independently reopened original idle."""

from dataclasses import dataclass
import json
from pathlib import Path

from ucc.animations.native_profile import MAX_PROFILE_BYTES
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.storage import ProjectStore
from .authored_idle_loop_preview import _path, _source_from_idle_proof
from .authored_idle_receipt import _current_idle_mapping
from .authored_idle_transactions import publish_idle_document
from .export_destination import ExportDestination, plan_destination
from .godot_saved_preview_catalog import coordination_paths
from .target_action_context import TargetActionSourceReview, operation_budget, source_review


MAPPING_FILENAME = 'idle-target-mapping.json'


@dataclass(frozen=True, slots=True)
class PublishedAuthoredIdleTargetMapping:
    path: Path
    sha256: str


def publish_authored_idle_target_mapping(store: ProjectStore, *, proof_file: Path, database_path: Path,
        expected_review: TargetActionSourceReview, destination: ExportDestination,
        cancel=None, timeout_s=300) -> PublishedAuthoredIdleTargetMapping:
    """Recheck both saved contexts and publish bytes accepted by the ordinary mapping picker."""
    if type(expected_review) is not TargetActionSourceReview:
        raise ValidationError('Review the attached registered target source before creating a mapping')
    if type(destination) is not ExportDestination or plan_destination(destination.path, store.root) != destination:
        raise ValidationError('Choose a new local directory for the authored idle mapping')
    proof, database, output = (_path(str(path)) for path in (proof_file, database_path, destination.path))
    if output.is_relative_to(store.root):
        raise ValidationError('Choose a mapping folder outside the saved target project')

    try:
        with operation_budget(cancel, timeout_s) as budget:
            master_blend = store.load().master_blend

            def recheck_target():
                review = source_review(store, database, expected_review.source.clip_id, expected_review.project_id,
                    expected_review.revision, master_blend, expected_review.project_sha256, budget)
                if review != expected_review:
                    raise ProjectConflict('The attached registered source review changed; review it again')

            recheck_target()
            with _source_from_idle_proof(proof, database, budget) as (admitted, verifier, current, authority, inputs):
                if store.root.is_relative_to(inputs.project_root) or inputs.project_root.is_relative_to(store.root):
                    raise ValidationError('Open a separate target project copy before creating the authored idle mapping')
                receipt = json.loads(admitted.receipt_json)
                reserved = (inputs.project_root, inputs.candidate_directory, proof.parent, inputs.blender.parent,
                    inputs.worker.parent, *coordination_paths(database), *coordination_paths(inputs.database),
                    *(Path(name).parent for name in receipt['worker_dependencies']))
                if any(output.is_relative_to(path) for path in reserved):
                    raise ValidationError('Choose a mapping folder outside the original project, candidate, proof, catalogs and runtime')
                candidate, source = admitted.candidate, expected_review.source
                if (candidate.target.project_id, candidate.target.master_sha256,
                        candidate.source_sha256, candidate.snapshot_sha256) != (
                        expected_review.project_id, expected_review.master_sha256,
                        source.source_sha256, source.snapshot_sha256):
                    raise ProjectConflict('The authored idle proof differs from the exact attached source, snapshot or saved master')
                mapping = _current_idle_mapping(admitted, verifier, current)
                if len(mapping.mapping_json) > MAX_PROFILE_BYTES:
                    raise ValidationError('The authored idle mapping exceeds the target mapping limit')

            def guard():
                recheck_target()
                authority.assert_current()

            digest = publish_idle_document(store, destination, MAPPING_FILENAME, mapping.mapping_json, guard, budget)
            return PublishedAuthoredIdleTargetMapping(output/MAPPING_FILENAME, digest)
    except OSError as error:
        raise ProjectStorageError('Cannot authenticate the authored idle proof or save the new mapping') from error
