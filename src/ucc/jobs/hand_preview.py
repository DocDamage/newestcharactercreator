"""Complete actual static skin preview with source-bound left-hand camera bounds."""
from dataclasses import dataclass
import math
from pathlib import Path
from threading import Event

from ucc.core.errors import ProjectConflict,ProjectStorageError,ValidationError
from ucc.core.hand_parts import POLICY,TARGETS,METADATA_SHA256
from ucc.core.storage import ProjectStore
from .geometry_evidence import EvidenceError
from .hand_storage import installed_inputs,safe_directory,check_cancel
from .master_preview import MasterPreview,preview_saved_master,_master_file,_digest
from .protocol import JobRequest
from .runner import BlenderJobRunner


@dataclass(frozen=True,slots=True)
class HandPreview:
    preview: MasterPreview
    bounds: tuple[tuple[float,float,float],tuple[float,float,float]]


def preview_hand(store: ProjectStore,*,blender_exe: Path,worker_script: Path,mpfb_data_dir: Path,
                 expected_project_id: str,expected_revision: int,expected_master_blend: str,
                 cancel: Event|None=None,timeout_s: float=300) -> HandPreview:
    initial=store.load()
    if initial.master_blend is None:raise ValidationError('Generate a saved character before viewing hands')
    if type(timeout_s) not in (int,float) or not .05<=timeout_s<=3600 or not math.isfinite(timeout_s):
        raise ValidationError('Hand preview timeout_s is outside the supported range')
    if (initial.project_id!=expected_project_id or type(expected_revision) is not int
            or initial.revision!=expected_revision or initial.master_blend!=expected_master_blend):
        raise ProjectConflict('Saved character changed before hand preview')
    check_cancel(cancel);source,source_sha=_master_file(store,expected_master_blend)
    if _digest(source,cancel)!=source_sha:raise ProjectStorageError('Saved hand master identity changed')
    data=installed_inputs(mpfb_data_dir,cancel)
    staged={'candidate.blend':source,'basemesh_vertex_groups.json':data['basemesh_vertex_groups.json'],
            **{t.filename:data[t.filename] for t in TARGETS}}
    options={'master_sha256':source_sha,'metadata_sha256':METADATA_SHA256,
             **{t.variant+'_target_sha256':t.sha256 for t in TARGETS}}
    result,_=BlenderJobRunner(blender_exe,safe_directory(store,'.ucc-jobs',create=True),worker_script).run(
        JobRequest.new('inspect_mpfb_hand_bounds',input_project='candidate.blend',options=options),
        staged_inputs=staged,timeout_s=timeout_s,cancel=cancel)
    info=result.details;bounds=info.get('bounds')
    if (set(info)!={'schema_version','policy','master_sha256','slot','bounds','hand_vertices','visual_quality_approved'}
            or type(info['schema_version']) is not int or info['schema_version']!=1 or info['policy']!=POLICY
            or info['master_sha256']!=source_sha or info['slot']!='hand.L' or type(info['hand_vertices']) is not int
            or info['hand_vertices']!=1747 or info['visual_quality_approved'] is not False
            or type(bounds) is not list or len(bounds)!=2 or any(type(row) is not list or len(row)!=3 for row in bounds)
            or any(type(v) not in (int,float) or not -1e6<v<1e6 or not math.isfinite(v) for row in bounds for v in row)
            or any(a>=b for a,b in zip(*bounds)) or not .01<max(b-a for a,b in zip(*bounds))<.5):
        raise EvidenceError('Saved hand bounds lack exact source/region identities')
    preview=preview_saved_master(store,blender_exe=blender_exe,worker_script=worker_script,
                expected_project_id=expected_project_id,expected_revision=expected_revision,
                expected_master_blend=expected_master_blend,full_surface=True,timeout_s=timeout_s,cancel=cancel)
    if store.load()!=initial or preview.master_sha256!=source_sha or _digest(source,cancel)!=source_sha:
        raise ProjectConflict('Character changed during complete hand preview')
    return HandPreview(preview,tuple(tuple(float(v) for v in row) for row in bounds))
