"""Add verified frame-specific normals/material over unchanged facial geometry."""
from dataclasses import dataclass,replace
from pathlib import Path
from threading import Event
import math,time
from ucc.core.errors import ProjectConflict,ProjectStorageError,ValidationError
from ucc.core.expression_material import POLICY,STAGE,VERIFY
from ucc.core.expression_library import canonical_digest
from ucc.core.expressions import TARGETS
from ucc.core.skin_material import APPEARANCE_KEY,SkinMaterialSpec
from ucc.core.storage import ProjectStore
from ucc.preview.expression_material import read_material_expression
from ucc.preview.expression_cache import read_json
from .expression_preview import preview_saved_expressions,ExpressionPreview
from .skin_material_preparation import _BudgetCancel
from .skin_material_storage import registered_material_binding
from .godot_candidate_inputs import project_sources,regular_file
from .expression_storage import safe_directory
from .master_preview import _digest
from .runner import BlenderJobRunner
from .protocol import JobRequest
from .worker_resources import worker_dependency_files


@dataclass(frozen=True,slots=True)
class MaterialExpressionEvidence:
    workdir: Path
    verify_dir: Path
    bindings: dict
    proof: dict
    watched_inputs: tuple[tuple[str,str],...]
    stage_job_id: str
    reopen_job_id: str


def preview_material_expressions(store: ProjectStore,*,blender_exe: Path,worker_script: Path,mpfb_data_dir: Path,
        expected_project_id: str,expected_revision: int,expected_master_blend: str,
        cancel: Event | None=None,timeout_s: float=1800) -> ExpressionPreview:
    if type(timeout_s) not in (int,float) or not math.isfinite(timeout_s) or not .05<=timeout_s<=3600:
        raise ValidationError('Material facial preview needs a bounded total deadline')
    deadline=time.monotonic()+timeout_s;budget=_BudgetCancel(cancel,deadline)
    def remaining():
        if budget.is_set():raise ProjectStorageError('Material facial preview cancelled or total deadline exceeded')
        return max(.05,deadline-time.monotonic())
    remaining();initial=store.load()
    if (initial.project_id!=expected_project_id or type(expected_revision) is not int or initial.revision!=expected_revision
            or initial.master_blend!=expected_master_blend):raise ProjectConflict('Saved character changed before material facial preview')
    binding=registered_material_binding(store,initial,budget)
    if binding is None:raise ValidationError('Material facial preview needs a registered owned material')
    spec=SkinMaterialSpec.from_dict(binding['spec']);sources=project_sources(store,initial,budget)
    paths={store.file,*sources.values(),Path(blender_exe).resolve(),*worker_dependency_files(Path(worker_script))}
    paths.add(safe_directory(store,'materials','manifests')/(dict(initial.appearance)[APPEARANCE_KEY]+'.json'))
    paths.update(safe_directory(store,'materials','proofs')/(binding[k]+'.json') for k in ('recipe_sha256','stage_sha256','verification_sha256'))
    paths.update(safe_directory(store,'master','versions')/(binding[k]+'.blend') for k in ('source_master_sha256','material_master_sha256','final_master_sha256'))
    paths.update(Path(__file__).resolve().parents[1].rglob('*.py'))
    hashes={p:_digest(p,budget) for p in paths}
    def unchanged():
        remaining()
        if store.load()!=initial or project_sources(store,initial,budget)!=sources:raise ProjectConflict('Saved material facial preview sources changed')
        for p,h in hashes.items():
            if p.is_symlink() or not p.is_file() or _digest(p,budget)!=h:raise ProjectStorageError('Material facial source, proof or adapter changed')
        if registered_material_binding(store,initial,budget)!=binding:raise ProjectStorageError('Saved facial material binding changed')
    expected=dict(expected_project_id=initial.project_id,expected_revision=initial.revision,expected_master_blend=initial.master_blend)
    geometry=preview_saved_expressions(store,blender_exe=blender_exe,worker_script=worker_script,mpfb_data_dir=mpfb_data_dir,
        cancel=budget,timeout_s=remaining(),**expected);unchanged()
    options={**geometry.bindings,'owned_material_spec':spec.to_dict()}
    names=['candidate.blend','expression_clip.json','expression_motion.blend','expression_motion.json','expression_skin.bin','expression_skin.json',*[t.staged_name for t in TARGETS]]
    staged={name:geometry.workdir/name for name in names}
    original={name:_digest(p,budget) for name,p in staged.items()}
    runner=BlenderJobRunner(Path(blender_exe),safe_directory(store,'.ucc-jobs',create=True),Path(worker_script))
    request=JobRequest.new(STAGE,input_project='candidate.blend',options=options)
    stage,folder=runner.run(request,staged_inputs=staged,timeout_s=remaining(),cancel=budget);unchanged()
    normals=regular_file(folder/'expression_normals.bin',folder,32*1024*1024)
    manifest=regular_file(folder/'expression_normals.json',folder,4*1024*1024)
    options.update(normals_sha256=_digest(normals,budget),normals_manifest_sha256=_digest(manifest,budget))
    stage_expected={'schema_version':1,'policy':POLICY,'bindings':geometry.bindings,'owned_material_spec':spec.to_dict(),
        'normals_sha256':options['normals_sha256'],'normals_manifest_sha256':options['normals_manifest_sha256'],
        'frame_count':25,'visual_quality_approved':False,'engine_import_verified':False}
    if canonical_digest(stage.details)!=canonical_digest(stage_expected):raise ProjectStorageError('Normal stage evidence differs from its saved full-frame outputs')
    verification=JobRequest.new(VERIFY,input_project='candidate.blend',options=options)
    verified,reopened=runner.run(verification,staged_inputs={**staged,'expression_normals.bin':normals,'expression_normals.json':manifest},timeout_s=remaining(),cancel=budget)
    unchanged();report=read_json(geometry.workdir/'expression_motion.json',geometry.bindings['motion_report_sha256'],4*1024*1024)
    cache=read_material_expression(folder,geometry.cache,options,verified.details,report,cancel_check=lambda:remaining())
    for name,path in {**staged,'expression_normals.bin':normals,'expression_normals.json':manifest}.items():
        expected_hash=original.get(name,options['normals_sha256'] if name.endswith('.bin') else options['normals_manifest_sha256'])
        for candidate in (path,folder/name,reopened/name):
            if candidate.is_symlink() or not candidate.is_file() or _digest(candidate,budget)!=expected_hash:
                raise ProjectStorageError('Material expression staged source/output changed: '+name)
    unchanged()
    watched=tuple(sorted((str(p),h) for p,h in hashes.items() if p.is_relative_to(store.root)))
    evidence=MaterialExpressionEvidence(folder,reopened,options,verified.details,watched,request.job_id,verification.job_id)
    return replace(geometry,cache=cache,material_evidence=evidence)
