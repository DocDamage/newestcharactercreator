"""Publish one local proof pointer for a currently authenticated idle candidate."""

from dataclasses import dataclass
import json
from pathlib import Path

from ucc.core.errors import ProjectStorageError, ValidationError
from ucc.core.target_action_format import canonical_bytes
from .authored_idle_loop_preview import POLICY, _path, _pointer
from .authored_idle_policy import IdleSourcePolicyRecord
from .authored_idle_receipt import _admitted_idle_candidate
from .authored_idle_transactions import publish_idle_document
from .export_destination import ExportDestination, plan_destination
from .godot_candidate_inputs import identity
from .target_action_context import operation_budget, protected


PROOF_FILENAME = 'idle-loop-proof.json'


@dataclass(frozen=True, slots=True)
class PublishedAuthoredIdleLoopProof:
    path: Path
    sha256: str


def publish_authored_idle_loop_proof(store, *, directory: Path, expected_receipt_sha256: str,
        source_policy_records: tuple[IdleSourcePolicyRecord, ...], database_path: Path, blender_exe: Path, worker_script: Path,
        destination: ExportDestination, cancel=None, timeout_s=300) -> PublishedAuthoredIdleLoopProof:
    """Reopen current authoring evidence, then publish a private pointer without native work."""
    if type(destination) is not ExportDestination or plan_destination(destination.path, store.root) != destination:
        raise ValidationError('Choose a new local folder for the idle loop proof')
    root, candidate, database, blender, worker, output = (
        _path(str(path)) for path in (store.root, directory, database_path, blender_exe, worker_script, destination.path))
    reserved = (root, candidate, blender.parent, worker.parent,
                *(Path(str(database) + suffix) for suffix in ('', '-wal', '-shm', '-journal')))
    if any(output.is_relative_to(path) for path in reserved):
        raise ValidationError('Choose a proof folder outside the original project, candidate, catalog and runtime')

    with operation_budget(cancel, timeout_s) as budget:
        stamps = {}

        def remember(rows):
            for path, stamp in rows.items():
                budget.check()
                if stamps.setdefault(path, stamp) != stamp:
                    raise ProjectStorageError('Idle proof reads disagree on current source identity')

        def unchanged():
            for path, stamp in stamps.items():
                budget.check()
                protected(path)
                if (identity(path) if path.exists() else None) != stamp:
                    raise ProjectStorageError('Idle proof source changed before exclusive publication')

        with _admitted_idle_candidate(store, candidate, expected_receipt_sha256, source_policy_records,
                database, blender, worker, budget.cancel, budget.remaining(),
                capture_authority=remember) as (admitted, _, current):
            receipt = json.loads(admitted.receipt_json)
            if any(output.is_relative_to(Path(name).parent) for name in receipt['worker_dependencies']):
                raise ValidationError('Choose a proof folder outside the retained runtime dependency folders')
            records = [{'asset_id': row.asset_id, 'path': str(_path(str(row.path))), 'sha256': row.sha256}
                       for row in source_policy_records]
            payload = canonical_bytes({'schema_version': 1, 'policy': POLICY, 'project_root': str(root),
                'catalog_path': str(database), 'candidate_directory': str(admitted.candidate.directory),
                'receipt_sha256': admitted.candidate.receipt_sha256, 'source_policy_records': records,
                'blender_executable': {'path': str(blender), 'sha256': receipt['blender_executable_sha256']},
                'worker_script': {'path': str(worker), 'sha256': receipt['worker_dependencies'][str(worker)]}})
            _pointer(payload)
            current.check()
        digest = publish_idle_document(store, destination, PROOF_FILENAME, payload, unchanged, budget)
        return PublishedAuthoredIdleLoopProof(output/PROOF_FILENAME, digest)
