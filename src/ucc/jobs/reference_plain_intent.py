"""Two fresh saved-scene read-backs bind plain physical body to slider intent."""
from pathlib import Path
from threading import Event

from ucc.core.errors import ProjectStorageError
from ucc.core.storage import ProjectStore
from .master_preview import _digest, _master_file
from .phenotype import from_saved_parameters, verify_evaluated_shape
from .project_animation_references import _context
from .protocol import JobRequest
from .runner import BlenderJobRunner


def inspect_plain_body_intent(store: ProjectStore, *, blender_exe: Path, worker_script: Path,
        expected_project_id: str, expected_revision: int, expected_master_blend: str,
        cancel: Event | None, timeout_s: float) -> dict:
    initial, master_sha, _, unchanged = _context(store, expected_project_id, expected_revision,
                                               expected_master_blend, cancel)
    macro = from_saved_parameters(initial.parameters)
    source, _ = _master_file(store, initial.master_blend)
    runner = BlenderJobRunner(blender_exe, store.root/'.ucc-jobs', worker_script)
    reports = []
    for _ in range(2):
        request = JobRequest.new('inspect_character', input_project='plain_candidate.blend',
                                 options={'macro_parameters': macro})
        result, directory = runner.run(request, staged_inputs={'plain_candidate.blend': source},
                                       timeout_s=timeout_s, cancel=cancel)
        copied = directory/'plain_candidate.blend'
        if copied.is_symlink() or not copied.is_file() or _digest(copied, cancel) != master_sha:
            raise ProjectStorageError('Plain body read-back used another saved master')
        reports.append(result.details)
        unchanged()
    proof = verify_evaluated_shape(macro, *reports)
    unchanged()
    return proof
