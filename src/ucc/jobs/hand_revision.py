"""Atomic real-hand swaps/reset after independent original-source verification."""
from dataclasses import dataclass
import math
from pathlib import Path
from threading import Event
from uuid import uuid4

from ucc.core.errors import CompatibilityError,ProjectConflict,ProjectStorageError,ValidationError
from ucc.core.hand_parts import (TARGETS,METADATA_SHA256,ensure_source_intent,hand_selection,
                                 hand_asset_id,build_hand_receipt)
from ucc.core.master_versions import MasterRevision,stage_unverified_master
from ucc.core.models import CharacterProject,PartInstance
from ucc.core.storage import ProjectStore
from .geometry_evidence import EvidenceError
from .hand_storage import (check_cancel,installed_inputs,safe_directory,load_hand_library,
                            load_hand_receipt,publish_hand_receipt)
from .hand_revision_evidence import validate_revision_evidence
from .master_preview import _digest,_master_file
from .protocol import JobRequest
from .runner import BlenderJobRunner


@dataclass(frozen=True,slots=True)
class HandRevisionResult:
    project: CharacterProject
    revision: MasterRevision|None
    manifest_sha256: str
    observed: dict
    stage_job_id: str
    reopen_job_id: str


def apply_hand_revision(
    store: ProjectStore,*,manifest_sha256: str,selection: str,blender_exe: Path,worker_script: Path,
    mpfb_data_dir: Path,expected_project_id: str,expected_revision: int,expected_master_blend: str,
    cancel: Event|None=None,timeout_s: float=300,
) -> HandRevisionResult:
    if type(selection) is not str or selection not in {'neutral','shorter','longer'}:
        raise ValidationError('Select neutral, shorter or longer from the registered hand library')
    initial=store.load()
    if (type(expected_revision) is not int or initial.project_id != expected_project_id
            or initial.revision != expected_revision or initial.master_blend != expected_master_blend):
        raise ProjectConflict('Project changed before hand revision preparation')
    if initial.master_blend is None:
        raise ValidationError('Generate an existing master before swapping a hand')
    if type(timeout_s) not in (int,float) or not .05<=timeout_s<=3600 or not math.isfinite(timeout_s):
        raise ValidationError('Hand timeout_s is outside the supported range')
    check_cancel(cancel)
    executable,script=Path(blender_exe),Path(worker_script)
    if executable.is_symlink() or not executable.is_file() or script.is_symlink() or not script.is_file():
        raise ValidationError('Installed Blender executable or bundled bridge is missing/redirected')
    library=load_hand_library(store,manifest_sha256,cancel)
    ensure_source_intent(initial,library.manifest['recipe'])
    current=hand_selection(initial,manifest_sha256)
    source,source_sha=_master_file(store,expected_master_blend)
    if _digest(source,cancel) != source_sha:
        raise ProjectStorageError('Current hand master does not match its immutable filename')
    original_sha=library.manifest['recipe']['bindings']['master_sha256']
    options={'master_sha256':source_sha,'original_master_sha256':original_sha,'manifest_sha256':manifest_sha256,
             'metadata_sha256':METADATA_SHA256,**{t.variant+'_target_sha256':t.sha256 for t in TARGETS},
             **{v+'_asset_sha256':r['sha256'] for v,r in library.manifest['assets'].items()},
             'current_selection':current,'selection':selection}
    if current == 'neutral':
        if source_sha != original_sha:
            raise CompatibilityError('This hand library belongs to a different master; build compatible assets again')
    else:
        receipt=load_hand_receipt(store,library,source_sha,current,cancel)
        options['current_observation_sha256']=receipt['observation_sha256']
    metadata_sha=_digest(store.file,cancel)
    installed=installed_inputs(mpfb_data_dir,cancel)
    jobs=safe_directory(store,'.ucc-jobs',create=True)
    staged={'candidate.blend':source,'original.blend':library.source_master,'hand_manifest.json':library.manifest_path,
            'basemesh_vertex_groups.json':installed['basemesh_vertex_groups.json'],
            **{t.filename:installed[t.filename] for t in TARGETS},
            **{'hand-'+v+'.blend':p for v,p in library.assets.items()}}
    hashes={'candidate.blend':source_sha,'original.blend':original_sha,'hand_manifest.json':manifest_sha256,
            'basemesh_vertex_groups.json':METADATA_SHA256,**{t.filename:t.sha256 for t in TARGETS},
            **{'hand-'+v+'.blend':r['sha256'] for v,r in library.manifest['assets'].items()}}
    runner=BlenderJobRunner(executable,jobs,script)
    request=JobRequest.new('stage_mpfb_hand_revision',input_project='candidate.blend',options=options)
    stage,stage_dir=runner.run(request,staged_inputs=staged,timeout_s=timeout_s,cancel=cancel)
    output,report=stage_dir/'revised_human.blend',stage_dir/'hand_revision_report.json'
    if any(p.is_symlink() or not p.is_file() for p in (output,report)):
        raise EvidenceError('Hand worker produced no actual revised master/report')
    scene_sha,report_sha=_digest(output,cancel),_digest(report,cancel)
    verification=JobRequest.new('verify_mpfb_hand_revision',input_project='candidate.blend',
                                options=dict(options,revised_sha256=scene_sha,revision_report_sha256=report_sha))
    verified,verify_dir=runner.run(verification,staged_inputs={**staged,'revised_human.blend':output,
                                       'hand_revision_report.json':report},timeout_s=timeout_s,cancel=cancel)
    observed=validate_revision_evidence(stage.details,verified.details,options,scene_sha)
    all_paths={**staged,'revised_human.blend':output,'hand_revision_report.json':report}
    all_hashes=dict(hashes,**{'revised_human.blend':scene_sha,'hand_revision_report.json':report_sha})
    for name,path in all_paths.items():
        for candidate in (path,stage_dir/name,verify_dir/name):
            if candidate.is_symlink() or not candidate.is_file() or _digest(candidate,cancel) != all_hashes[name]:
                raise ProjectStorageError('Hand input/output changed before atomic promotion: '+name)
    installed_inputs(mpfb_data_dir,cancel)
    load_hand_library(store,manifest_sha256,cancel)
    if store.load() != initial or _digest(store.file,cancel) != metadata_sha:
        raise ProjectConflict('Project changed during hand revision; original master remains authoritative')
    check_cancel(cancel)
    revision=None
    if observed['selection_changed']:
        parts=()
        if selection != 'neutral':
            part_id=initial.parts[0].part_id if initial.parts else str(uuid4())
            parts=(PartInstance(part_id,hand_asset_id(manifest_sha256,selection),'hand.L'),)
            publish_hand_receipt(store,build_hand_receipt(manifest_sha256,scene_sha,original_sha,
                                  selection,observed['observation_sha256']),cancel)
        revision=stage_unverified_master(store,output,authorized_source_root=stage_dir,
                    expected_project_id=expected_project_id,expected_revision=expected_revision,
                    expected_sha256=scene_sha,expected_project=initial,proposed_parts=parts,cancel=cancel)
    return HandRevisionResult(revision.project if revision else initial,revision,manifest_sha256,
               {**observed,'original_master_preserved':True,
                'authoritative_master_sha256':scene_sha if revision else source_sha},request.job_id,verification.job_id)
