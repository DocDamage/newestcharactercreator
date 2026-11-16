"""Read-only saved-shape checks before referenced facial playback."""
from pathlib import Path
import struct

from ucc.core.errors import ProjectStorageError
from ucc.core.facial import NOSE_TARGETS
from .master_preview import _master_file, _digest
from .phenotype import from_saved_parameters, verify_evaluated_shape
from .protocol import JobRequest
from .runner import BlenderJobRunner


def inspect_expression_body_intent(store, project, *, blender_exe, worker_script, cancel, timeout_s):
    source, sha = _master_file(store, project.master_blend)
    expected = from_saved_parameters(project.parameters)
    runner = BlenderJobRunner(Path(blender_exe), store.root/'.ucc-jobs', Path(worker_script))
    reports = []; files = []
    for _ in range(2):
        request = JobRequest.new('inspect_character', input_project='candidate.blend',
                                 options={'macro_parameters': expected})
        result, directory = runner.run(request, staged_inputs={'candidate.blend': source},
                                       timeout_s=timeout_s, cancel=cancel)
        candidate = directory/'candidate.blend'
        if candidate.is_symlink() or _digest(candidate, cancel) != sha:
            raise ProjectStorageError('Body-intent inspection changed its exact prepared master')
        reports.append(result.details)
        files.extend((p, _digest(p, cancel)) for p in
                     (candidate, directory/'request.json', directory/'result.json'))
    return verify_evaluated_shape(expected, *reports), tuple(files)


def check_expression_face_intent(project, observation: dict) -> None:
    keys = observation.get('all_keys')
    if type(keys) is not dict:
        raise ProjectStorageError('Prepared facial preview has no original key observations')
    width = dict(project.facial_parameters).get('nose_width', .5)
    for target, weight in zip(NOSE_TARGETS, (max(0., .5-width), max(0., width-.5))):
        expected = struct.unpack('<f', struct.pack('<f', weight))[0]
        row = keys.get(target.name)
        actual = row.get('value') if type(row) is dict else (0. if row is None else None)
        if type(actual) not in (int, float) or actual != expected:
            raise ProjectStorageError('Apply saved face settings to the master before expression playback')
