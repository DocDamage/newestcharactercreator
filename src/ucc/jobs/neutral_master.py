"""Two fresh exact-neutral observations, bound to an unchanged saved project."""
from dataclasses import dataclass
import math
from pathlib import Path
from threading import Event

from ucc.animations.source_rest_frames import is_sha256
from ucc.core.errors import ProjectConflict, ProjectStorageError, ValidationError
from ucc.core.storage import ProjectStore
from .master_preview import _master_file, _digest
from .protocol import JobRequest
from .runner import BlenderJobRunner

POLICY = 'READ_ONLY_MPFB_EXACT_NEUTRAL_MASTER_V1'
HASHES = {'state_sha256', 'full_skin_sha256', 'visible_skin_sha256', 'rest_sha256', 'weights_sha256', 'key_state_sha256'}
FALSE_FLAGS = {'source_provenance_verified', 'project_action_admission_verified', 'engine_import_verified', 'visual_quality_approved'}


@dataclass(frozen=True, slots=True)
class NeutralMasterInspection:
    project_id: str
    revision: int
    project_metadata_sha256: str
    master_sha256: str
    observation: dict
    worker_job_ids: tuple[str, str]


def checked_observation(raw, master_sha: str, expression_count: int) -> dict:
    expected = {'schema_version': 1, 'policy': POLICY, 'master_sha256': master_sha, 'mpfb_version': '2.0.18',
        'bone_count': 163, 'full_vertex_count': 19158, 'visible_vertex_count': 13380,
        'action_count': 0, 'driven_datablocks': 0, 'nla_tracks': 0, 'bone_constraints': 0,
        'exact_identity_pose_basis': True, 'expression_key_count': expression_count, 'source_state_preserved': True,
        **{name: False for name in FALSE_FLAGS}}
    if (type(raw) is not dict or set(raw) != set(expected)|HASHES|{'blender_version', 'inspected_datablocks'}
            or any(type(raw[k]) is not type(v) or raw[k] != v for k, v in expected.items())
            or any(not is_sha256(raw[k]) for k in HASHES)
            or type(raw['inspected_datablocks']) is not int or not 1 <= raw['inspected_datablocks'] <= 100000
            or type(raw['blender_version']) is not str or not raw['blender_version'].startswith('5.3.')
            or len(raw['blender_version']) > 64 or any(ord(c) < 32 for c in raw['blender_version'])):
        raise ValidationError('Incomplete or incompatible exact-neutral master observation')
    return raw


def inspect_saved_neutral_master(store: ProjectStore, *, blender_exe: Path, worker_script: Path,
                                 expected_project_id: str, expected_revision: int, expected_master_blend: str,
                                 cancel: Event | None = None, timeout_s: float = 300) -> NeutralMasterInspection:
    """Inspect actual neutrality even when metadata contains external clip IDs.

    This does not admit an arbitrary rehashed master, validate clip references,
    authorize editing or change the project. Those checks remain separate.
    """
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s) or not .05 <= timeout_s <= 3600):
        raise ValidationError('Neutral inspection timeout_s is outside the supported range')
    try:
        executable, script = Path(blender_exe), Path(worker_script)
    except TypeError as error:
        raise ValidationError('Select the installed Blender and bundled bridge paths') from error
    if any(p.is_symlink() or not p.is_file() for p in (executable, script)):
        raise ValidationError('Installed Blender executable or bundled bridge is missing/redirected')
    initial = store.load()
    if (type(expected_revision) is not int or initial.project_id != expected_project_id
            or initial.revision != expected_revision or initial.master_blend != expected_master_blend):
        raise ProjectConflict('Saved project changed before neutral-master inspection')
    if initial.master_blend is None or initial.family != 'humanoid.v1' or initial.base_provider != 'mpfb':
        raise ValidationError('Neutral inspection requires an existing MPFB humanoid master')
    def check_cancel():
        if cancel is not None and cancel.is_set():
            raise ProjectStorageError('Neutral-master inspection cancelled; original project retained')
    check_cancel(); master, master_sha = _master_file(store, initial.master_blend)
    metadata_sha = _digest(store.file, cancel)
    def unchanged():
        check_cancel()
        if jobs.is_symlink() or jobs.resolve(strict=False).parent != store.root:
            raise ProjectStorageError('Neutral inspection private jobs path is redirected')
        current, sha = _master_file(store, initial.master_blend)
        if store.load() != initial or _digest(store.file, cancel) != metadata_sha:
            raise ProjectConflict('Saved project changed during neutral-master inspection')
        if current != master or sha != master_sha or _digest(current, cancel) != master_sha:
            raise ProjectStorageError('Saved neutral master bytes changed during inspection')
    jobs = store.root/'.ucc-jobs'
    runner = BlenderJobRunner(executable, jobs, script)
    observations = []; job_ids = []
    for _ in range(2):
        unchanged()
        request = JobRequest.new('inspect_mpfb_neutral_master', input_project='candidate.blend',
                                 options={'master_sha256': master_sha})
        result, folder = runner.run(request, staged_inputs={'candidate.blend': master}, cancel=cancel, timeout_s=timeout_s)
        unchanged()
        staged = folder/'candidate.blend'
        if (folder.is_symlink() or folder.resolve().parent != jobs.resolve() or staged.is_symlink()
                or not staged.is_file() or _digest(staged, cancel) != master_sha):
            raise ProjectStorageError('Staged neutral master is missing, redirected or changed')
        observations.append(checked_observation(result.details, master_sha, 12 if initial.expression is not None else 0))
        job_ids.append(request.job_id)
    if observations[0] != observations[1]:
        raise ValidationError('Independent neutral-master workers disagree on original exact state')
    unchanged()
    return NeutralMasterInspection(initial.project_id, initial.revision, metadata_sha, master_sha,
                                   observations[0], tuple(job_ids))
